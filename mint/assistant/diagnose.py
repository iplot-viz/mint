"""Why rows of the table aren't drawn, read from MINT itself: answered without the model."""
import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from mint.assistant.snapshot import RowInfo, Snapshot

# A question about the table's state: "why are they red?", "what is wrong?"...
ABOUT_STATE = re.compile(
    r"\b(?:red|wrong|errors?|fail\w*|broken|problems?|issues?|not (?:work\w*|drawn|shown)|doesn'?t work|nothing|"
    r"empty|blank)\b", re.IGNORECASE)
ASKING = re.compile(r"\?|^\s*(?:why|what|how come)\b", re.IGNORECASE)
INVALID = "Invalid|"
# A request to put the data sources right: "fix the data source of the signals"...
FIXING = re.compile(r"\b(?:fix|correct|repair|solve|sort out|change|update|switch|replace)\b", re.IGNORECASE)
SOURCE_WORDS = re.compile(r"\b(?:data ?sources?|sources?|ds)\b", re.IGNORECASE)
THEM = re.compile(r"^\s*(?:please\s+)?(?:fix|correct|change|repair)\w*\s+(?:it|them|that|those|these|this)\b",
                  re.IGNORECASE)


@dataclass
class Problems:
    missing: Dict[str, List[RowInfo]] = field(default_factory=dict)  # a data source not here -> the rows using it
    invalid: List[Tuple[RowInfo, str]] = field(default_factory=list)  # other rows that can't be drawn, and why
    sources: List[str] = field(default_factory=list)  # those a row can use here

    def __bool__(self):
        return bool(self.missing or self.invalid)


def find(snap: Snapshot, sources) -> Problems:
    """Rows naming a data source that isn't here, then rows whose Status says they are invalid."""
    problems = Problems(sources=list(sources))
    for row in snap.rows:
        if row.data_source and row.data_source not in problems.sources:
            problems.missing.setdefault(row.data_source, []).append(row)
        elif row.status.startswith(INVALID):
            problems.invalid.append((row, row.status[len(INVALID):].strip()))
    return problems


def asks_about_state(text: str) -> bool:
    """A question about what is wrong, red or not drawn, rather than a request to change something."""
    return bool(ABOUT_STATE.search(text or "")) and bool(ASKING.search(text or ""))


def asks_to_fix(text: str, sources, offered: bool = False) -> bool:
    """A request to fix the data sources that names none of them: the change MINT found is the one meant. Right
    after MINT offered it, "fix them" says the same."""
    text = text or ""
    if any(re.search(rf"(?<![\w-]){re.escape(source)}(?![\w-])", text, re.IGNORECASE) for source in sources):
        return False
    return bool(FIXING.search(text) and SOURCE_WORDS.search(text)) or (offered and bool(THEM.search(text)))


def replacement(name: str, sources) -> Optional[str]:
    """The data source here that one no longer here most likely became: imaspy -> imas; the only one there is."""
    sources = list(sources)
    lowered = {source.lower(): source for source in sources}
    prefixed = [s for s in sources if name.lower().startswith(s.lower()) or s.lower().startswith(name.lower())]
    if len(prefixed) == 1:
        return prefixed[0]
    close = difflib.get_close_matches(name.lower(), list(lowered), n=1, cutoff=0.6)
    if close:
        return lowered[close[0]]
    return sources[0] if len(sources) == 1 else None
