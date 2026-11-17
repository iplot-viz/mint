"""The command language the model answers in: grammar and parser."""
import re
import shlex
from dataclasses import dataclass, field
from typing import Dict, List

from mint.assistant import settings

MAX_COMMANDS = 3
MAX_IDS = 12
RANGE_UNITS = ("seconds", "minutes", "hours", "days")
WINDOW_UNITS = ("ms", "s", "min", "h", "d")
WINDOW_SECONDS = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "d": 86400}
WINDOW = re.compile(r"^(-?\d+(?:\.\d+)?)(ms|s|min|h|d)$")
COMBINE_OPS = ("subtract", "add", "multiply", "divide")
PLOT_SWITCHES = ("log", "grid", "legend", "marker")
# The units of a time counted from the start of a pulse ("range from 40 to 60 s").
PULSE_UNITS = ("ms", "s", "min", "h")
# The canvas toolbar's tools, the windows and dialogs MINT opens, its themes, and the samples a ruler can mark.
TOOLS = ("select", "crosshair", "pan", "zoom", "dist", "marker", "ruler")
OPENABLE = ("export", "image", "csv", "save_workspace", "open_workspace", "preferences", "rulers")
THEMES = ("dark", "light", "auto", "none")
EXTREMES = ("max", "min", "first", "last")
SHIFT_UNITS = ("ms", "s", "min", "h", "d")
# Settings whose value is free text, written in quotes.
TEXT_PARAMS = ("title", "label", "ylabel")
# A time of the attached file (see snapshot.FileInfo), which a range can use instead of a date.
TIME_ID = re.compile(r"^t\d+$")


class CommandError(ValueError):
    """The model's answer is not valid command text."""


@dataclass
class Command:
    verb: str
    ids: List[str] = field(default_factory=list)
    words: List[str] = field(default_factory=list)
    params: Dict[str, str] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    text: str = ""

    def __str__(self):
        """The command as the model writes it, which parse() reads back ("Last applied" shows it)."""
        ids, words = self.ids, self.words
        if self.verb == "combine":
            ids, words = words + ids, []
        elif self.verb in ("move", "source"):
            words = ["to"] + words
        elif self.verb == "range" and words[:1] == ["from"] and len(words) == 4:
            words = ["from", words[1], "to", words[2], words[3]]
        elif self.verb == "range" and words[:1] == ["from"]:
            words = ["from", _when(words[1]), "to", _when(words[2])]
        elif self.verb == "zoom" and words[:1] != ["last"]:
            words = ["from", words[0], "to", words[1]] + words[2:] if len(words) == 3 else \
                ["from", _when(words[0]), "to", _when(words[1])]
        elif self.verb == "pan":
            words = ["by"] + words
        elif self.verb == "ruler" and words != ["off"]:
            words = ["at"] + (words if len(words) == 2 or words[0] in EXTREMES else [_when(words[0])])
        params = [f"window={v}s" if k == "seconds" else f'{k}="{v}"' if k in TEXT_PARAMS else f"{k}={v}"
                  for k, v in self.params.items()]
        return " ".join([self.verb] + ids + words + params + self.flags + ([f'"{self.text}"'] if self.text else []))


def _when(word: str) -> str:
    return word if TIME_ID.match(word) else f'"{word}"'


def _alt(options) -> str:
    return " | ".join(f'"{o}"' for o in options)


