"""Answers to the assistant's own questions."""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from mint.assistant.commands import Command
from mint.assistant.snapshot import Snapshot

SECONDS = {"ms": 0.001, "msec": 0.001, "millisecond": 0.001, "milliseconds": 0.001,
           "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
           "min": 60, "mins": 60, "minute": 60, "minutes": 60,
           "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
           "d": 86400, "day": 86400, "days": 86400}
VALUE = re.compile(r"^\s*(?:about|around|over|at|by|of|x|×)?\s*(-?\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)?\s*[.!]?\s*$")
# More words than this is a new request rather than an answer.
MAX_ANSWER_WORDS = 6


@dataclass
class OpenQuestion:
    request: str
    snap: Snapshot
    commands: List[Command] = field(default_factory=list)
    command: Optional[Command] = None
    param: str = ""


def value_in(text: str, param: str) -> Optional[float]:
    """The number a short answer gives for a parameter ("10 s", "2 Hz", "x 3.6"), in its unit, or None."""
    m = VALUE.match(text or "")
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "").lower()
    if param == "seconds":
        if not unit:
            return value  # a bare number answering "over how long" is seconds
        return value * SECONDS[unit] if unit in SECONDS else None
    if param == "hz":
        return value if unit in ("", "hz") else None
    return value if not unit else None


def is_answer(text: str) -> bool:
    return 0 < len((text or "").split()) <= MAX_ANSWER_WORDS


# "undo that", in the languages the assistant understands: MINT undoes the last card itself.
UNDO_WORDS = {"undo", "deshaz", "deshazlo", "deshacer", "annule", "annuler", "rückgängig", "annulla", "desfaz",
              "desfazer", "revert"}


def is_undo(text: str) -> bool:
    words = re.findall(r"\w+", (text or "").lower())
    return 0 < len(words) <= 4 and words[0] in UNDO_WORDS


def with_answer(question: OpenQuestion, answer: str) -> str:
    """The original request with the user's answer, for the model."""
    return f"{question.request.rstrip(' .?!')}. {answer.strip()}"
