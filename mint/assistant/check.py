"""What MINT reads in a request by itself, to complete or question the model's answer."""
import re
from typing import List, Optional

from mint.assistant import commands, diagnose, prompt
from mint.assistant.commands import Command
from mint.assistant.snapshot import Snapshot

# Place words.
TOP = {"top", "upper"}
BOTTOM = {"bottom", "lower"}
LEFT = {"left"}
RIGHT = {"right"}
PLACES = TOP | BOTTOM | LEFT | RIGHT
TWO = {"two"}
SEVERAL = TWO | {"both", "plots"}
# How many plots a place holds is said within a few words of it: "both top plots".
NEAR = 3
WITH = re.compile(r"\b(?:with|next to|beside)\b", re.IGNORECASE)
# Merging plots, and the words that say where to: "merge the first plot into the second" keeps its way round,
# "merge them into one" says nothing of which.
MERGING = re.compile(r"\b(?:merge|join|combine|unify|unite|combin\w*)\b", re.IGNORECASE)
TOWARDS = re.compile(r"\b(?:into|onto|to|in|inside|on)\b", re.IGNORECASE)
INTO_ONE = re.compile(TOWARDS.pattern + r"\s+(?:a\s+)?(?:one|single)\b", re.IGNORECASE)
ALL = re.compile(r"\b(?:all|every|everything)\b", re.IGNORECASE)
# "Merge the first two plots": without the word for plots, "combine A and B" may be arithmetic.
OF_PLOTS = re.compile(r"\b(?:plots?|graphs?|both)\b", re.IGNORECASE)
FIRST_TWO = re.compile(r"\b(?:first|1st)\s+two\b|\bplots?\s+(?:1|one)\s+and\s+(?:2|two)\b", re.IGNORECASE)
# "Zoom on the last 10 minutes": the end of what is drawn, not a new time range, which would read other data.
LAST_SPAN = re.compile(r"\b(?:last|final)\s+(?:(\d+(?:\.\d+)?)\s*|(an?|one|two|three|four|five|six|ten|fifteen|twenty|"
                       r"thirty)\s+)?(ms|milliseconds?|s|secs?|seconds?|mins?|minutes?|h|hrs?|hours?)\b",
                       re.IGNORECASE)
SPELLED = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10, "fifteen": 15,
           "twenty": 20, "thirty": 30}
ZOOMING = re.compile(r"\b(?:zoom\w*|blow\w*\s+up|magnif\w*|enlarge|close[\s-]?up)\b", re.IGNORECASE)
LOADING = re.compile(r"\b(?:load\w*|fetch\w*|read|reload|range|redraw|refresh)\b", re.IGNORECASE)
VIEWING = {"zoom", "pan", "home", "range", "draw"}
# What to ask for a title or label the request doesn't write.
TEXT_QUESTIONS = {"title": "What should the title be?", "label": "What name should it have in the legend?",
                  "ylabel": "What should the y axis label say?"}
# Letters, then a digit ("TF07", "MP0071"), but not a function such as log10.
CODE = re.compile(r"[A-Za-z]{2,}\D*\d")
NOT_A_CODE = re.compile(r"log\d+", re.IGNORECASE)
# "It", "this"... as pronouns.
IT = re.compile(r"\b(?:(?:this|that) one|it|this|that|these|those)\b", re.IGNORECASE)
ARTICLE = re.compile(r"^the\s+", re.IGNORECASE)
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
# "2 signals", "two pressure signals".
COUNT = re.compile(r"\b(\d{1,2}|" + "|".join(NUMBERS) + r")\s+(?:\w+\s+)?(?:signals?|variables?)\b", re.IGNORECASE)


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


# The words of each plot switch, typos of them included.
SWITCH_WORDS = {
    "log": re.compile(r"\blog|linear|\blin\b", re.IGNORECASE),
    "grid": re.compile(r"grid", re.IGNORECASE),
    "legend": re.compile(r"legen", re.IGNORECASE),
    "marker": re.compile(r"\bmar[kcq]\w*|\bpoints?\b|\bdots?\b|\bsamples?\b|\bmeasurements?\b", re.IGNORECASE),
}