def build_grammar(row_ids, plot_ids, recipes: dict, file_ids=(), time_ids=(), data_sources=()) -> str:
    """GBNF grammar of the answers valid for these rows and plots, the variables and times of an attached file, and
    the data sources rows can use.

    Numbers are optional even where a recipe needs them: a forced number is invented, while MINT can ask.
    """
    windowed = [name for name, r in recipes.items() if "seconds" in r.get("params", {})]
    recipe_rules = []
    for name, recipe in recipes.items():
        params = recipe.get("params", {})
        if "seconds" in params:
            continue
        rule = f'"{name}"' + "".join(f' (" {pname}=" num)?' for pname in params)
        recipe_rules.append(rule)
    if windowed:
        # The window keeps the user's unit: converting "a quarter of an hour" is MINT's job.
        recipe_rules.insert(0, f'({_alt(windowed)}) (" window=" num ({_alt(WINDOW_UNITS)}))?')

    canvas = ["zoom", "pan", "home", "view", "focus", "ruler", "tool", "timewindow", "detach", "canvas"]
    verbs = (["plot-cmd", "split"] + canvas if plot_ids else []) + (["add"] if file_ids else []) + \
        ["find", "range", "draw", "open", "theme", "say"]
    if row_ids:
        # ask is for choosing among rows: with an empty table, a request about a signal is a search.
        verbs = ["process", "combine", "move", "remove", "hide", "show", "envelope", "style", "shift"] + \
            (["source"] if data_sources else []) + verbs + ["ask"]
    # With the times of a file (t1, t2...) a date can be one of them, and a pulse can't.
    when = "when" if time_ids else "str"
    pulse = ("[A-Za-z0-9_:.+/()-]{1,80}" if not time_ids else "([A-Za-su-z0-9_:.+/()-] [A-Za-z0-9_:.+/()-]{0,79} | "
             "\"t\" ([0-9]{0,40} [A-Za-z_:.+/()-] [A-Za-z0-9_:.+/()-]{0,38})?)")
    lines = [
        f"root ::= cmd (\"\\n\" cmd){{0,{MAX_COMMANDS - 1}}}",
        "cmd ::= " + " | ".join(verbs),
        "num ::= \"-\"? [0-9]{1,9} (\".\" [0-9]{1,6})?",
        "int ::= [1-9] [0-9]{0,5}",
        "str ::= \"\\\"\" [^\"\\\\\\n]{1,160} \"\\\"\"",
        "word ::= [A-Za-z0-9_:.+-]{1,40}",
        "find ::= \"find\" (\" \" word){1,4}",
        "range ::= \"range \" (\"last \" int \" \" (" + _alt(RANGE_UNITS) + ") | \"day \" (\"today\" | \"yesterday\" | "
        "[0-9]{4} \"-\" [0-9]{2} \"-\" [0-9]{2}" + (" | tid" if time_ids else "") + ")"
        " | \"month \" [0-9]{4} \"-\" [0-9]{2} | \"from \" " + when + " \" to \" " + when
        + " | \"from \" num \" to \" num \" \" (" + _alt(PULSE_UNITS) + ") | \"pulse \" " + pulse + ")",
        "draw ::= \"draw\"",
        "onoff ::= \"on\" | \"off\"",
        "ask ::= \"ask \" str",
        "say ::= \"say \" str",
        "open ::= \"open \" (" + _alt(OPENABLE) + ")",
        "theme ::= \"theme \" (" + _alt(THEMES) + ")",
        "units ::= " + _alt(PULSE_UNITS),
    ]
    if row_ids:
        lines += [
            "row ::= " + _alt(row_ids),
            f"rows ::= (\" \" row){{1,{MAX_IDS}}}",
            "process ::= \"process\" rows \" \" recipe (\" replace\")?",
            "recipe ::= " + " | ".join(recipe_rules),
            "combine ::= \"combine \" (" + _alt(COMBINE_OPS) + ") \" \" row \" \" row",
            "remove ::= \"remove\" rows",
            "hide ::= \"hide\" rows",
            "show ::= \"show\" rows",
            "envelope ::= \"envelope\" rows \" \" onoff",
        ]
        if data_sources:
            lines += ["ds ::= " + _alt(data_sources), "source ::= \"source\" rows \" to \" ds"]
        target = "plot | \"new\"" if plot_ids else "\"new\""
        lines.append(f"move ::= \"move\" rows \" to \" ({target})")
        lines += [
            "style ::= \"style\" rows sprop{1,4}",
            "sprop ::= " + " | ".join(f'" {key}=" ({settings.grammar_values(s)})' for key, s in settings.SIGNAL.items()),
            "shift ::= \"shift \" row \" \" (\"time \" num \" \" (" + _alt(SHIFT_UNITS) + ") | \"value \" num)"
            " (\" copy\")?",
        ]
    if file_ids:
        lines += [
            "fvar ::= " + _alt(file_ids),
            "add ::= \"add\" ((\" \" fvar){1," + str(MAX_IDS) + "} | \" all\") (\" together\")?",
        ]
    if time_ids:
        lines += ["tid ::= " + _alt(time_ids), "when ::= str | tid"]
    if plot_ids:
        lines += [
            "plot ::= " + _alt(plot_ids),
            "plots ::= (\" \" plot){1," + str(MAX_IDS) + "} | \" all\"",
            "plot-cmd ::= \"plot\" plots prop{1,4}",
            "split ::= \"split\" plots",
            "prop ::= " + " | ".join(f'" {key}=" ({settings.grammar_values(s)})' for key, s in settings.PLOT.items()),
            # A time from the start of what is drawn (of the pulse, in a pulse), or a date and time.
            "moment ::= num \" to \" num \" \" units | str \" to \" str",
            # "last": the end of what is drawn, back by that much.
            "zoom ::= \"zoom\" plots (\" from \" moment | \" last \" num \" \" units)",
            "pan ::= \"pan\" plots \" by \" num \" \" (" + _alt(SHIFT_UNITS) + ")",
            "home ::= \"home\" (\" \" plot){0," + str(MAX_IDS) + "}",
            "view ::= \"view \" (\"undo\" | \"redo\")",
            "focus ::= \"focus \" (plot | \"off\")",
            "ruler ::= \"ruler \" (plot \" at \" (num \" \" units | str)"
            + (" | row \" at \" (" + _alt(EXTREMES) + ")" if row_ids else "") + " | \"off\")",
            "tool ::= \"tool \" (" + _alt(TOOLS) + ")",
            "timewindow ::= \"timewindow\" (\" \" plot)?",
            "detach ::= \"detach \" onoff",
            "canvas ::= \"canvas\" cprop{1,3}",
            "cprop ::= " + " | ".join(f'" {key}=" ({settings.grammar_values(s)})' for key, s in settings.CANVAS.items()),
        ]
    return "\n".join(lines) + "\n"


