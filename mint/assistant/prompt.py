"""What the model reads: fixed instructions and examples, then the workspace, then the request."""
import re
from dataclasses import replace
from typing import List, Optional, Tuple

from mint.assistant.snapshot import RowInfo, Snapshot

SYSTEM = """You are the assistant of MINT, a tool to plot and process ITER plant signals. Turn the user's request into commands for their workspace: one command for each thing the user asks, one per line, never the same command twice, and nothing else.

The workspace lists the rows r1, r2... of the signals table (the plot that shows it, then its "alias", or its variable name when it has no alias) and where each plot is on the screen.

Commands:
process ROWS RECIPE [replace] - adds a processed copy of each row to its plot. Add replace only when the user wants the original changed (replace, overwrite, instead of).
  moving_average, gaussian, savgol or median [window=N with unit ms, s, min, h or d]: smoothing over that window; median also removes spikes.
  lowpass hz=N: keeps what changes slower than N Hz.
  derivative, integral, abs, log10, scale factor=N [offset=N].
  relative_time: time axis in seconds from the first point.
combine subtract|add|multiply|divide ROW_A ROW_B - a new signal A-B, A+B, A*B or A/B.
plot PLOTS|all [log=on|off] [grid=on|off] [legend=on|off] [title="..."] - how plots look. log=on is a logarithmic axis.
find WORDS - searches variables to add, by words of their name.
range last N seconds|minutes|hours|days | range day today|yesterday|YYYY-MM-DD | range month YYYY-MM | range from "YYYY-MM-DD HH:MM" to "YYYY-MM-DD HH:MM" | range pulse ID - the time range to plot, in UTC.
move ROWS to PLOT|new - shows rows in another plot. remove ROWS. draw.
ask "QUESTION" - when you cannot tell which row or plot the user means.
say "SENTENCE" - for anything else: greetings, questions, things these commands cannot do.

Rules:
- Use only ids from the workspace. "This", "it" or "these" mean the selected rows; if none is selected, ask which.
- "Names in the request" tells you which rows the user's words point to.
- Leave out any number the user did not give (window, hz, factor): MINT picks a window or asks.
- Write ask and say in English, like the rest of MINT, also when the request is in another language. Keep them short and warm, like a colleague in the control room. Call signals by their names and plots by where they are (the top plot), never r1 or p1.
- "The same for X" repeats the Last applied commands on X.
- No say next to a change: MINT shows the change itself."""

SYSTEM_TRAINED = ("You are the assistant of MINT. Turn the user's request into MINT commands for their workspace, "
                  "or ask or say something short and warm in English.")

# (workspace text or None to keep the previous one, request, answer)
EXAMPLES: List[Tuple[Optional[str], str, str]] = [
    ("Today 2026-10-04 (UTC). Time range: last 2 hours.\n"
     "r1 in p1: \"T_inlet\"\n"
     "r2 in p1: \"T_outlet\"\n"
     "r3 in p2: CRYO-CP-03:MP0015-XI\n"
     "r4 in p3: \"I_TF07\"\n"
     "Plots from top to bottom: p1, p2, p3.\n"
     "Selected: r4",
     "smooth the inlet temperature over 30 s", "process r1 moving_average window=30s"),
    (None, "put the pressure plot in log scale", "plot p2 log=on"),
    (None, "filter this one, keep what is slower than 2 Hz", "process r4 lowpass hz=2"),
    (None, "outlet minus inlet", "combine subtract r2 r1"),
    (None, "remove the spikes of MP0015 and overwrite it\nNames in the request: r3 = MP0015",
     "process r3 median replace"),
    (None, "show me the last 6 hours and redraw", "range last 6 hours\ndraw"),
    (None, "yesterday", "range day yesterday"),
    (None, "low-pass it", "process r4 lowpass"),
    (None, "x axis from zero in the bottom plot", "process r4 relative_time"),
    ("Today 2026-11-02 (UTC). Time range: pulse ITER:MCTB_PSS-TF07_FD/11.\n"
     "r1 in p1: \"pirani\"\n"
     "r2 in p1: VAC-TKM-PPC-CP-VI:MP0071-PTCP00-XI\n"
     "r3 in p2: CWS-SCSU-HR00:MF0010-FT-XI\n"
     "Plots: p1 left, p2 right.\n"
     "Selected: none",
     "rate of change of the pirani, and a log axis on its plot\nNames in the request: r1 = pirani",
     "process r1 derivative\nplot p1 log=on"),
    (None, "smooth that", "ask \"Sure, which one: the pirani, MP0071 or the flow?\""),
    (None, "put the flow with the pressures", "move r3 to p1"),
    (None, "add the TF07 coil current", "find TF07 current"),
    (None, "MF0010 in m3/h please, it is in l/s\nNames in the request: r3 = MF0010", "process r3 scale factor=3.6"),
    (None, "no grid on the right plot", "plot p2 grid=off"),
    (None, "log on both plots", "plot p1 p2 log=on"),
    (None, "average the flow over a quarter of an hour", "process r3 moving_average window=15min"),
    (None, "du 3 novembre 8h au 4 novembre 20h", "range from \"2026-11-03 08:00\" to \"2026-11-04 20:00\""),
    (None, "show pulse ITER:MCTB_PSS-TF07_FD/12 instead", "range pulse ITER:MCTB_PSS-TF07_FD/12"),
    (None, "export this to excel", "say \"I can't export myself, but the Export button next to Draw will.\""),
    (None, "hello! what can you do?",
     "say \"Hi! I can smooth or filter signals, combine them, change the plots, add variables and set the time "
     "range. What do you need?\""),
    (None, "perfecto, gracias!", "say \"You're welcome!\""),
]