# "Disable" a signal is hiding it from the plot, as its legend entry does, not taking it out of the table.
HIDING = re.compile(r"\b(?:disable|hide|turn off|switch off|deactivate)\b", re.IGNORECASE)
# "Hide the legend" hides a switch of the plot, not a signal.
HIDING_A_SWITCH = re.compile(HIDING.pattern + r"\s+(?:\S+\s+){0,2}?(?:" +
                             "|".join(words.pattern for words in SWITCH_WORDS.values()) + ")", re.IGNORECASE)
# Text written to steer the assistant itself ("ignore all previous instructions and..."): whatever follows is no
# request about the workspace.
STEERING = re.compile(r"\b(?:ignore|disregard|forget)\b.{0,30}\b(?:instructions?|rules|prompt)\b|\bsystem prompt\b|"
                      r"\bdeveloper mode\b|\bjailbreak", re.IGNORECASE)
REMOVING = re.compile(r"\b(?:remove|delete|erase|drop|take out|table|eliminat\w*|cancell\w*|remov\w*|exclu\w*)\b",
                      re.IGNORECASE)


def _source_meant(snap: Snapshot, request: str, cmd: Command) -> str:
    """The data source a "source" command should name: the one the request names, else, for rows whose own isn't
    here any more, the one it most likely became (imaspy -> imas), not whichever the model took."""
    target = cmd.words[0]
    if re.search(rf"(?<![\w-]){re.escape(target)}(?![\w-])", request or "", re.IGNORECASE):
        return target
    gone = {row.data_source for row in snap.rows if row.id in cmd.ids and row.data_source
            and row.data_source not in snap.data_sources}
    fixes = {diagnose.replacement(source, snap.data_sources) for source in gone}
    return fixes.pop() if len(fixes) == 1 and None not in fixes else target


def _bare(name: str) -> str:
    """A variable name without case or separators: "MAG-MCTB-F1-LA14_D" is "MAG-MCTB-F1:LA14_D"."""
    return re.sub(r"[-:._/\s]", "", name).lower()


def _not_in_file(snap: Snapshot, request: str, cmd: Command) -> List[str]:
    """For an "add" of the file's variables, the codes the request names that none of them has, when it names
    no code they have: the user typed a variable the file lacks, and one with a like name must not stand in."""
    if snap.file is None:
        return []
    # The file's own name and its pulses are codes too, but not variables.
    around = _bare(" ".join([snap.file.name, *snap.file.pulses, *snap.file.times]))
    codes = [code for code in unknown_codes(snap, request) if _bare(code) not in around]
    if not codes:
        return []
    added = [_bare(v.name) for v in snap.file.variables if v.id in cmd.ids or "all" in cmd.ids]
    if any(_bare(code) in name for code in codes for name in added):
        return []
    every = [_bare(v.name) for v in snap.file.variables]
    return [code for code in codes if not any(_bare(code) in name for name in every)]


def _made_up(request: str, cmds: List[Command]) -> Optional[str]:
    """The title or label of a command that the request doesn't write, if any: that text is the user's to give."""
    said = re.sub(r"[\W_]", "", request or "").lower()
    for cmd in cmds:
        for key, value in cmd.params.items():
            if key in commands.TEXT_PARAMS and re.sub(r"[\W_]", "", value).lower() not in said:
                return key
    return None


def _undone(cmds: List[Command]) -> List[Command]:
    """The commands without what one of them undoes of an earlier one: a row hidden and then shown again."""
    first = {}
    kept = []
    for cmd in cmds:
        if cmd.verb in ("hide", "show"):
            ids = [row for row in cmd.ids if first.setdefault(row, cmd.verb) == cmd.verb]
            if not ids:
                continue
            if len(ids) < len(cmd.ids):
                cmd = Command(cmd.verb, ids=ids)
        kept.append(cmd)
    return cmds if len(kept) == len(cmds) and all(a is b for a, b in zip(kept, cmds)) else kept


def _all_into(snap: Snapshot, request: str, cmd: Command) -> Command:
    """A move of rows into the plot they are in already, when the request wants all in it: the other rows go."""
    if cmd.verb != "move" or snap.plot(cmd.words[0]) is None or snap.unlisted or not ALL.search(request or ""):
        return cmd
    if any(snap.row(row) is None or snap.row(row).plot != cmd.words[0] for row in cmd.ids):
        return cmd
    others = [row.id for row in snap.rows if row.plot and row.plot != cmd.words[0]]
    return Command("move", ids=others, words=cmd.words) if 0 < len(others) <= commands.MAX_IDS else cmd