def merge(cmds: List[Command]) -> List[Command]:
    """Fold commands that only differ in their ids, and drop repeated ones."""
    merged = []
    for c in cmds:
        twin = next((m for m in merged if m.verb == c.verb and m.verb in ("process", "plot", "remove", "hide", "show",
                                                                          "envelope", "split")
                     and m.words == c.words and m.params == c.params and m.flags == c.flags
                     and "all" not in m.ids + c.ids), None)
        if twin is not None:
            twin.ids += [i for i in c.ids if i not in twin.ids]
        elif str(c) not in [str(m) for m in merged]:
            merged.append(c)
    return merged


def parse(text: str) -> List[Command]:
    """Commands of an answer. Raises CommandError on anything outside the language."""
    commands = []
    for line in (text or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as e:
            raise CommandError(f"unreadable command {line!r}: {e}")
        if not tokens:
            continue
        commands.append(_parse_tokens(tokens, line))
    if not commands:
        raise CommandError("empty answer")
    return merge(commands)[:MAX_COMMANDS]


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _plain(value: float) -> str:
    return str(int(value)) if value == int(value) else repr(round(value, 9))


def _ids(tokens, prefix):
    ids = []
    while tokens and len(tokens[0]) > 1 and tokens[0][0] == prefix and tokens[0][1:].isdigit():
        token = tokens.pop(0)
        if token not in ids:
            ids.append(token)
    return ids


def _parse_tokens(tokens, line) -> Command:
    verb, rest = tokens[0], tokens[1:]
    if verb == "process":
        ids = _ids(rest, "r")
        if not ids or not rest:
            raise CommandError(f"process needs rows and a recipe: {line!r}")
        cmd = Command("process", ids=ids, words=[rest.pop(0)])
        for token in rest:
            if token == "replace":
                cmd.flags.append("replace")
            elif "=" in token:
                key, value = token.split("=", 1)
                if key == "window":
                    m = WINDOW.match(value)
                    if not m:
                        raise CommandError(f"unreadable window {value!r}")
                    key, value = "seconds", _plain(float(m.group(1)) * WINDOW_SECONDS[m.group(2)])
                cmd.params[key] = value
            else:
                raise CommandError(f"unexpected {token!r} in {line!r}")
        return cmd
    if verb == "combine":
        if len(rest) != 3 or rest[0] not in COMBINE_OPS:
            raise CommandError(f"combine needs an operation and two rows: {line!r}")
        return Command("combine", ids=rest[1:], words=[rest[0]])
    if verb == "plot":
        ids = ["all"] if rest[:1] == ["all"] else _ids(rest, "p")
        if ids == ["all"]:
            rest = rest[1:]
        cmd = Command("plot", ids=ids)
        for token in rest:
            if "=" not in token:
                raise CommandError(f"unexpected {token!r} in {line!r}")
            key, value = token.split("=", 1)
            cmd.params[key] = value
        if not ids or not cmd.params:
            raise CommandError(f"plot needs plots and a setting: {line!r}")
        return cmd
    if verb == "find":
        if not rest:
            raise CommandError("find needs words")
        return Command("find", words=rest[:4])
    if verb == "range":
        if not rest:
            raise CommandError("range needs a period")
        kind = rest[0]
        if kind == "last" and len(rest) == 3 and rest[1].isdigit() and rest[2] in RANGE_UNITS:
            return Command("range", words=rest)
        if kind in ("day", "month", "pulse") and len(rest) == 2:
            return Command("range", words=rest)
        if kind == "from" and len(rest) == 4 and rest[2] == "to":
            return Command("range", words=["from", rest[1], rest[3]])
        if kind == "from" and len(rest) == 5 and rest[2] == "to" and rest[4] in PULSE_UNITS \
                and _is_number(rest[1]) and _is_number(rest[3]):
            return Command("range", words=["from", rest[1], rest[3], rest[4]])
        raise CommandError(f"unreadable range {line!r}")
    if verb == "move":
        ids = _ids(rest, "r")
        if not ids or len(rest) != 2 or rest[0] != "to":
            raise CommandError(f"move needs rows and a target: {line!r}")
        return Command("move", ids=ids, words=[rest[1]])
    if verb == "source":
        ids = _ids(rest, "r")
        if not ids or len(rest) != 2 or rest[0] != "to":
            raise CommandError(f"source needs rows and a data source: {line!r}")
        return Command("source", ids=ids, words=[rest[1]])
    if verb == "envelope":
        ids = _ids(rest, "r")
        if not ids or rest not in (["on"], ["off"]):
            raise CommandError(f"envelope needs rows and on or off: {line!r}")
        return Command("envelope", ids=ids, words=rest)
    if verb == "split":
        ids = ["all"] if rest == ["all"] else _ids(rest, "p")
        if not ids or (ids != ["all"] and rest):
            raise CommandError(f"split needs plots: {line!r}")
        return Command("split", ids=ids)
    if verb in ("remove", "hide", "show"):
        ids = _ids(rest, "r")
        if not ids or rest:
            raise CommandError(f"{verb} needs rows: {line!r}")
        return Command(verb, ids=ids)
    if verb == "add":
        ids = ["all"] if rest[:1] == ["all"] else _ids(rest, "v")
        if ids == ["all"]:
            rest = rest[1:]
        if not ids or rest not in ([], ["together"]):
            raise CommandError(f"add needs variables of the file: {line!r}")
        return Command("add", ids=ids, flags=rest)
    if verb in ("style", "canvas"):
        ids = _ids(rest, "r") if verb == "style" else []
        cmd = Command(verb, ids=ids)
        for token in rest:
            if "=" not in token:
                raise CommandError(f"unexpected {token!r} in {line!r}")
            key, value = token.split("=", 1)
            cmd.params[key] = value
        if (verb == "style" and not ids) or not cmd.params:
            raise CommandError(f"{verb} needs {'rows and ' if verb == 'style' else ''}a setting: {line!r}")
        return cmd
    if verb in ("zoom", "pan"):
        ids = ["all"] if rest[:1] == ["all"] else _ids(rest, "p")
        if ids == ["all"]:
            rest = rest[1:]
        if verb == "zoom" and ids and len(rest) == 5 and rest[0] == "from" and rest[2] == "to" \
                and rest[4] in PULSE_UNITS and _is_number(rest[1]) and _is_number(rest[3]):
            return Command("zoom", ids=ids, words=[rest[1], rest[3], rest[4]])
        if verb == "zoom" and ids and len(rest) == 3 and rest[0] == "last" and _is_number(rest[1]) \
                and rest[2] in PULSE_UNITS:
            return Command("zoom", ids=ids, words=rest)
        if verb == "zoom" and ids and len(rest) == 4 and rest[0] == "from" and rest[2] == "to":
            return Command("zoom", ids=ids, words=[rest[1], rest[3]])
        if verb == "pan" and ids and len(rest) == 3 and rest[0] == "by" and _is_number(rest[1]) \
                and rest[2] in SHIFT_UNITS:
            return Command("pan", ids=ids, words=[rest[1], rest[2]])
        raise CommandError(f"unreadable {verb} {line!r}")
    if verb == "home":
        ids = _ids(rest, "p")
        if rest:
            raise CommandError(f"home takes plots or nothing: {line!r}")
        return Command("home", ids=ids)
    if verb == "view" and rest in (["undo"], ["redo"]):
        return Command("view", words=rest)
    if verb == "focus" and len(rest) == 1 and (rest[0] == "off" or _ids(list(rest), "p")):
        return Command("focus", ids=[] if rest[0] == "off" else rest, words=["off"] if rest[0] == "off" else [])
    if verb == "ruler":
        if rest == ["off"]:
            return Command("ruler", words=["off"])
        ids = _ids(rest, "p") or _ids(rest, "r")
        if len(ids) == 1 and rest[:1] == ["at"]:
            if len(rest) == 3 and _is_number(rest[1]) and rest[2] in PULSE_UNITS:
                return Command("ruler", ids=ids, words=rest[1:])
            if len(rest) == 2:
                return Command("ruler", ids=ids, words=rest[1:])
        raise CommandError(f"unreadable ruler {line!r}")
    if verb == "tool" and len(rest) == 1 and rest[0] in TOOLS:
        return Command("tool", words=rest)
    if verb == "timewindow":
        ids = _ids(rest, "p")
        if rest:
            raise CommandError(f"timewindow takes a plot or nothing: {line!r}")
        return Command("timewindow", ids=ids)
    if verb == "detach" and rest in (["on"], ["off"]):
        return Command("detach", words=rest)
    if verb == "open" and len(rest) == 1 and rest[0] in OPENABLE:
        return Command("open", words=rest)
    if verb == "theme" and len(rest) == 1 and rest[0] in THEMES:
        return Command("theme", words=rest)
    if verb == "shift":
        ids = _ids(rest, "r")
        flags = ["copy"] if rest[-1:] == ["copy"] else []
        rest = rest[:-1] if flags else rest
        if len(ids) == 1 and len(rest) == 3 and rest[0] == "time" and _is_number(rest[1]) and rest[2] in SHIFT_UNITS:
            return Command("shift", ids=ids, words=rest, flags=flags)
        if len(ids) == 1 and len(rest) == 2 and rest[0] == "value" and _is_number(rest[1]):
            return Command("shift", ids=ids, words=rest, flags=flags)
        raise CommandError(f"unreadable shift {line!r}")
    if verb == "draw" and not rest:
        return Command("draw")
    if verb in ("ask", "say") and len(rest) == 1:
        return Command(verb, text=rest[0])
    raise CommandError(f"unknown command {line!r}")