STOPWORDS = {"the", "and", "for", "plot", "plots", "signal", "signals", "all", "with", "from", "this", "that",
             "these", "row", "rows", "time", "data", "last", "show", "put", "make", "into", "over", "please"}
TOKEN = re.compile(r"[A-Za-z0-9_]+(?:[-:.][A-Za-z0-9_]+)*")
CODE_LIKE = re.compile(r"[0-9_:]")
# Words of a name: "T_inlet" and "flow-he" are two words each, as people say them.
WORD = re.compile(r"[a-z0-9]+")
# The letters a code starts with, before its digits: "mlt" in "mlt1000".
CODE_LETTERS = re.compile(r"([a-z]+)\d")
# A name written in the request must not be glued to more letters or to more of a code:
# "pirani" is not in "piranis", "PIR-1101" is not in "PIR-1101-XI", but a final dot is fine.
NAME_START = r"(?<!\w)(?<!\w[-:.])"
NAME_END = r"(?!\w)(?![-:.]\w)"
MAX_LOOSE = 4
MAX_ROWS = 50
# Token budget of the listed rows: evaluated when a workspace opens and, from the first changed row on, after each edit.
ROW_BUDGET = 400
FEW_PLOTS = 6
MAX_TEXT = 100
# What a signal measures, read from its ITER code (MT0021 is a temperature sensor) or the
# transmitter in the name (-TT, -PT...), so "the temperature" also points at rows shown by alias.
MEASURES = {
    "temperature": ("MT", "TT", {"temp", "temperature", "temperatures"},
                    {"temperature", "temperatures", "temp", "température", "températures", "temperatura",
                     "temperaturas", "temperatur", "temperaturen"}),
    "pressure": ("MP", "PT", {"pressure", "press", "pirani", "penning"},
                 {"pressure", "pressures", "pression", "pressions", "presión", "presion", "presiones", "pressione",
                  "pressioni", "pressão", "pressao", "pressões", "druck", "drücke"}),
    "flow": ("MF", "FT", {"flow"},
             {"flow", "flows", "débit", "debit", "débits", "caudal", "caudales", "flujo", "portata", "portate",
              "vazão", "vazao", "durchfluss", "durchfluß"}),
    "level": ("ML", "LT", {"level"},
              {"level", "levels", "niveau", "niveaux", "nivel", "niveles", "livello", "livelli", "nível", "níveis",
               "füllstand", "pegel"}),
}
SAID = {word: meaning for meaning, (_, _, _, words) in MEASURES.items() for word in words}
# Words that point back at the change just applied ("the same for MP0071"). Only then is it shown:
# a small model shown it on every request repeats it.
BACK = re.compile(r"\b(?:same|again|too|also|as well|likewise|repeat|now|try|mism[oa]s?|igual|tambi[eé]n|otra vez|"
                  r"de nuevo|repite|ahora|m[eê]mes?|pareil|aussi|encore|refais|maintenant|gleiche[nrs]?|dasselbe|"
                  r"selbe|auch|nochmal|noch mal|wieder|jetzt|ebenso|stess[oaie]|anche|ancora|di nuovo|adesso|"
                  r"mesm[oa]s?|tamb[eé]m|de novo|agora|repete|outra vez)\b", re.IGNORECASE)