def _merge_in_place(snap: Snapshot, request: str, cmd: Command) -> Command:
    """A merge of plots that moves rows into the plot they are in already, which changes nothing: the plots the
    request points at, or the only two, go into the first of them."""
    target = cmd.words[0] if cmd.verb == "move" and cmd.words else None
    if snap.plot(target) is None or not MERGING.search(request or "") or not OF_PLOTS.search(request or ""):
        return cmd
    if any(snap.row(row) is None or snap.row(row).plot != target for row in cmd.ids):
        return cmd
    order = [plot.id for plot in sorted(snap.plots, key=lambda p: (p.row, p.col))]
    named = places(snap, request)
    if len(named) > 1:
        plots = named
    elif FIRST_TWO.search(request):
        plots = order[:2]
    elif len(order) == 2:
        plots = order
    else:
        return cmd
    plots = [plot for plot in order if plot in plots]
    if target not in plots or any(row.plot in plots[1:] for row in snap.unlisted):
        return cmd
    ids = [row.id for row in sorted(snap.rows, key=lambda row: row.index) if row.plot in plots[1:]]
    return Command("move", ids=ids, words=[plots[0]]) if 0 < len(ids) <= commands.MAX_IDS else cmd


def _last_unit(word: str) -> str:
    word = word.lower()
    return "ms" if word == "ms" or word.startswith("milli") else "s" if word.startswith("s") else \
        "min" if word.startswith("m") else "h"


def _zoom_to_the_end(snap: Snapshot, request: str, cmds: List[Command]) -> List[Command]:
    """A zoom on the last minutes of what is drawn, for a request that zooms on them or shows them in a plot."""
    found = LAST_SPAN.search(request or "")
    named = places(snap, request)
    if not found or LOADING.search(request) or not (ZOOMING.search(request) or named):
        return cmds
    number, spelled, unit = found.groups()
    if number is None and spelled is None and len(unit) > 1 and unit.lower().endswith("s"):
        return cmds  # "the last minutes": how many isn't said
    amount = number or str(SPELLED.get((spelled or "a").lower(), 1))
    # The plots the model zoomed, when it did: a place in the request may be for another of its commands. With
    # no plot or signal named, all of them.
    zoomed = next((c.ids for c in cmds if c.verb == "zoom"), None)
    if zoomed and not named and not prompt.named(snap, request):
        zoomed = ["all"]
    ids = zoomed or named or ["all"]
    zoom = Command("zoom", ids=list(ids), words=["last", amount, _last_unit(unit)])
    if all(cmd.verb in ("say", "ask") for cmd in cmds):
        return [zoom]
    at = next((i for i, cmd in enumerate(cmds) if cmd.verb in VIEWING), len(cmds))
    return [cmd for cmd in cmds[:at] if cmd.verb not in VIEWING] + [zoom] + \
        [cmd for cmd in cmds[at:] if cmd.verb not in VIEWING]


def _merging_anyhow(request: str) -> bool:
    """The request merges plots and doesn't say which goes into which."""
    loose = INTO_ONE.sub(" ", request or "")
    return bool(MERGING.search(loose)) and not TOWARDS.search(loose) and not WITH.search(loose)


def _merge_of(snap: Snapshot, cmd: Command):
    """For a move of whole plots into another, the plots it merges, in order, and the rows of each; else None."""
    order = [plot.id for plot in snap.plots]
    if cmd.verb != "move" or cmd.words[0] not in order:
        return None
    members = {}
    for row in sorted(snap.rows + snap.unlisted, key=lambda row: row.index):
        if row.plot:
            members.setdefault(row.plot, []).append(row.id)
    moved = set(cmd.ids)
    emptied = [plot for plot in order if plot != cmd.words[0] and members.get(plot)
               and set(members[plot]) <= moved]
    if not emptied or {row for plot in emptied for row in members[plot]} != moved:
        return None
    return [plot for plot in order if plot in emptied or plot == cmd.words[0]], members


