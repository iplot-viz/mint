"""What MINT reads in a request by itself, to complete or question the model's answer."""
import re
from typing import List, Optional

from mint.assistant import prompt
from mint.assistant.commands import Command
from mint.assistant.snapshot import Snapshot

# Place words, in the languages the assistant understands.
TOP = {"top", "upper", "arriba", "superior", "superiores", "haut", "oben", "obere", "oberen", "sopra", "superiore",
       "superiori", "cima"}
BOTTOM = {"bottom", "lower", "abajo", "inferior", "inferiores", "bas", "unten", "untere", "unteren", "sotto",
          "inferiore", "inferiori", "baixo"}
LEFT = {"left", "izquierda", "izquierdo", "gauche", "links", "linke", "linken", "sinistra", "sinistro", "esquerda",
        "esquerdo"}
RIGHT = {"right", "derecha", "derecho", "droite", "rechts", "rechte", "rechten", "destra", "destro", "direita",
         "direito"}
PLACES = TOP | BOTTOM | LEFT | RIGHT
TWO = {"two", "dos", "deux", "zwei", "due", "dois", "duas"}
SEVERAL = TWO | {"both", "plots", "ambos", "ambas", "gráficos", "graficos", "gráficas", "graficas", "graphiques",
                 "beide", "beiden", "diagramme", "entrambi", "entrambe", "grafici"}
# How many plots a place holds is said within a few words of it: "both top plots".
NEAR = 3
WITH = re.compile(r"\b(?:with|next to|beside|junto a|junto con|junto de|con|avec|à côté de|mit|neben|insieme a|"
                  r"accanto a|com|ao lado de)\b", re.IGNORECASE)
# Letters, then a digit ("TF07", "MP0071"), but not a function such as log10.
CODE = re.compile(r"[A-Za-z]{2,}\D*\d")
NOT_A_CODE = re.compile(r"log\d+", re.IGNORECASE)
# "It", "this"... as pronouns, in the languages the assistant understands.
IT = re.compile(r"\b(?:(?:this|that) one|it|this|that|these|those|esto|eso|ça|cela|ceci|dies|questo|quello|isso|isto)\b",
                re.IGNORECASE)
ARTICLE = re.compile(r"^(?:the|el|la|los|las|le|les|der|die|das|den|il|lo|gli|o|os|as)\s+", re.IGNORECASE)
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "due": 2,
           "tre": 3, "quattro": 4, "cinque": 5, "dois": 2, "duas": 2, "três": 3, "quatro": 4}
# "2 signals", "two pressure signals", "dos señales".
COUNT = re.compile(r"\b(\d{1,2}|" + "|".join(NUMBERS) + r")\s+(?:\w+\s+)?(?:signals?|variables?|señal(?:es)?|"
                   r"signaux|signale?|segnali|segnale|variablen|variabili|sinais|sinal|variáveis|variável)\b",
                   re.IGNORECASE)


def places(snap: Snapshot, request: str) -> List[str]:
    """The plots the request points at by where they are on screen, or [] if it does not, or not clearly."""
    words = re.findall(r"\w+", (request or "").lower())
    marks = [i for i, word in enumerate(words) if word in PLACES]
    said = {words[i] for i in marks}
    vertical = [end for side, end in ((TOP, 0), (BOTTOM, -1)) if said & side]
    horizontal = [end for side, end in ((LEFT, 0), (RIGHT, -1)) if said & side]
    if not snap.plots or not marks or len(vertical) > 1 or len(horizontal) > 1:
        return []
    near = {words[j] for i in marks for j in range(max(0, i - NEAR), i + NEAR + 1) if j < len(words)}
    rows = sorted({p.row for p in snap.plots})
    cols = sorted({p.col for p in snap.plots})
    if len(cols) == 1 and vertical and near & TWO:  # "the top two plots" in a single column
        line = sorted(snap.plots, key=lambda p: p.row)
        hits = line[:2] if vertical[0] == 0 else line[-2:]
    else:
        hits = [p for p in snap.plots if (not vertical or p.row == rows[vertical[0]])
                and (not horizontal or p.col == cols[horizontal[0]])]
    # One plot for "the top plot", several for "both top plots": anything else is not clear.
    return [p.id for p in hits] if (len(hits) > 1) == bool(near & SEVERAL) else []