CONTROL = re.compile("[\x00-\x1f\x7f\u0085  ]+")


def clean(text: str, limit: int = MAX_TEXT) -> str:
    """Text from the table or the user, made inert for the prompt.

    Chat markers such as <|im_end|> would be read as real turn boundaries, and line breaks could fake a workspace line.
    """
    text = CONTROL.sub(" ", str(text or ""))
    text = text.replace("<|", "< |").replace("|>", "| >").replace("<think>", "<think >").replace("</think>",
                                                                                             "</think >")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def estimate_tokens(text: str) -> int:
    """Rough token count of the text: one per digit or symbol, one per 4 letters.

    The real tokenizer lives in the model process; a round trip per table edit is not worth it.
    """
    letters = sum(-(-len(w) // 4) for w in re.findall(r"[A-Za-z]+", text))
    return letters + sum(ch.isdigit() or not (ch.isalpha() or ch.isspace()) for ch in text)


def visible(snap: Snapshot) -> Snapshot:
    """Rows shown to the model: the selected ones first, then table order, within ROW_BUDGET and MAX_ROWS.

    Rows left out stay in ``unlisted``, still reachable by name (see answer_ids).
    """
    keep, spent = set(), 0
    for row in [r for r in snap.rows if r.id in snap.selected] + [r for r in snap.rows if r.id not in snap.selected]:
        cost = estimate_tokens(_row_line(row))
        if len(keep) == MAX_ROWS or (keep and spent + cost > ROW_BUDGET):
            break
        keep.add(row.id)
        spent += cost
    if len(keep) == len(snap.rows):
        return snap
    return replace(snap, rows=[r for r in snap.rows if r.id in keep], selected=[s for s in snap.selected if s in keep],
                   unlisted=[r for r in snap.rows if r.id not in keep])


def _positions(snap: Snapshot) -> str:
    if not snap.plots:
        return ""
    rows = sorted({p.row for p in snap.plots})
    cols = sorted({p.col for p in snap.plots})
    first, last = snap.plots[0].id, snap.plots[-1].id
    if len(snap.plots) > FEW_PLOTS and len(snap.plots) == len(rows) * len(cols):
        # Many plots filling a grid: plots are numbered in reading order, so saying the grid
        # places every one of them in a few tokens instead of naming each (40 plots: 342 -> 26 tokens).
        if len(cols) == 1:
            return f"Plots from top to bottom: {first} to {last}."
        if len(rows) == 1:
            return f"Plots from left to right: {first} to {last}."
        return f"Plots: {first} to {last}, in {len(rows)} rows of {len(cols)}, numbered left to right, then down."
    if len(cols) == 1:
        return "Plots from top to bottom: " + ", ".join(p.id for p in snap.plots) + "."

    def word(value, values, first, last):
        if len(values) == 1:
            return ""
        if value == values[0]:
            return first
        if value == values[-1]:
            return last
        return f"{'row' if first == 'top' else 'column'} {values.index(value) + 1}"

    places = []
    for p in snap.plots:
        place = " ".join(w for w in (word(p.row, rows, "top", "bottom"), word(p.col, cols, "left", "right")) if w)
        places.append(f"{p.id} {place}".strip())
    return "Plots: " + ", ".join(places) + "."


def _row_line(row: RowInfo) -> str:
    # The alias alone when there is one: MINT keeps aliases unique, and variable codes cost
    # about one token per character. A request naming the variable still finds the row.
    name = f"\"{clean(row.alias, 48)}\"" if row.alias else clean(row.variable)
    text = f"{row.id} {'in ' + row.plot if row.plot else 'not plotted'}: {name}"
    return text + (" (processed)" if row.y or row.x else "")


def render_workspace(snap: Snapshot) -> str:
    # The date and not the time: this text must stay the same until the table changes, to be
    # evaluated ahead, and dates are all a range needs ("yesterday", "8 to 9:30 this morning").
    lines = [f"Today {snap.now.strftime('%Y-%m-%d')} (UTC). Time range: {clean(snap.range_text) or 'not set'}."]
    lines += [_row_line(row) for row in snap.rows]
    if snap.hidden_rows:
        lines.append(f"({snap.hidden_rows} more rows are not listed; select rows to talk about them.)")
    positions = _positions(snap)
    if positions:
        lines.append(positions)
    for plot in snap.plots:
        notes = []
        if plot.log_scale:
            notes.append("log scale")
        if plot.title:
            notes.append(f"title \"{clean(plot.title, 48)}\"")
        if notes:
            lines.append(f"{plot.id}: {', '.join(notes)}")
    if not snap.rows:
        lines.append("The table is empty.")
    lines.append("Selected: " + (" ".join(snap.selected) if snap.selected else "none"))
    return "\n".join(lines)


def points_back(request: str) -> bool:
    """Whether the request refers to the change just applied, so the model needs to see it."""
    return bool(BACK.search(request or ""))


def measures(row: RowInfo) -> Optional[str]:
    """What the row's signal measures (temperature, pressure, flow, level), if its code or alias says so."""
    part = row.variable.split(":")[-1].upper() if ":" in row.variable else ""
    alias = set(WORD.findall(row.alias.lower()))
    for meaning, (component, transmitter, alias_words, _) in MEASURES.items():
        if re.match(component + r"\d", part) or re.search(rf"-{transmitter}[A-Z0-9]*(?:-|$)", part) \
                or alias & alias_words:
            return meaning
    return None


def _code_letters(word: str) -> str:
    match = CODE_LETTERS.match(word)
    return match.group(1) if match else ""


def _contains(words: List[str], part: List[str]) -> bool:
    return bool(part) and any(words[i:i + len(part)] == part for i in range(len(words) - len(part) + 1))


def named(snap: Snapshot, request: str, meanings: bool = True) -> List[Tuple[RowInfo, List[str]]]:
    """Rows, listed or not, that the request names, with the words that name them.

    Longest match first; a word that fits more than MAX_LOOSE rows is too vague and points at none.
    """
    request = request or ""
    text = request.lower()
    rows = snap.rows + snap.unlisted
    names = {row.id: {n.lower() for n in (row.alias, row.variable, row.variable.split(":")[-1])
                      if len(n) >= 3 and n.lower() not in STOPWORDS} for row in rows}
    found, taken = {}, []

    def point(row, words):
        entry = found.setdefault(row.id, (row, []))[1]
        if words not in entry:
            entry.append(words)

    words_of = {row.id: [WORD.findall(n) for n in names[row.id]] for row in rows}
    for name, row in sorted(((n, r) for r in rows for n in names[r.id]), key=lambda pair: -len(pair[0])):
        for m in re.finditer(NAME_START + re.escape(name) + NAME_END, text):
            span = m.span()
            # Inside a longer name already found ("pirani" in "CP01 pirani"): that one is meant.
            if any(s < span[1] and span[0] < e and (s, e) != span for s, e in taken):
                continue
            if span not in taken:
                taken.append(span)
            point(row, request[span[0]:span[1]])
            # Processed copies carry the name inside theirs ("pirani_avg_2s"): "the smoothed
            # pirani" may mean one of them, so they are pointed at too, unless too many do.
            target = WORD.findall(name)
            copies = [other for other in rows if other.id != row.id and other.derived
                      and any(_contains(words, target) for words in words_of[other.id])]
            for other in copies if len(copies) <= MAX_LOOSE else []:
                point(other, request[span[0]:span[1]])
    for m in TOKEN.finditer(request):
        token, low = m.group(), m.group().lower()
        if len(low) < 3 or low in STOPWORDS or any(s < m.end() and m.start() < e for s, e in taken):
            continue
        hits = [r for r in rows if any(low in WORD.findall(n) for n in names[r.id])]
        if not hits and len(low) >= 4 and CODE_LIKE.search(low):
            hits = [r for r in rows if any(low in n for n in names[r.id])]
        if not hits and low.isalpha():
            # The letters of a code, as people shorten it ("mlt" for MLT1000): the signal before its copies.
            hits = [r for r in rows if any(_code_letters(w) == low for n in names[r.id] for w in WORD.findall(n))]
            hits = [r for r in hits if not r.derived] or hits
        if len(hits) <= MAX_LOOSE:
            for row in hits:
                point(row, token)
    # Last, what the signals measure. Not when the word only describes a row already named,
    # nor for processed copies, which carry the code of their original.
    for m in re.finditer(r"\w+", request) if meanings else ():
        meaning = SAID.get(m.group().lower())
        if not meaning or any(s < m.end() and m.start() < e for s, e in taken):
            continue
        hits = [r for r in rows if measures(r) == meaning and not r.derived]
        if len(hits) <= MAX_LOOSE and not any(r.id in found for r in hits):
            for row in hits:
                point(row, m.group())
    return list(found.values())[:8]


def mentions(snap: Snapshot, request: str) -> str:
    """Rows whose alias or variable name the request names, e.g. 'r2 = LA2_D'.

    Plain matching finds codes a small model misses, also in rows a big table leaves out of the listing.
    """
    parts = [f"{row.id} = {' '.join(words)} ({'in ' + row.plot if row.plot else 'not plotted'})"
             for row, words in named(snap, request)]
    return clean(", ".join(parts), 240)


def answer_ids(snap: Snapshot, request: str) -> Tuple[List[str], List[str]]:
    """Row and plot ids the answer may use: the listed ones plus those of unlisted rows the request names."""
    rows = [r.id for r in snap.rows]
    plots = [p.id for p in snap.plots]
    # The same text build() reads, so the grammar allows exactly the rows the hint names.
    for row, _ in named(snap, clean(request, 600)):
        if row.id not in rows:
            rows.append(row.id)
            if row.plot and row.plot not in plots:
                plots.append(row.plot)
    return rows, plots


def _workspace_part(workspace: str) -> str:
    return f"Workspace:\n{workspace}\n\n"


def _request_part(request: str, hints: str = "") -> str:
    return f"Request: {request}" + (f"\nNames in the request: {hints}" if hints else "")


# ChatML is written here, not read from the model file, so the file cannot run template code.
# Qwen3's own template writes an empty thought when thinking is off.
FORMATS = {
    "chatml": "",
    "qwen3-nothink": "<think>\n\n</think>\n\n",
}


class ChatFormat:
    """Turns (role, text) messages into the exact text the model was trained on."""

    def __init__(self, name: str):
        if name not in FORMATS:
            raise ValueError(f"unsupported chat format {name!r}")
        self.name = name
        self._opening = FORMATS[name]

    @staticmethod
    def turn(role: str, text: str) -> str:
        return f"<|im_start|>{role}\n{text}<|im_end|>\n"

    @staticmethod
    def user_opening() -> str:
        return "<|im_start|>user\n"

    def open_assistant(self) -> str:
        return "<|im_start|>assistant\n" + self._opening


def fixed_prefix(fmt: ChatFormat, few_shot: bool = True) -> str:
    """Instructions and worked examples for a general model; one system line for a model trained for MINT."""
    if not few_shot:
        return fmt.turn("system", SYSTEM_TRAINED)
    text = fmt.turn("system", SYSTEM)
    for workspace, request, answer in EXAMPLES:
        user = (_workspace_part(workspace) if workspace else "") + _request_part(request)
        text += fmt.turn("user", user)
        text += fmt.turn("assistant", answer)
    return text


def build(fmt: ChatFormat, snap: Snapshot, request: str, few_shot: bool = True) -> Tuple[str, str]:
    """(prefix that can be evaluated before the request is known, full prompt)."""
    head = fixed_prefix(fmt, few_shot)
    workspace = render_workspace(snap)
    request = clean(request, 600)
    warm = head + fmt.user_opening() + _workspace_part(workspace) + "Request:"
    if snap.last_action and points_back(request):
        # After the part evaluated ahead, since only the request tells whether it is needed.
        workspace += f"\nLast applied: {clean(snap.last_action, 300)}"
    full = head + fmt.turn("user", _workspace_part(workspace) + _request_part(request, mentions(snap, request))) + \
        fmt.open_assistant()
    return warm, full
