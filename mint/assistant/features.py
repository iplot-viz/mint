"""MINT's own tools a request can be about: Statistics, the mini-map and Search Vars. MINT opens them or says
what they are, without the model: a small model takes "the statistics" for a signal to look for."""
import re
from dataclasses import dataclass
from typing import Optional

STATISTICS = "statistics"
MINIMAP = "minimap"
SEARCH = "search"

OPEN = "open"
CLOSE = "close"
ABOUT = "about"

NAMES = {
    STATISTICS: re.compile(r"\bstat(?:s|istics?)\b|\bstatisti", re.IGNORECASE),
    MINIMAP: re.compile(r"\bmini[- ]?maps?\b", re.IGNORECASE),
    SEARCH: re.compile(r"\bsearch[- ]?vars?\b|\bsearch(?:ing)?(?: for)?(?: the)? variables\s*(?:window|dialog|panel|"
                       r"tree|browser|button)?\s*[?.!]?$|\bvariables? (?:browser|tree)\b", re.IGNORECASE),
}
OPENING = re.compile(
    r"\b(?:open|show|display|enable|activate|turn on|switch on|bring up|see|view|give me|share|pull up|get me)\b",
    re.IGNORECASE)
CLOSING = re.compile(r"\b(?:close|hide|disable|deactivate|turn off|switch off|get rid of|remove)\b", re.IGNORECASE)
ASKING = re.compile(r"^\s*(?:what|where|how|which|why|is there|are there)\b", re.IGNORECASE)

ABOUT_TEXT = {
    STATISTICS: ("Statistics shows, for each signal drawn, its minimum, average and maximum, its first and last values "
                 "with their times, and how many samples it has. It's the bar chart button above the plots."),
    MINIMAP: ("The mini-map is a small overview of the plot under the canvas: it shows the whole time drawn, with "
              "the part you zoomed or panned to in orange. It works when a single plot is visible, and not while "
              "streaming. Its button is next to Statistics, above the plots."),
    SEARCH: ("Search Vars, above the table, lists the variables of each data source so you can tick and add them. "
             "I can look for them too: tell me a system such as CRYO, or part of a name."),
}


@dataclass(frozen=True)
class Asked:
    feature: str
    how: str  # OPEN, CLOSE or ABOUT


def asked(text: str) -> Optional[Asked]:
    """The tool the request is about and whether to open it, close it or say what it is; None if it names none."""
    text = text or ""
    found = [key for key, pattern in NAMES.items() if pattern.search(text)]
    if len(found) != 1:
        return None
    feature = found[0]
    if CLOSING.search(text):
        # Statistics is a window of its own, closed from there.
        return Asked(feature, CLOSE) if feature == MINIMAP else None
    if OPENING.search(text):
        return Asked(feature, OPEN)
    if ASKING.search(text):
        return Asked(feature, ABOUT)
    # The name alone ("the statistics", "mini-map please") asks for it; anything longer is another request.
    rest = NAMES[feature].sub(" ", text)
    return Asked(feature, OPEN) if len(re.findall(r"\w+", rest)) <= 3 else None
