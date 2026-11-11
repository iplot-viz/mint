"""Runs the language model in its own process, speaking one JSON object per line on stdin/stdout."""
import os
import sys

# Run as a script, Python puts this folder first on the import path: its modules
# (config, models...) must not shadow anything the model library imports.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != _HERE]

import contextlib  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import queue  # noqa: E402
import shutil  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

_OUT = sys.stdout


def send(**event):
    _OUT.write(json.dumps(event) + "\n")
    _OUT.flush()


def lower_priority():
    # The workstations are shared: the model must yield to MINT and to the other users.
    try:
        if hasattr(os, "nice"):
            os.nice(10)
        else:
            import ctypes
            below_normal = 0x4000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), below_normal)
    except Exception:
        pass


def sha256_of(path, chunk=8 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def file_key(path):
    """Identity of the file's content as the file system sees it.

    The change time is included: no user call can set it back after the file is rewritten.
    """
    info = os.stat(path)
    return f"{os.path.realpath(path)}|{info.st_size}|{info.st_mtime_ns}|{info.st_ctime_ns}|{info.st_ino}"


def verify_model(path, allowed, cache_path):
    """SHA-256 of the weights, refused unless allowed; runs before the model library opens the file.

    Remembered per (path, size, mtime): hashing a few GB takes seconds.
    """
    key = file_key(path)
    cache = {}
    if cache_path:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
    if not isinstance(cache, dict):
        cache = {}
    cached = cache.get(key)
    actual = cached if isinstance(cached, str) else sha256_of(path)
    if actual not in allowed:
        raise ValueError(f"the model file is not one MINT knows (SHA-256 {actual}); "
                         f"set MINT_ASSISTANT_SHA256 to this value to allow it")
    if cache_path and cache.get(key) != actual:
        cache[key] = actual
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            tmp = cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cache, f)
            os.replace(tmp, cache_path)
        except OSError as e:
            print(f"verified model cache not saved: {e}", file=sys.stderr, flush=True)
    return actual


