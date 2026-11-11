"""The command language the model answers in: grammar and parser."""
import re
import shlex
from dataclasses import dataclass, field
from typing import Dict, List

MAX_COMMANDS = 3
MAX_IDS = 12
RANGE_UNITS = ("seconds", "minutes", "hours", "days")
WINDOW_UNITS = ("ms", "s", "min", "h", "d")
WINDOW_SECONDS = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "d": 86400}
WINDOW = re.compile(r"^(-?\d+(?:\.\d+)?)(ms|s|min|h|d)$")
COMBINE_OPS = ("subtract", "add", "multiply", "divide")
PLOT_SWITCHES = ("log", "grid", "legend")


class CommandError(ValueError):
    """The model's answer is not valid command text."""


@dataclass
class Command:
    verb: str
    ids: List[str] = field(default_factory=list)
    words: List[str] = field(default_factory=list)
    params: Dict[str, str] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    text: str = ""

    def __str__(self):
        """The command as the model writes it, which parse() reads back ("Last applied" shows it)."""
        ids, words = self.ids, self.words
        if self.verb == "combine":
            ids, words = words + ids, []
        elif self.verb == "move":
            words = ["to"] + words
        elif self.verb == "range" and words[:1] == ["from"]:
            words = ["from", f'"{words[1]}"', "to", f'"{words[2]}"']
        params = [f"window={v}s" if k == "seconds" else f'{k}="{v}"' if k == "title" else f"{k}={v}"
                  for k, v in self.params.items()]
        return " ".join([self.verb] + ids + words + params + self.flags + ([f'"{self.text}"'] if self.text else []))


def _alt(options) -> str:
    return " | ".join(f'"{o}"' for o in options)


def build_grammar(row_ids, plot_ids, recipes: dict) -> str:
    """GBNF grammar of the answers valid for these rows and plots.

    Numbers are optional even where a recipe needs them: a forced number is invented, while MINT can ask.
    """
    windowed = [name for name, r in recipes.items() if "seconds" in r.get("params", {})]
    recipe_rules = []
    for name, recipe in recipes.items():
        params = recipe.get("params", {})
        if "seconds" in params:
            continue
        rule = f'"{name}"' + "".join(f' (" {pname}=" num)?' for pname in params)
        recipe_rules.append(rule)
    if windowed:
        # The window keeps the user's unit: converting "a quarter of an hour" is MINT's job.
        recipe_rules.insert(0, f'({_alt(windowed)}) (" window=" num ({_alt(WINDOW_UNITS)}))?')

    verbs = (["plot-cmd"] if plot_ids else []) + ["find", "range", "draw", "say"]
    if row_ids:
        # ask is for choosing among rows: with an empty table, a request about a signal is a search.
        verbs = ["process", "combine", "move", "remove"] + verbs + ["ask"]
    lines = [
        f"root ::= cmd (\"\\n\" cmd){{0,{MAX_COMMANDS - 1}}}",
        "cmd ::= " + " | ".join(verbs),
        "num ::= \"-\"? [0-9]{1,9} (\".\" [0-9]{1,6})?",
        "int ::= [1-9] [0-9]{0,5}",
        "str ::= \"\\\"\" [^\"\\\\\\n]{1,160} \"\\\"\"",
        "word ::= [A-Za-z0-9_:.+-]{1,40}",
        "find ::= \"find\" (\" \" word){1,4}",
        "range ::= \"range \" (\"last \" int \" \" (" + _alt(RANGE_UNITS) + ") | \"day \" (\"today\" | \"yesterday\" | "
        "[0-9]{4} \"-\" [0-9]{2} \"-\" [0-9]{2})"
        " | \"month \" [0-9]{4} \"-\" [0-9]{2} | \"from \" str \" to \" str | \"pulse \" [A-Za-z0-9_:.+/()-]{1,80})",
        "draw ::= \"draw\"",
        "ask ::= \"ask \" str",
        "say ::= \"say \" str",
    ]
    if row_ids:
        lines += [
            "row ::= " + _alt(row_ids),
            f"rows ::= (\" \" row){{1,{MAX_IDS}}}",
            "process ::= \"process\" rows \" \" recipe (\" replace\")?",
            "recipe ::= " + " | ".join(recipe_rules),
            "combine ::= \"combine \" (" + _alt(COMBINE_OPS) + ") \" \" row \" \" row",
            "remove ::= \"remove\" rows",
        ]
        target = "plot | \"new\"" if plot_ids else "\"new\""
        lines.append(f"move ::= \"move\" rows \" to \" ({target})")
    if plot_ids:
        lines += [
            "plot ::= " + _alt(plot_ids),
            "plot-cmd ::= \"plot\" ((\" \" plot){1," + str(MAX_IDS) + "} | \" all\") prop{1,4}",
            "onoff ::= \"on\" | \"off\"",
            "prop ::= " + " | ".join(f'" {s}=" onoff' for s in PLOT_SWITCHES) + " | \" title=\" str",
        ]
    return "\n".join(lines) + "\n"


