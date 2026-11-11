"""What was asked and what the user did with each answer, kept on this machine to retrain the model on."""
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone

from iplotLogging import setupLogger
from mint.assistant.config import state_dir

logger = setupLogger.get_logger(__name__)

FILE = "record.jsonl"
# Past this the file starts again and the previous one is kept as record.jsonl.1: at most twice this on disk.
MAX_BYTES = 5 * 1024 * 1024  # 1000 to 2000 cards: months of use for one operator


def path() -> str:
    return os.path.join(state_dir(), FILE)


def write(card: str, outcome: str, request: str, snap, commands) -> None:
    """Adds one outcome ("applied", "dismissed", "undone") of a card. Never raises: it is a bonus."""
    try:
        target = path()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target) and os.path.getsize(target) > MAX_BYTES:
            os.replace(target, target + ".1")
        workspace = asdict(snap)
        workspace.pop("unlisted", None)
        workspace["now"] = snap.now.isoformat()
        line = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "card": card, "outcome": outcome,
                "request": request, "commands": list(commands), "workspace": workspace}
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception as e:
        logger.warning(f"Assistant: could not record the outcome of a card: {e}")