class Worker:
    def __init__(self):
        self.llm = None
        self.sha256 = None
        self.cancelled = set()
        self.closing = False
        self.requests = queue.Queue()
        self._grammars = {}

    def read_stdin(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                send(ev="error", id=None, message="malformed request")
                continue
            if msg.get("op") == "cancel":
                # Tagged with the request, so a cancel cannot be lost to, or leak into, another one.
                self.cancelled.add(msg.get("id"))
                continue
            self.requests.put(msg)
        self.closing = True
        self.requests.put({"op": "quit"})

    def run(self):
        threading.Thread(target=self.read_stdin, daemon=True).start()
        while True:
            msg = self.requests.get()
            op = msg.get("op")
            if op == "quit":
                return
            try:
                if op == "load":
                    self.load(msg)
                elif op == "prime":
                    self.prime(msg)
                elif op == "warm":
                    self.warm(msg)
                elif op == "complete":
                    self.complete(msg)
                else:
                    send(ev="error", id=msg.get("id"), message=f"unknown op {op!r}")
            except Exception as e:  # report and keep serving: one bad request must not kill the model
                send(ev="error", id=msg.get("id"), message=f"{type(e).__name__}: {e}")

    def load(self, msg):
        t0 = time.perf_counter()
        if not os.path.isfile(msg["model"]):
            raise FileNotFoundError(f"model file not found: {msg['model']}")
        path = os.path.realpath(msg["model"])
        allowed = {h.lower() for h in msg.get("allowed_sha256") or []}
        checked = file_key(path)
        sha256 = verify_model(path, allowed, msg.get("verified_cache"))
        self.sha256 = sha256
        from llama_cpp import Llama
        threads = int(msg.get("threads") or 2)
        # A model trained for MINT declares its context size and the key/value cache is reserved for all of it.
        # Reading the header alone (vocab_only) takes a fraction of a second.
        probe = Llama(model_path=path, vocab_only=True, verbose=False)
        declared = {k: str(v)[:64] for k, v in (probe.metadata or {}).items() if k.startswith("mint.assistant.")}
        del probe
        try:
            ctx = int(declared.get("mint.assistant.context") or 4096)
        except ValueError:
            ctx = 4096
        self.llm = Llama(model_path=path, n_ctx=max(512, min(ctx, 32768)), n_threads=threads,
                         n_threads_batch=threads, n_batch=512, verbose=False, seed=0)
        if file_key(path) != checked:
            # Swapped between the check and the load: drop what was loaded.
            self.llm = None
            raise ValueError("the model file changed while it was being loaded")
        send(ev="loaded", seconds=round(time.perf_counter() - t0, 2), sha256=sha256, ctx=self.llm.n_ctx(), threads=threads, declared=declared)

    def _tokens(self, prompt):
        # Same tokenization as create_completion, so a warmed prefix matches.
        return self.llm.tokenize(prompt.encode("utf-8"), special=True)

    def _cached_prefix(self, tokens):
        cached = self.llm.input_ids[:self.llm.n_tokens]
        n = 0
        for a, b in zip(cached, tokens):
            if a != b:
                break
            n += 1
        return n

    def prime(self, msg):
        """Evaluate the fixed part of the prompt, or restore it from the cache of an earlier session.

        Uses llama.cpp sequence state files: the key/value cache is read and written in C, no pickling.
        """
        if self.llm is None:
            raise RuntimeError("model not loaded")
        t0 = time.perf_counter()
        tokens = self._tokens(msg["prompt"])
        path = self._cache_path(msg.get("cache_dir"), msg["prompt"])
        source = "cache" if path and self._restore(path, tokens) else "computed"
        if source == "computed":
            self.llm.n_tokens = 0
            self.llm.eval(tokens)
            if path:
                self._save(path, tokens)
        send(ev="primed", tokens=len(tokens), source=source, seconds=round(time.perf_counter() - t0, 2))

    def _cache_path(self, cache_dir, prompt):
        if not cache_dir or not self.sha256:
            return None
        import llama_cpp
        key = hashlib.sha256("\0".join([self.sha256, llama_cpp.__version__, str(self.llm.n_ctx()),
                                        prompt]).encode("utf-8")).hexdigest()[:32]
        return os.path.join(cache_dir, f"prefix-{key}.kv")

    def _restore(self, path, tokens):
        if not os.path.isfile(path):
            return False
        import ctypes
        import llama_cpp
        capacity = self.llm.n_ctx()
        saved = (llama_cpp.llama_token * capacity)()
        count = ctypes.c_size_t(0)
        self.llm.n_tokens = 0
        read = llama_cpp.llama_state_seq_load_file(self.llm._ctx.ctx, path.encode("utf-8"), 0, saved, capacity,
                                                   ctypes.byref(count))
        if not read or list(saved[:count.value]) != list(tokens):
            # Stale or damaged: the next eval starts from position 0 and overwrites whatever was loaded.
            self.llm.n_tokens = 0
            return False
        self.llm.input_ids[:len(tokens)] = tokens
        self.llm.n_tokens = len(tokens)
        with contextlib.suppress(OSError):
            os.utime(path)  # the most recently used files are the ones kept
        return True

    def _save(self, path, tokens):
        import llama_cpp
        folder, partial = os.path.dirname(path), path + ".partial"
        try:
            if shutil.disk_usage(folder).free < 2 * 1024 ** 3:
                return
            array = (llama_cpp.llama_token * len(tokens))(*tokens)
            if llama_cpp.llama_state_seq_save_file(self.llm._ctx.ctx, partial.encode("utf-8"), 0, array,
                                                   len(tokens)):
                os.replace(partial, path)
            # Each file is a few hundred MB: keep only the most recent ones.
            files = sorted((os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".kv")),
                           key=os.path.getmtime, reverse=True)
            for old in files[3:]:
                with contextlib.suppress(OSError):
                    os.remove(old)
        except OSError as e:
            print(f"prompt cache not saved: {e}", file=sys.stderr, flush=True)
        finally:
            with contextlib.suppress(OSError):
                os.remove(partial)

    def warm(self, msg):
        if self.llm is None:
            raise RuntimeError("model not loaded")
        t0 = time.perf_counter()
        tokens = self._tokens(msg["prompt"])
        common = self._cached_prefix(tokens)
        if common < len(tokens):
            self.llm.n_tokens = common
            self.llm.eval(tokens[common:])
        send(ev="warmed", tokens=len(tokens), new=len(tokens) - common,
             seconds=round(time.perf_counter() - t0, 3))

    def _grammar(self, text):
        grammar = self._grammars.get(text)
        if grammar is None:
            from llama_cpp import LlamaGrammar
            grammar = LlamaGrammar.from_string(text, verbose=False)
            if len(self._grammars) > 16:
                self._grammars.clear()
            self._grammars[text] = grammar
        return grammar

    def complete(self, msg):
        if self.llm is None:
            raise RuntimeError("model not loaded")
        from llama_cpp import LogitsProcessorList, StoppingCriteriaList
        from mint.assistant.doubt import TokenWatch
        request = msg.get("id")
        prompt = msg["prompt"]
        tokens = self._tokens(prompt)
        max_tokens = int(msg.get("max_tokens") or 160)
        if len(tokens) + max_tokens > self.llm.n_ctx():
            raise ValueError(f"the request needs {len(tokens) + max_tokens} tokens of context, "
                             f"the model has {self.llm.n_ctx()}")
        cached = self._cached_prefix(tokens)
        grammar = self._grammar(msg["grammar"]) if msg.get("grammar") else None

        def stopped(*_):
            return self.closing or request in self.cancelled

        t0 = time.perf_counter()
        t_first = None
        parts = []
        n_gen = 0
        finish = None
        watch = TokenWatch()
        if not stopped():
            stream = self.llm.create_completion(
                prompt, max_tokens=max_tokens, temperature=0.0, top_k=1,
                repeat_penalty=1.0, grammar=grammar, stream=True, stopping_criteria=StoppingCriteriaList([stopped]),
                logits_processor=LogitsProcessorList([watch]))
            for chunk in stream:
                if t_first is None:
                    t_first = time.perf_counter()
                parts.append(chunk["choices"][0]["text"])
                finish = chunk["choices"][0].get("finish_reason") or finish
                n_gen += 1
        t_end = time.perf_counter()
        cancelled = stopped()
        self.cancelled.discard(request)
        # "length" means the answer was cut by max_tokens: its last line may be half a command.
        try:
            ids = watch.ids(lambda token: self.llm.detokenize([token]).decode("utf-8", "ignore"))
        except Exception:  # how sure it was is a bonus: never lose the answer for it
            ids = []
        send(ev="done", id=request, text="".join(parts), cancelled=cancelled, finish=finish, ids=ids,
             timings={"prompt_tokens": len(tokens), "cached_tokens": cached, "generated": n_gen,
                      "prefill_s": round((t_first or t_end) - t0, 3), "total_s": round(t_end - t0, 3)})


def main():
    global _OUT
    # The protocol gets its own copy of stdout and file descriptor 1 is pointed at
    # stderr, so anything the C library prints cannot corrupt a JSON line.
    _OUT = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    lower_priority()
    Worker().run()


if __name__ == "__main__":
    main()
