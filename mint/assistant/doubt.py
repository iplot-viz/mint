"""How sure the model was of each row and plot it named, from its token probabilities."""
import math
import re
from typing import Dict, List, Optional, Tuple

# Below this, a row or plot the model chose is a guess; an alternative above ALTERNATIVE is a real doubt.
SURE = 0.5
ALTERNATIVE = 0.2
TOP = 5


class TokenWatch:
    """A logits processor recording each generated token's log-probability and top alternatives.

    It sees the raw scores, before the grammar masks them, at the cost of one softmax per token.
    """

    def __init__(self, top: int = TOP):
        self.top = top
        self.steps: List[dict] = []
        self._previous = None

    def __call__(self, input_ids, scores):
        import numpy as np
        if self._previous is not None:
            # The token chosen at the previous step is now the last input.
            chosen = int(input_ids[-1])
            self.steps[-1]["token"], self.steps[-1]["lp"] = chosen, float(self._previous[chosen])
        peak = float(np.max(scores))
        logp = scores - (peak + math.log(float(np.sum(np.exp(scores - peak)))))
        best = np.argpartition(-logp, self.top)[:self.top]
        self.steps.append({"alts": {int(i): float(logp[i]) for i in best}})
        self._previous = logp
        return scores

    def ids(self, detokenize) -> List[dict]:
        """Each row or plot id the answer wrote, with its probability and the ids it was weighed against."""
        steps = [s for s in self.steps if "token" in s]
        pieces = [detokenize(s["token"]) for s in steps]
        found, text, i = [], "", 0
        while i < len(steps):
            letter = re.search(r"(?:^|[\s])([rp])$", text)
            if letter and pieces[i].isdigit():
                start, digits, lp = i, "", 0.0
                while i < len(steps) and pieces[i].isdigit():
                    digits += pieces[i]
                    lp += steps[i]["lp"]
                    text += pieces[i]
                    i += 1
                alts = {}
                for pos in {start, i - 1}:
                    before = digits[:pos - start]
                    for token, alt_lp in steps[pos]["alts"].items():
                        piece = detokenize(token)
                        if not piece.isdigit() or piece == digits[pos - start]:
                            continue
                        # "r3" weighed against "r4", "r12" against "r13"; at the first digit of "r12",
                        # a "3" may start "r3" or "r32".
                        endings = {""} | ({digits[1:]} if pos == start and pos != i - 1 else set())
                        for ending in endings:
                            alt = letter.group(1) + before + piece + ending
                            alts[alt] = max(alts.get(alt, 0.0), math.exp(alt_lp))
                found.append({"id": letter.group(1) + digits, "p": math.exp(lp), "alts": alts})
                continue
            text += pieces[i]
            i += 1
        return found


def doubtful(ids: List[dict], valid: set) -> Optional[Tuple[str, str]]:
    """The first id the model hesitated on, and the valid id it hesitated with, if any."""
    for entry in ids or []:
        alts: Dict[str, float] = {a: p for a, p in entry.get("alts", {}).items() if a in valid and a != entry["id"]}
        if entry["id"] in valid and entry["p"] < SURE and alts:
            alt, p = max(alts.items(), key=lambda item: item[1])
            if p >= ALTERNATIVE:
                return entry["id"], alt
    return None
