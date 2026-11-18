"""Questions about the data drawn, answered from the samples MINT read: the last value, the extremes, the mean, how
many samples. The model never sees the values, so these never reach it."""
import re
from typing import List

LAST, FIRST, MAX, MIN, MEAN, COUNT, UNIT = "last", "first", "max", "min", "mean", "count", "unit"
ORDER = (UNIT, LAST, FIRST, MAX, MIN, MEAN, COUNT)
_THING = r"(?:values?|samples?|points?|readings?|data)"
WHAT = {
    LAST: re.compile(rf"\b(?:last|latest|newest|most recent|current|final)\s+{_THING}\b|\bvalues? (?:right )?now\b|"
                     r"\bwhen (?:is|was) the last\b", re.IGNORECASE),
    FIRST: re.compile(rf"\bfirst\s+{_THING}\b", re.IGNORECASE),
    MAX: re.compile(r"\b(?:max(?:imum|ima)?|peak|highest|largest|biggest)\b", re.IGNORECASE),
    # Not "30 min", a window.
    MIN: re.compile(r"(?<![\d.])(?<!\d )\b(?:min(?:imum|ima)?|lowest|smallest)\b", re.IGNORECASE),
    # Not "moving average" nor "average it over 30 s": those are processing; nor "what do you mean?".
    MEAN: re.compile(r"(?<!moving )(?<!rolling )(?<!running )(?<!you )(?<!i )(?<!does )(?<!do )(?<!it )"
                     r"\b(?:mean|average|avg)\b(?!.*\bover\b)", re.IGNORECASE),
    COUNT: re.compile(r"\b(?:how many|number of|count of)\s+(?:samples|points|values|data points)\b", re.IGNORECASE),
    # "The unit of the variable" ("unitof" too), "what unit is it in": not "what units does the export use".
    UNIT: re.compile(r"\bunits?\s*(?:of|for)\b|\bwhat\s+units?\s+(?:is|are)\b|\bmeasured in\b", re.IGNORECASE),
}
# A question, not a request to do something: "what's the max of X?", "tell me the last values".
QUESTION = re.compile(r"\?|^\s*(?:what|which|how|when|is|are|tell|give me|do we)\b|"
                      r"\b(?:want to know|need to know|tell me|wondering)\b", re.IGNORECASE)
# All the rows drawn, rather than those named: "each of them", "every signal", "per signal".
EVERY = re.compile(r"\b(?:each|every|all|per|them|these|those)\b", re.IGNORECASE)
MAX_ROWS = 8


def asked(text: str) -> List[str]:
    """What the question asks of the data drawn (LAST, MAX...), in a fixed order; [] if it isn't such a question."""
    text = text or ""
    if not QUESTION.search(text):
        return []
    return [what for what in ORDER if WHAT[what].search(text)]


def for_every_row(text: str) -> bool:
    return bool(EVERY.search(text or ""))