def _merged_into_first(snap: Snapshot, request: str, cmd: Command) -> Command:
    """A merge of whole plots the other way round when it empties the first of them into a later one: MINT keeps
    the place of an emptied plot as a gap."""
    merge = _merge_of(snap, cmd) if _merging_anyhow(request) else None
    if merge is None or merge[0][0] == cmd.words[0]:
        return cmd
    plots, members = merge
    ids = [row for plot in plots[1:] for row in members[plot]]
    if len(ids) > commands.MAX_IDS or not set(ids) <= {row.id for row in snap.rows}:
        return cmd
    return Command("move", ids=ids, words=[plots[0]])


def alike(snap: Snapshot, request: str, cmds: List[Command]) -> set:
    """The plots a merge with no word for where takes in, and their rows: the model hesitating between two of
    them is no doubt, as the merge comes out the same."""
    moves = [cmd for cmd in cmds if cmd.verb == "move"]
    merge = _merge_of(snap, moves[0]) if len(moves) == 1 and _merging_anyhow(request) else None
    if merge is None:
        return set()
    plots, members = merge
    return set(plots) | {row for plot in plots for row in members[plot]}


def review(snap: Snapshot, request: str, cmds: List[Command]) -> List[Command]:
    """The model's commands, completed where the request is plain about what they leave out.

    A command moving the rows that others should join becomes a question. A plot switch the request
    doesn't name is dropped when it names another, or other settings or commands come with it: "enable the
    markers" must not turn the grid on. Rows the request disables are hidden from the plot, not removed. A variable named in full that the file lacks is
    looked for, not swapped for one of the file with a like name. Plots merged with no word for where end
    in the first of them, and a move of rows into the plot they are in, when all should be there or the request
    merges plots it makes clear, moves the others. A zoom on the last minutes ends where the plots' data ends,
    whatever numbers the model wrote. A title or label the request doesn't write is asked for, and
    what an answer undoes of itself is dropped.
    Text that tries to steer the assistant itself changes nothing.
    """
    if STEERING.search(request or ""):
        return [Command("say", text="I only act on plain requests about this workspace. What would you like to "
                                    "change?")]
    signals_part = HIDING_A_SWITCH.sub(" ", request or "")
    if HIDING.search(signals_part) and not REMOVING.search(signals_part):
        cmds = [Command("hide", ids=list(cmd.ids)) if cmd.verb == "remove" else cmd for cmd in cmds]
    for i, cmd in enumerate(cmds):
        missing = _not_in_file(snap, request, cmd) if cmd.verb == "add" else []
        if missing:
            cmds[i] = Command("find", words=missing[:4])
    hits = places(snap, request)
    # A switch the request names is evidence for what it wants; one it doesn't name is dropped only against such
    # evidence, or beside other settings: a typo or "the same" are no evidence.
    said = {key for key, words in SWITCH_WORDS.items() if words.search(request or "")}
    for cmd in cmds:
        if cmd.verb == "source" and cmd.words:
            cmd.words = [_source_meant(snap, request, cmd)]
        if cmd.verb == "plot" and set(cmd.ids) < set(hits):
            cmd.ids = list(hits)
        if cmd.verb == "plot":
            alone = not said and all(key in SWITCH_WORDS for key in cmd.params) and all(c.verb == "plot" for c in cmds)
            cmd.params = {key: value for key, value in cmd.params.items()
                          if key not in SWITCH_WORDS or key in said or alone}
    if any(cmd.verb == "plot" and not cmd.params for cmd in cmds):
        cmds = [cmd for cmd in cmds if cmd.verb != "plot" or cmd.params] or [
            Command("say", text="I can't change that yet. On a plot I can set log scale, grid, legend and where it "
                                "goes, markers, line style and width, font size, background, the y axis limits and "
                                "label, and the title; and on a signal its colour, line and markers.")]
    cmds = _zoom_to_the_end(snap, request, cmds)
    made_up = _made_up(request, cmds)
    if made_up:
        return [Command("ask", text=TEXT_QUESTIONS[made_up])]
    cmds = _undone(cmds)
    if sum(cmd.verb == "move" for cmd in cmds) == 1:
        for i, cmd in enumerate(cmds):
            cmds[i] = _merged_into_first(snap, request, _merge_in_place(snap, request, _all_into(snap, request, cmd)))
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
