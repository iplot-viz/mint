"""Assistant settings, read from MINT_ASSISTANT* environment variables or the MINT_XK_CONFIG file."""
import os
import stat
import tempfile
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

ENV_ENABLED = "MINT_ASSISTANT"
ENV_MODEL = "MINT_ASSISTANT_MODEL"
ENV_SHA256 = "MINT_ASSISTANT_SHA256"
ENV_THREADS = "MINT_ASSISTANT_THREADS"
ENV_RECORD = "MINT_ASSISTANT_RECORD"

MAX_DEFAULT_THREADS = 4


def _env(name: str) -> str:
    # load_env() in mint.__main__ keeps the end of line in the value.
    return (os.environ.get(name) or "").strip()


def _is_true(value: str) -> bool:
    return value.lower() in ("1", "true", "yes", "on")


@dataclass
class AssistantConfig:
    enabled: bool = False
    model_path: str = ""
    sha256: str = ""
    threads: int = 0
    record: bool = False

    @classmethod
    def from_environment(cls) -> "AssistantConfig":
        threads = 0
        try:
            threads = max(0, int(_env(ENV_THREADS) or 0))
        except ValueError:
            pass
        return cls(enabled=_is_true(_env(ENV_ENABLED)),
                   model_path=os.path.expanduser(_env(ENV_MODEL)),
                   sha256=_env(ENV_SHA256).lower(),
                   threads=threads or default_threads(), record=_is_true(_env(ENV_RECORD)))


def runtime_available() -> bool:
    """True when the optional model runtime (the 'assistant' extra) is installed."""
    return find_spec("llama_cpp") is not None


def _cgroup_cpu_limit():
    # Shared nodes may cap each user with a cgroup quota while os.cpu_count() reports the whole machine.
    if not hasattr(os, "getuid"):
        return None
    for path in ("/sys/fs/cgroup/cpu.max", f"/sys/fs/cgroup/user.slice/user-{os.getuid()}.slice/cpu.max"):
        try:
            quota, period = Path(path).read_text().split()[:2]
            if quota != "max":
                return max(1, int(int(quota) / int(period)))
        except (OSError, ValueError):
            pass
    return None


def cpu_budget() -> int:
    """Cores this process may really use: affinity, cgroup quota and physical cores."""
    counts = [os.cpu_count() or 1]
    if hasattr(os, "sched_getaffinity"):
        counts.append(len(os.sched_getaffinity(0)))
    limit = _cgroup_cpu_limit()
    if limit:
        counts.append(limit)
    try:
        import psutil
        physical = psutil.cpu_count(logical=False)
        if physical:
            counts.append(physical)
    except Exception:
        pass
    return max(1, min(counts))


def default_threads() -> int:
    # One core stays free for MINT itself; above 4 threads the gain is small on shared machines.
    return max(1, min(MAX_DEFAULT_THREADS, cpu_budget() - 1))


def state_dir() -> str:
    base = os.environ.get("IPLOT_DUMP_PATH") or os.path.join(str(Path.home()), ".local", "1Dtool")
    return os.path.join(base, "assistant")


def prompt_cache_dir():
    """A private folder on the local disk for the cached prompt state, or None.

    Each file is a few hundred MB; the folder must be ours, not a link and not readable by others.
    """
    uid = os.getuid() if hasattr(os, "getuid") else None
    path = os.path.join(tempfile.gettempdir(), f"mint-assistant-{uid}" if uid is not None else "mint-assistant")
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            return None
        if uid is not None and (info.st_uid != uid or stat.S_IMODE(info.st_mode) & 0o077):
            return None
        return path
    except OSError:
        return None
