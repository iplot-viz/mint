"""Accuracy and latency of the assistant's model on requests with known answers, in-process and without Qt.

    python -m mint.tools.assistant_eval --model M.gguf --format chatml --cases cases.jsonl [--threads 4]

Each line of the cases file:
    {"id": "...", "workspace": {...snapshot...}, "request": "...", "expect": ["process r1 moving_average window=30s", ...]}
"expect" lists the acceptable answers, one command per line; for ask and say only the verb counts.
"--quiet-failures" prints only the scores.
"""
import argparse
import json
import statistics
import sys
import time
from dataclasses import fields
from datetime import datetime, timedelta

from mint.assistant import check, commands, doubt, models, prompt, recipes
from mint.assistant.snapshot import PlotInfo, RowInfo, Snapshot


def _known(cls, values: dict) -> dict:
    """The fields the class has: files written by older versions may carry others."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in values.items() if k in names}


def snapshot_from_dict(d: dict) -> Snapshot:
    rows = [RowInfo(**_known(RowInfo, r)) for r in d.get("rows", [])]
    plots = [PlotInfo(**_known(PlotInfo, p)) for p in d.get("plots", [])]
    snap = Snapshot(rows=rows, plots=plots, selected=d.get("selected", []), range_text=d.get("range_text", ""),
                    range_seconds=d.get("range_seconds"), pulse_mode=d.get("pulse_mode", False),
                    last_action=d.get("last_action", ""))
    if d.get("now"):
        snap.now = datetime.fromisoformat(d["now"])
    return snap


def normalize(cmds, now=None, range_seconds=None):
    """What the user sees: a command MINT turns into a question (a number is missing) counts as 'ask'."""
    out = []
    for c in cmds:
        if c.verb == "process":
            try:
                recipes.resolve_params(c.words[0], c.params, range_seconds)
            except recipes.RecipeError:
                out.append(("ask",))
                continue
        if c.verb == "range" and c.words[:1] == ["day"] and c.words[1] in ("today", "yesterday") and now:
            day = now.date() - timedelta(days=1 if c.words[1] == "yesterday" else 0)
            c = commands.Command("range", words=["day", day.isoformat()])
        if c.verb in ("ask", "say", "find"):
            # Free text, and search words that work are many: only the decision is graded.
            out.append((c.verb,))
            continue
        params = tuple(sorted((k, float(v)) if _is_number(v) else (k, v) for k, v in c.params.items()))
        ids = tuple(c.ids) if c.verb == "combine" else tuple(sorted(c.ids))
        out.append((c.verb, ids, tuple(c.words), params, tuple(sorted(c.flags))))
    return tuple(sorted(out))


def _is_number(v):
    try:
        float(v)
        return True
    except ValueError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--format", required=True, choices=sorted(prompt.FORMATS))
    ap.add_argument("--cases", required=True)
    ap.add_argument("--workspaces", help="JSON object of named workspaces, for cases that give \"ws\"")
    ap.add_argument("--few-shot", choices=["auto", "yes", "no"], default="auto",
                    help="worked examples in the prompt; auto: as the model file declares (as in MINT)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--quiet-failures", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--split", choices=["all", "dev", "test"], default="all",
                    help="dev = odd case numbers (tune the prompt on these), test = even ones (never look at them)")
    args = ap.parse_args(argv)

    from llama_cpp import Llama, LlamaGrammar, LogitsProcessorList

    cases = [json.loads(line) for line in open(args.cases, encoding="utf-8") if line.strip()]
    if args.workspaces:
        with open(args.workspaces, encoding="utf-8") as f:
            named = json.load(f)
        for case in cases:
            if "ws" in case and "workspace" not in case:
                case["workspace"] = named[case["ws"]]
    if args.split != "all":
        parity = 1 if args.split == "dev" else 0
        cases = [c for c in cases if int("".join(ch for ch in c["id"] if ch.isdigit()) or 0) % 2 == parity]
    if args.limit:
        cases = cases[:args.limit]
    # As in real use, several requests in a row on the same workspace.
    cases.sort(key=lambda c: json.dumps(c["workspace"], sort_keys=True))
    fmt = prompt.ChatFormat(args.format)
    t0 = time.perf_counter()
    llm = Llama(model_path=args.model, n_ctx=args.ctx, n_threads=args.threads, n_threads_batch=args.threads,
                n_batch=512, verbose=False, seed=0)
    load_s = time.perf_counter() - t0

    declared = {k: str(v) for k, v in (llm.metadata or {}).items() if k.startswith("mint.assistant.")}
    few = models.few_shot("", declared) if args.few_shot == "auto" else args.few_shot == "yes"
    head = prompt.fixed_prefix(fmt, few)
    head_tokens = llm.tokenize(head.encode("utf-8"), special=True)
    t0 = time.perf_counter()
    llm.eval(head_tokens)
    cold_s = time.perf_counter() - t0

    ok = 0
    by_verb = {}
    request_s, warm_s, gen_tokens, workspace_tokens = [], [], [], []
    failures = []
    asked = {}  # (asked instead, was right) -> cases
    for case in cases:
        snap = prompt.visible(snapshot_from_dict(case["workspace"]))
        warm, full = prompt.build(fmt, snap, case["request"], few)
        # Same as MINT: the workspace is evaluated while the user types, the request after Enter.
        tokens = llm.tokenize(warm.encode("utf-8"), special=True)
        workspace_tokens.append(len(tokens) - len(head_tokens))
        common = 0
        for a, b in zip(llm.input_ids[:llm.n_tokens], tokens):
            if a != b:
                break
            common += 1
        t0 = time.perf_counter()
        if common < len(tokens):
            llm.n_tokens = common
            llm.eval(tokens[common:])
        warm_s.append(time.perf_counter() - t0)

        row_ids, plot_ids = prompt.answer_ids(snap, case["request"])
        grammar = LlamaGrammar.from_string(commands.build_grammar(row_ids, plot_ids, recipes.load()), verbose=False)
        t0 = time.perf_counter()
        watch = doubt.TokenWatch()
        out = llm.create_completion(full, max_tokens=160, temperature=0.0, top_k=1, repeat_penalty=1.0,
                                    grammar=grammar, logits_processor=LogitsProcessorList([watch]))
        request_s.append(time.perf_counter() - t0)
        text = out["choices"][0]["text"]
        gen_tokens.append(out["usage"]["completion_tokens"])
        try:
            got = normalize(check.review(snap, case["request"], commands.parse(text)), snap.now, snap.range_seconds)
        except commands.CommandError as e:
            got = ("unparsable", str(e))
        expected = [normalize(commands.parse(e), snap.now, snap.range_seconds) for e in case["expect"]]
        hit = got in expected
        # As MINT does: a proposal naming a row or plot the model hesitated on becomes a question.
        unsure = got[:1] != (("ask",),) and doubt.doubtful(
            watch.ids(lambda t: llm.detokenize([t]).decode("utf-8", "ignore")), set(row_ids) | set(plot_ids))
        asked[(bool(unsure), hit)] = asked.get((bool(unsure), hit), 0) + 1
        verb = commands.parse(case["expect"][0])[0].verb
        stats = by_verb.setdefault(verb, [0, 0])
        stats[1] += 1
        if hit:
            ok += 1
            stats[0] += 1
        else:
            failures.append({"id": case["id"], "request": case["request"], "got": text, "expect": case["expect"],
                             "asked": bool(unsure)})

    n = len(cases)
    summary = {
        "model": args.model.split("/")[-1], "split": args.split, "threads": args.threads, "few_shot": few,
        "cases": n,
        "accuracy": round(ok / n, 3),
        "by_verb": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_verb.items())},
        "load_s": round(load_s, 2), "cold_prefix_tokens": len(head_tokens), "cold_prefix_s": round(cold_s, 1),
        "warm_workspace_s_median": round(statistics.median(warm_s), 2),
        # A new workspace (or the first request after opening one) pays this while the user types.
        "warm_workspace_s_max": round(max(warm_s), 2), "workspace_tokens_max": max(workspace_tokens),
        "request_s_median": round(statistics.median(request_s), 2),
        "request_s_p90": round(sorted(request_s)[int(0.9 * (n - 1))], 2),
        "gen_tokens_median": statistics.median(gen_tokens),
        # The doubt check: wrong answers it turns into a question, and right ones it questions for nothing.
        "asked_instead_of_wrong": asked.get((True, False), 0), "asked_instead_of_right": asked.get((True, True), 0),
    }
    print(json.dumps(summary))
    if not args.quiet_failures:
        for f in failures:
            print(json.dumps(f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