def _partners(snap: Snapshot, request: str):
    """In "put A with B", the rows only B names and the words for B, or None."""
    m = WITH.search(request or "")
    if not m:
        return None
    # To the end of the sentence: the answer to the question review() asks comes after it.
    after = re.split(r"[.?!](?:\s|$)", request[m.end():])[0]
    rows = {row.id for row, _ in prompt.named(snap, after)} - \
        {row.id for row, _ in prompt.named(snap, request[:m.start()])}
    return (rows, prompt.clean(after.strip(), 60)) if rows else None


def review(snap: Snapshot, request: str, cmds: List[Command]) -> List[Command]:
    """The model's commands, completed where the request is plain about what they leave out.

    A command moving the rows that others should join becomes a question.
    """
    hits = places(snap, request)
    for cmd in cmds:
        if cmd.verb == "plot" and set(cmd.ids) < set(hits):
            cmd.ids = list(hits)
    partners = _partners(snap, request) if any(c.verb == "move" for c in cmds) else None
    if partners and any(c.verb == "move" and set(c.ids) <= partners[0] for c in cmds):
        return [Command("ask", text=f"Sure, which signal should go with {partners[1]}?")]
    return cmds


def chosen(snap: Snapshot, request: str, answer: str) -> List[str]:
    """The rows an answer to "which one?" names, when the request named none.

    Empty when the answer names no row, or a signal and copies of it without saying which.
    """
    if prompt.named(snap, request):
        return []
    said = ARTICLE.sub("", answer.strip(" .!?").lower())
    exact = [row for row in snap.rows + snap.unlisted
             if said in {name.lower() for name in (row.alias, row.variable, row.variable.split(":")[-1]) if name}]
    if len(exact) == 1:  # "the pirani" is the pirani, not also its copy pirani_avg_2s
        return [exact[0].id]
    rows = [row for row, _ in prompt.named(snap, answer, meanings=False)]
    if len(rows) == 1 or (0 < len(rows) <= prompt.MAX_LOOSE and not any(row.derived for row in rows)):
        return [row.id for row in rows]
    return []


def in_place_of_it(request: str, answer: str) -> Optional[str]:
    """The request with the signal named in reply in place of its "it": "smooth it" -> "smooth the pirani"."""
    return IT.sub(answer.strip(" .!?"), request, count=1) if IT.search(request) else None


def selection_for_it(snap: Snapshot, request: str, cmds: List[Command]) -> Optional[str]:
    """The request with the selected rows in place of its "this", when the model asks which signal anyway."""
    if len(cmds) != 1 or cmds[0].verb != "ask" or "which" not in cmds[0].text.lower():
        return None
    rows = [snap.row(row_id) for row_id in snap.selected]
    names = [row.alias or row.variable for row in rows if row is not None]
    it = IT.search(request)
    # "It" with two rows selected is still a question; "these" needs more than one.
    if not names or not it or (len(names) > 1) != (it.group(0).lower() in ("these", "those")):
        return None
    return in_place_of_it(request, " and ".join(names))


def unknown_codes(snap: Snapshot, request: str) -> List[str]:
    """Codes in the request that no row has in its name ("need TF07 coil current"): signals to look for."""
    names = [name.lower() for row in snap.rows + snap.unlisted for name in (row.alias, row.variable)]
    found = {}
    for token in prompt.TOKEN.findall(request or ""):
        if CODE.match(token) and not NOT_A_CODE.fullmatch(token) and not any(token.lower() in n for n in names):
            found.setdefault(token.lower(), token)
    return list(found.values())


def wanted(request: str) -> Optional[int]:
    """How many signals the request asks for ("a workspace with 2 signals"), when it says."""
    match = COUNT.search(request or "")
    if match is None:
        return None
    number = match.group(1).lower()
    return (int(number) if number.isdigit() else NUMBERS[number]) or None
