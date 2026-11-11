"""Client side of the model worker: starts it with QProcess and exchanges JSON lines."""
import json
import os
import shutil
import subprocess
import sys
from collections import deque

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)

WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker.py")

# What the model process needs to find Python, its libraries and a temporary folder. Nothing
# else of MINT's environment (data source settings, credentials) is passed to it.
WORKER_ENVIRONMENT = ("PATH", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "LD_LIBRARY_PATH", "HOME", "USERPROFILE",
                      "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL")


ISOLATION = ["--user", "--map-root-user", "--net"]
_isolation = None


def network_isolation():
    """Command prefix that starts the model process without network access, or [] when unavailable.

    On Linux an empty network namespace (unshare) leaves the process nothing to connect to.
    """
    global _isolation
    if _isolation is None:
        _isolation = []
        unshare = shutil.which("unshare") if sys.platform.startswith("linux") else None
        if unshare:
            try:
                probe = subprocess.run([unshare, *ISOLATION, "true"], capture_output=True, timeout=5)
                if probe.returncode == 0:
                    _isolation = [unshare, *ISOLATION]
            except (OSError, subprocess.SubprocessError):
                pass
    return _isolation


def worker_environment() -> QProcessEnvironment:
    system = QProcessEnvironment.systemEnvironment()
    env = QProcessEnvironment()
    for name in WORKER_ENVIRONMENT:
        if system.contains(name):
            env.insert(name, system.value(name))
    env.insert("PYTHONUNBUFFERED", "1")
    return env

STOPPED, LOADING, READY, BUSY, FAILED = "stopped", "loading", "ready", "busy", "failed"


class ModelEngine(QObject):
    stateChanged = Signal(str)
    loaded = Signal(dict)
    primed = Signal(dict)
    completed = Signal(int, str, dict)
    failed = Signal(int, str)

    def __init__(self, model_path: str, threads: int, allowed_sha256=(), verified_cache: str = None, parent=None):
        super().__init__(parent)
        self._load_request = {"op": "load", "model": model_path, "threads": threads,
                              "allowed_sha256": list(allowed_sha256), "verified_cache": verified_cache}
        self._process = None
        self._buffer = b""
        self._stderr_tail = deque(maxlen=20)
        self._state = STOPPED
        self._next_id = 0
        self._pending = None
        self._last_warm = None
        self.isolated = False

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, state: str):
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    def start(self):
        if self._process is not None:
            return
        process = QProcess(self)
        process.setProcessEnvironment(worker_environment())
        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        self._set_state(LOADING)
        command = [*network_isolation(), sys.executable, WORKER_SCRIPT]
        self.isolated = len(command) > 2
        logger.info("Assistant model process " + ("without network access" if self.isolated else
                                                  "started (network isolation not available here)"))
        process.start(command[0], command[1:])
        self._send(self._load_request)

    def prime(self, prompt: str, cache_dir: str = None):
        """Evaluate the fixed prompt prefix, restored from the local cache when it is there."""
        self._last_warm = None
        self._send({"op": "prime", "prompt": prompt, "cache_dir": cache_dir})

    def warm(self, prompt: str):
        """Evaluate a prompt prefix now, so the next request only pays for the new text."""
        if self._state != READY or prompt == self._last_warm:
            return
        self._last_warm = prompt
        self._send({"op": "warm", "prompt": prompt})

    def complete(self, prompt: str, grammar: str, max_tokens: int = 160) -> int:
        if self._state != READY:
            raise RuntimeError(f"the model is not ready ({self._state})")
        self._next_id += 1
        self._pending = self._next_id
        self._set_state(BUSY)
        self._send({"op": "complete", "id": self._next_id, "prompt": prompt, "grammar": grammar,
                    "max_tokens": max_tokens})
        return self._next_id

    def cancel(self):
        if self._state == BUSY and self._pending is not None:
            self._send({"op": "cancel", "id": self._pending})

    def shutdown(self):
        process, self._process = self._process, None
        if process is None:
            return
        for signal, slot in ((process.finished, self._on_finished), (process.errorOccurred, self._on_error),
                             (process.readyReadStandardOutput, self._on_stdout),
                             (process.readyReadStandardError, self._on_stderr)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        if process.state() != QProcess.ProcessState.NotRunning:
            if self._state == BUSY:
                # In the middle of a computation it would not read 'quit' for seconds, and it
                # keeps nothing worth saving.
                process.kill()
            else:
                process.write(b'{"op": "quit"}\n')
                process.closeWriteChannel()
                # Waiting blocks the window (QProcess docs), so the wait is short and a kill follows.
                if not process.waitForFinished(300):
                    process.kill()
            process.waitForFinished(300)
        self._set_state(STOPPED)

    def _send(self, message: dict):
        if self._process is not None:
            self._process.write((json.dumps(message) + "\n").encode("utf-8"))

    def _on_stdout(self):
        if self._process is None:
            return
        self._buffer += bytes(self._process.readAllStandardOutput())
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                logger.debug(f"assistant worker: {line[:200]!r}")
                continue
            self._on_event(event)

    def _on_event(self, event: dict):
        kind = event.get("ev")
        if kind == "loaded":
            logger.info(f"Assistant model loaded in {event.get('seconds')} s ({event.get('threads')} threads)")
            self._set_state(READY)
            self.loaded.emit(event)
        elif kind == "primed":
            logger.info(f"Assistant prompt ready in {event.get('seconds')} s ({event.get('source')})")
            self.primed.emit(event)
        elif kind == "warmed":
            logger.debug(f"Assistant prompt warmed: {event}")
        elif kind == "done":
            if event.get("id") == self._pending:
                self._pending = None
                self._set_state(READY)
                timings = dict(event.get("timings") or {}, cancelled=bool(event.get("cancelled")),
                               finish=event.get("finish"), ids=event.get("ids") or [])
                self.completed.emit(int(event["id"]), event.get("text", ""), timings)
        elif kind == "error":
            message = event.get("message", "unknown error")
            request = event.get("id")
            logger.warning(f"Assistant worker error: {message}")
            if self._state == LOADING:
                self._set_state(FAILED)
                self.failed.emit(-1, message)
            elif request is not None and request == self._pending:
                self._pending = None
                self._set_state(READY)
                self.failed.emit(int(request), message)

    def _on_stderr(self):
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self._stderr_tail.append(line)
                logger.debug(f"assistant worker: {line}")

    def _on_finished(self, exit_code, _status):
        pending, self._pending = self._pending, None
        self._process = None
        tail = " | ".join(list(self._stderr_tail)[-3:])
        message = f"the model process stopped (exit code {exit_code})" + (f": {tail}" if tail else "")
        logger.warning(f"Assistant: {message}")
        self._set_state(FAILED)
        self.failed.emit(pending if pending is not None else -1, message)

    def _on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._process = None
            self._set_state(FAILED)
            self.failed.emit(-1, "the model process could not start")