def merge(cmds: List[Command]) -> List[Command]:
    """Fold commands that only differ in their ids, and drop repeated ones."""
    merged = []
    for c in cmds:
        twin = next((m for m in merged if m.verb == c.verb and m.verb in ("process", "plot", "remove")
                     and m.words == c.words and m.params == c.params and m.flags == c.flags
                     and "all" not in m.ids + c.ids), None)
        if twin is not None:
            twin.ids += [i for i in c.ids if i not in twin.ids]
        elif str(c) not in [str(m) for m in merged]:
            merged.append(c)
    return merged


def parse(text: str) -> List[Command]:
    """Commands of an answer. Raises CommandError on anything outside the language."""
    commands = []
    for line in (text or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as e:
            raise CommandError(f"unreadable command {line!r}: {e}")
        if not tokens:
            continue
        commands.append(_parse_tokens(tokens, line))
    if not commands:
        raise CommandError("empty answer")
    return merge(commands)[:MAX_COMMANDS]


def _plain(value: float) -> str:
    return str(int(value)) if value == int(value) else repr(round(value, 9))


def _ids(tokens, prefix):
    ids = []
    while tokens and len(tokens[0]) > 1 and tokens[0][0] == prefix and tokens[0][1:].isdigit():
        token = tokens.pop(0)
        if token not in ids:
            ids.append(token)
    return ids


def _parse_tokens(tokens, line) -> Command:
    verb, rest = tokens[0], tokens[1:]
    if verb == "process":
        ids = _ids(rest, "r")
        if not ids or not rest:
            raise CommandError(f"process needs rows and a recipe: {line!r}")
        cmd = Command("process", ids=ids, words=[rest.pop(0)])
        for token in rest:
            if token == "replace":
                cmd.flags.append("replace")
            elif "=" in token:
                key, value = token.split("=", 1)
                if key == "window":
                    m = WINDOW.match(value)
                    if not m:
                        raise CommandError(f"unreadable window {value!r}")
                    key, value = "seconds", _plain(float(m.group(1)) * WINDOW_SECONDS[m.group(2)])
                cmd.params[key] = value
            else:
                raise CommandError(f"unexpected {token!r} in {line!r}")
        return cmd
    if verb == "combine":
        if len(rest) != 3 or rest[0] not in COMBINE_OPS:
            raise CommandError(f"combine needs an operation and two rows: {line!r}")
        return Command("combine", ids=rest[1:], words=[rest[0]])
    if verb == "plot":
        ids = ["all"] if rest[:1] == ["all"] else _ids(rest, "p")
        if ids == ["all"]:
            rest = rest[1:]
        cmd = Command("plot", ids=ids)
        for token in rest:
            if "=" not in token:
                raise CommandError(f"unexpected {token!r} in {line!r}")
            key, value = token.split("=", 1)
            cmd.params[key] = value
        if not ids or not cmd.params:
            raise CommandError(f"plot needs plots and a setting: {line!r}")
        return cmd
    if verb == "find":
        if not rest:
            raise CommandError("find needs words")
        return Command("find", words=rest[:4])
    if verb == "range":
        if not rest:
            raise CommandError("range needs a period")
        kind = rest[0]
        if kind == "last" and len(rest) == 3 and rest[1].isdigit() and rest[2] in RANGE_UNITS:
            return Command("range", words=rest)
        if kind in ("day", "month", "pulse") and len(rest) == 2:
            return Command("range", words=rest)
        if kind == "from" and len(rest) == 4 and rest[2] == "to":
            return Command("range", words=["from", rest[1], rest[3]])
        raise CommandError(f"unreadable range {line!r}")
    if verb == "move":
        ids = _ids(rest, "r")
        if not ids or len(rest) != 2 or rest[0] != "to":
            raise CommandError(f"move needs rows and a target: {line!r}")
        return Command("move", ids=ids, words=[rest[1]])
    if verb == "remove":
        ids = _ids(rest, "r")
        if not ids or rest:
            raise CommandError(f"remove needs rows: {line!r}")
        return Command("remove", ids=ids)
    if verb == "draw" and not rest:
        return Command("draw")
    if verb in ("ask", "say") and len(rest) == 1:
        return Command(verb, text=rest[0])
    raise CommandError(f"unknown command {line!r}")
