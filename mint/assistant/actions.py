"""Commands turned into validated, reversible changes of the workspace."""
import calendar
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from iplotLogging import setupLogger
from mint.assistant import recipes
from mint.assistant.commands import Command
from mint.assistant.snapshot import ORDINALS, Snapshot

logger = setupLogger.get_logger(__name__)

UNIT_SECONDS = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
OPERATORS = {"subtract": "-", "add": "+", "multiply": "*", "divide": "/"}
OPERATOR_WORDS = {"subtract": "minus", "add": "plus", "multiply": "times", "divide": "over"}
PROCESSABLE_PLOT_TYPES = ("PlotXY", "")
COMMENT_PREFIX = "Assistant: "
# Nanosecond timestamps in int64 cover 1677-2262; plant data lives well inside this.
FIRST_YEAR, LAST_YEAR = 1970, 2100
MAX_SPAN_SECONDS = 100 * 365 * 86400
# The "Last" box of the relative time mode is a spin box that stops at 99.
MAX_RELATIVE_AMOUNT = 99


class ActionError(ValueError):
    """A command that cannot be applied; the message is shown to the user."""


class MissingValue(ActionError):
    """A number the user did not give: the message asks for it, ``param`` says which one."""

    def __init__(self, question: str, param: str):
        super().__init__(question)
        self.param = param
        self.command = None


@dataclass
class Lazy:
    """A value decided when the change is applied: a free alias or a new plot."""
    kind: str
    key: str


class ApplyContext:
    """What one Apply needs to know about the table as it is at that moment."""

    def __init__(self, workspace):
        self.ws = workspace
        self.reset()

    def reset(self):
        self._aliases = None
        self._next_row = None
        self._stacks = {}
        self._resolved = {}

    def resolve(self, value):
        if not isinstance(value, Lazy):
            return value
        # The same Lazy used by two changes (an alias given to a row and then referenced) is one name.
        if id(value) in self._resolved:
            return self._resolved[id(value)]
        if value.kind == "alias":
            if self._aliases is None:
                self._aliases = set(self.ws.aliases())
            result = unique_alias(value.key, self._aliases)
            self._aliases.add(result)
        else:
            if value.key not in self._stacks:
                if self._next_row is None:
                    self._next_row = self.ws.next_free_plot_row()
                self._stacks[value.key] = f"{self._next_row}.1"
                self._next_row += 1
            result = self._stacks[value.key]
        self._resolved[id(value)] = result
        return result

    def values(self, values: dict) -> dict:
        return {k: self.resolve(v) for k, v in values.items()}


@dataclass
class Change:
    lines: List[str]
    do: Callable[[], None]
    undo: Callable[[], None]
    needs_draw: bool = False
    needs_refresh: bool = False


@dataclass
class Proposal:
    title: str = ""
    changes: List[Change] = field(default_factory=list)
    detail: str = ""
    messages: List[str] = field(default_factory=list)
    search: Optional[List[str]] = None
    context: Optional[ApplyContext] = None
    # The model asked the user something instead of (or before) acting.
    question: bool = False
    # The commands that make the changes, as the model writes them ("Last applied" once applied).
    commands: List[str] = field(default_factory=list)

    @property
    def lines(self) -> List[str]:
        return [line for change in self.changes for line in change.lines if line]

    def apply(self):
        """All the changes or none: on a failure the ones done are undone."""
        if self.context is not None:
            self.context.reset()
        done = []
        try:
            for change in self.changes:
                done.append(change)  # before do(): a change that fails halfway is undone too
                change.do()
        except Exception:
            for change in reversed(done):
                try:
                    change.undo()
                except Exception:
                    logger.exception("Assistant: undo after a failed apply")
            raise

    def undo(self) -> List[str]:
        """Undo every change it can, newest first; returns why the others could not be undone."""
        problems = []
        for change in reversed(self.changes):
            try:
                change.undo()
            except ActionError as e:
                problems.append(str(e))
            except Exception:
                logger.exception("Assistant: undo failed")
                problems.append("One change couldn't be put back.")
        return problems


def _short(name: str, limit: int = 32) -> str:
    name = name.split(":")[-1] if ":" in name and len(name) > limit else name
    return name if len(name) <= limit else name[:limit - 1] + "…"


def _identifier(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text.split(":")[-1]).strip("_")
    return text or "signal"


def unique_alias(base: str, taken: set) -> str:
    alias = _identifier(base)[:48]
    if alias not in taken:
        return alias
    n = 2
    while f"{alias}_{n}" in taken:
        n += 1
    return f"{alias}_{n}"


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


class Planner:
    """Builds a Proposal from commands, checking them against a snapshot of the workspace."""

    def __init__(self, workspace, snap: Snapshot):
        self.ws = workspace
        self.snap = snap
        self.context = ApplyContext(workspace)
        # Only to name things on the card; the real names are taken at Apply.
        self._aliases = set(snap.aliases())
        self._next_plot_row = snap.next_free_plot_row()

    def plan(self, cmds: List[Command]) -> Proposal:
        proposal = Proposal(context=self.context)
        titles = []
        for cmd in cmds:
            handler = getattr(self, f"_{cmd.verb}", None)
            if handler is None:
                raise ActionError(f"I can't do '{cmd.verb}' yet.")
            try:
                title = handler(cmd, proposal)
            except MissingValue as e:
                e.command = cmd  # so the user's answer can fill it in
                raise
            if title and title not in titles:
                titles.append(title)
        proposal.title = " + ".join(titles)
        proposal.commands = [str(c) for c in cmds if c.verb not in ("ask", "say", "find")]
        return proposal

    def _name(self, row) -> str:
        """A row as the user knows it: by its name, plus its plot or order only when names repeat."""
        label = _short(row.label)
        twins = [r for r in self.snap.rows if _short(r.label).lower() == label.lower()]
        if len(twins) <= 1:
            return label
        if row.plot and sum(r.plot == row.plot for r in twins) == 1:
            return f"{label} (in {self.snap.place(row.plot)})"
        order = [r.id for r in twins].index(row.id)
        return f"{label} (the {ORDINALS[order] if order < len(ORDINALS) else f'{order + 1}th'} one in the table)"

    def _say_names(self, text: str) -> str:
        """A sentence of the model with any r1/p2 it let slip turned into names and places."""
        text = re.sub(r"\s*\(\s*[rp]\d+\s*\)", "", text)

        def name(m):
            item = self.snap.row(m.group(0)) if m.group(1) == "r" else self.snap.plot(m.group(0))
            if item is None:
                return m.group(0)
            return self._name(item) if m.group(1) == "r" else self.snap.place(item.id)

        return re.sub(r"\b([rp])\d+\b", name, text)

    def _alias(self, base: str):
        shown = unique_alias(base, self._aliases)
        self._aliases.add(shown)
        return shown, Lazy("alias", base)

    @staticmethod
    def _new_plot(key: str) -> Lazy:
        return Lazy("stack", key)


    def _process(self, cmd: Command, proposal: Proposal) -> str:
        recipe = cmd.words[0]
        if recipe not in recipes.load():
            raise ActionError(f"I don't know the processing '{recipe}'.")
        replace = "replace" in cmd.flags
        rows = [self._row(row_id) for row_id in cmd.ids]
        if recipes.load()[recipe]["axis"] == "x":
            # A plot mixing absolute and relative time axes is not drawn, so the whole plot changes.
            plots = {r.plot for r in rows if r.plot}
            rows += [r for r in self.snap.rows if r.plot in plots and r not in rows]
        try:
            values = recipes.resolve_params(recipe, cmd.params, self._window_reference(rows))
        except recipes.RecipeError as e:
            text = _capital(str(e))
            text = text if text[-1:] in ".?!" else text + "."
            if isinstance(e, recipes.MissingParam):
                raise MissingValue(text, e.param)
            raise ActionError(text)
        asked = set(cmd.ids)
        for row in rows:
            if row.envelope:
                raise ActionError(f"{self._name(row)} is shown as a min/max band, and I can't process that.")
            if row.plot_type not in PROCESSABLE_PLOT_TYPES:
                raise ActionError(f"{self._name(row)} isn't plotted against time, so I can't process it.")
        title = ""
        for row in sorted(rows, key=lambda r: r.index):
            info = recipes.render(recipe, values, row.y if recipes.load()[recipe]["axis"] == "y" else "")
            self.ws.check_expression(info["expr"])
            proposal.detail = proposal.detail or info["expr"]
            title = info["title"]
            column = info["axis"]
            # " — " after the name: ITER variable names have colons of their own.
            if column == "x":
                why = "" if row.id in asked else ", so the plot keeps one time axis"
                line = f"{self._name(row)} — {info['plain']}{why}"
            elif replace:
                line = f"{self._name(row)} — {info['plain']}, replacing the original"
            if replace or column == "x":
                proposal.changes.append(self._set_cells_change(
                    row, {column: info["expr"]}, line))
            else:
                shown, alias = self._alias(f"{row.alias or row.variable}_{info['alias']}")
                where = f"in {self.snap.place(row.plot)}" if row.plot else "in the table, not plotted yet"
                proposal.changes.append(self._copy_row_change(
                    row, {column: info["expr"], "Alias": alias, "Comment": COMMENT_PREFIX + info["describe"]},
                    f"{self._name(row)} — {info['plain']} → new signal {shown}, {where}"))
        return title

    def _window_reference(self, rows) -> Optional[float]:
        if self.snap.range_seconds:
            return self.snap.range_seconds
        for row in rows:
            span = self.ws.plot_x_span_seconds(self.snap.plot(row.plot)) if row.plot else None
            if span:
                return span
        return None

    def _combine(self, cmd: Command, proposal: Proposal) -> str:
        op = cmd.words[0]
        a, b = self._row(cmd.ids[0]), self._row(cmd.ids[1])
        if a.id == b.id:
            raise ActionError("I need two different signals to combine.")
        if a.data_source != b.data_source:
            # MINT evaluates an expression in the data source of its row: the other one would be refused.
            raise ActionError(f"I can only combine two signals from the same source, and these come from "
                              f"{a.data_source} and {b.data_source}.")
        refs, names = [], []
        for row in (a, b):
            if row.alias:
                refs.append(row.alias)
                names.append(row.alias)
            elif not row.is_expression:
                refs.append(row.variable)
                names.append(row.variable)
            else:
                # A row computed by an expression can only be referenced by its alias.
                given, alias = self._alias(f"{row.id}_{_identifier(row.variable)}")
                proposal.changes.append(self._set_cells_change(
                    row, {"Alias": alias}, f"{self._name(row)} gets the name {given}, so the new signal can use it"))
                refs.append(alias)
                names.append(given)
        expr = f"${{{names[0]}}} {OPERATORS[op]} ${{{names[1]}}}"
        self.ws.check_expression(expr, is_expression=True)
        shown, alias = self._alias(f"{_identifier(a.label)}_{OPERATOR_WORDS[op]}_{_identifier(b.label)}")
        stack = self._new_plot(f"combine-{a.id}-{b.id}")
        values = {"DS": a.data_source, "Variable": _Expression(refs, OPERATORS[op]), "Stack": stack,
                  "Alias": alias, "Comment": COMMENT_PREFIX + f"{a.label} {OPERATORS[op]} {b.label}"}
        proposal.detail = proposal.detail or expr
        # In words: a "-" between two ITER codes, which have dashes of their own, is easy to misread.
        proposal.changes.append(self._new_row_change(
            values, after_uid=(b if b.index > a.index else a).uid,
            line=f"New signal {shown} = {self._name(a)} {OPERATOR_WORDS[op]} {self._name(b)}, in a new plot"))
        return "New signal"


    def _move(self, cmd: Command, proposal: Proposal) -> str:
        target = cmd.words[0]
        if target == "new":
            stack, place = self._new_plot("move"), "a new plot"
        else:
            plot = self.snap.plot(target)
            if plot is None:
                raise ActionError(f"There is no plot {target}.")
            stack, place = plot.stack, self.snap.place(target)
        rows = [self._row(row_id) for row_id in cmd.ids]
        if len(rows) > 1:
            # One line for the lot: "Move A to a new plot" twice would read as two new plots.
            names = ", ".join(self._name(r) for r in rows[:-1]) + f" and {self._name(rows[-1])}"
            lines = [f"Move {names} together to {place}"] + [""] * (len(rows) - 1)
        else:
            lines = [f"Move {self._name(rows[0])} to {place}"]
        for row, line in zip(rows, lines):
            proposal.changes.append(self._set_cells_change(
                row, {"Stack": stack}, line))
        return "Move"

    def _remove(self, cmd: Command, proposal: Proposal) -> str:
        for row_id in cmd.ids:
            proposal.changes.append(self._remove_row_change(self._row(row_id)))
        return "Remove"

    def _draw(self, cmd: Command, proposal: Proposal) -> str:
        proposal.changes.append(Change([], lambda: None, lambda: None, needs_draw=True))
        return "Draw"


    def _plot(self, cmd: Command, proposal: Proposal) -> str:
        plots = self.snap.plots if cmd.ids == ["all"] else [self._plot_info(pid) for pid in cmd.ids]
        if not plots:
            raise ActionError("There are no plots yet.")
        settings = {}
        words = []
        for key, value in cmd.params.items():
            if key in ("log", "grid", "legend"):
                if value not in ("on", "off"):
                    raise ActionError(f"{key} must be on or off.")
                settings[{"log": "log_scale"}.get(key, key)] = value == "on"
                words.append(f"{'log scale' if key == 'log' else key} {value}")
            elif key == "title":
                settings["plot_title"] = value
                words.append(f"title \"{value}\"")
            else:
                raise ActionError(f"I can't change '{key}' of a plot.")
        positions = [(p.id, p.row, p.col) for p in plots]
        for plot_id, row, col in positions:
            if self.ws.canvas_plot(row, col) is None:
                raise ActionError(f"{_capital(self.snap.place(plot_id))} isn't drawn yet. Click Draw, then ask me again.")
        ws = self.ws
        places = {p.id: self.snap.place(p.id) for p in plots}
        old = []

        def find(plot_id, row, col):
            # A Draw replaces the plot objects, so they are looked up by position every time.
            plot = ws.canvas_plot(row, col)
            if plot is None:
                raise ActionError(f"{_capital(places[plot_id])} isn't drawn any more, so I couldn't change it.")
            return plot

        def do():
            old.clear()
            for plot_id, row, col in positions:
                plot = find(plot_id, row, col)
                old.append({k: getattr(plot, k, None) for k in settings})
                for k, v in settings.items():
                    setattr(plot, k, v)

        def undo():
            for (plot_id, row, col), previous in zip(positions, old):
                plot = find(plot_id, row, col)
                for k, v in previous.items():
                    setattr(plot, k, v)

        where = "all plots" if cmd.ids == ["all"] else " and ".join(places[p.id] for p in plots)
        proposal.changes.append(Change([f"{_capital(where)}: {', '.join(words)}"], do, undo, needs_refresh=True))
        return "Plot settings"


    def _range(self, cmd: Command, proposal: Proposal) -> str:
        kind = cmd.words[0]
        ws = self.ws
        if kind == "last":
            amount, unit = int(cmd.words[1]), cmd.words[2]
            span = amount * UNIT_SECONDS[unit]
            if span > MAX_SPAN_SECONDS:
                raise ActionError("That time range is longer than 100 years.")
            line = f"Time range: the last {unit[:-1]}" if amount == 1 else f"Time range: the last {amount} {unit}"
            relative = _relative(span)
            if relative is not None:
                new = {"mode": "RELATIVE_TIME", "relative": relative[0], "base": relative[1],
                       "auto_refresh": ws.relative_auto_refresh()}
                set_range = lambda: ws.set_range_dict(new)  # noqa: E731
            else:
                # Too many units for the relative mode's box: the same span, ending now.
                end = self.snap.now.astimezone(timezone.utc)
                start_ns, end_ns = _ns(end - timedelta(seconds=span)), _ns(end)
                set_range = lambda: ws.set_time_range_ns(start_ns, end_ns)  # noqa: E731
        elif kind == "pulse":
            pulse = cmd.words[1]
            new = {"mode": "PULSE_NUMBER", "pulse_nb": [pulse], "base": 1, "t_start": "", "t_end": ""}
            line = f"Pulse {pulse}"
            set_range = lambda: ws.set_range_dict(new)  # noqa: E731
        else:
            start, end = self._period(cmd)
            line = f"Time range: {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M} UTC"
            start_ns, end_ns = _ns(start), _ns(end)
            set_range = lambda: ws.set_time_range_ns(start_ns, end_ns)  # noqa: E731
        before = {}

        def do():
            before.clear()
            before.update(ws.range_dict())
            set_range()

        def undo():
            if before:
                ws.set_range_dict(before)

        proposal.changes.append(Change([line], do, undo, needs_draw=True))
        return "Time range"

    def _period(self, cmd: Command):
        kind = cmd.words[0]
        try:
            if kind == "day":
                if cmd.words[1] in ("today", "yesterday"):
                    now = self.snap.now.astimezone(timezone.utc)
                    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
                    if cmd.words[1] == "yesterday":
                        start -= timedelta(days=1)
                else:
                    start = datetime.strptime(cmd.words[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end = start + timedelta(days=1)
            elif kind == "month":
                start = datetime.strptime(cmd.words[1], "%Y-%m").replace(tzinfo=timezone.utc)
                end = start + timedelta(days=calendar.monthrange(start.year, start.month)[1])
            else:
                start, end = (_parse_when(text) for text in cmd.words[1:3])
        except ValueError:
            raise ActionError("I couldn't read those dates. Could you write them like 2026-11-03 08:00?")
        if end <= start:
            raise ActionError("The end of the time range must be after its start.")
        if not (FIRST_YEAR <= start.year and end.year <= LAST_YEAR):
            raise ActionError(f"Dates must be between {FIRST_YEAR} and {LAST_YEAR}.")
        return start, end


    def _ask(self, cmd: Command, proposal: Proposal) -> str:
        proposal.messages.append(self._say_names(cmd.text))
        proposal.question = True
        return ""

    def _say(self, cmd: Command, proposal: Proposal) -> str:
        proposal.messages.append(self._say_names(cmd.text))
        return ""

    def _find(self, cmd: Command, proposal: Proposal) -> str:
        proposal.search = list(cmd.words)
        return ""


    def _row(self, row_id: str):
        row = self.snap.row(row_id)
        if row is None:
            raise ActionError(f"There is no row {row_id[1:]} in the table.")
        return row

    def _plot_info(self, plot_id: str):
        plot = self.snap.plot(plot_id)
        if plot is None:
            raise ActionError(f"There is no plot {plot_id}.")
        return plot

    def _set_cells_change(self, row, values: dict, line: str) -> Change:
        ws, ctx, uid = self.ws, self.context, row.uid
        old = {}

        def do():
            old.clear()
            old.update(ws.set_cells(uid, ctx.values(values)))

        def undo():
            if old:
                ws.set_cells(uid, old)

        return Change([line], do, undo, needs_draw=True)

    def _copy_row_change(self, row, overrides: dict, line: str) -> Change:
        values = self.ws.copyable_values(row.uid)
        values.update(overrides)
        return self._new_row_change(values, after_uid=row.uid, line=line)

    def _new_row_change(self, values: dict, after_uid: str, line: str) -> Change:
        ws, ctx = self.ws, self.context
        created = {}

        def do():
            resolved = ctx.values(values)
            variable = resolved.get("Variable")
            if isinstance(variable, _Expression):
                resolved["Variable"] = variable.text(ctx)
            created["uid"] = ws.insert_row_after(after_uid, resolved)

        def undo():
            if created.get("uid"):
                ws.remove_row(created.pop("uid"))

        return Change([line], do, undo, needs_draw=True)

    def _remove_row_change(self, row) -> Change:
        ws, uid = self.ws, row.uid
        saved = {}

        def do():
            saved.clear()
            saved.update(ws.remove_row(uid))

        def undo():
            if saved:
                ws.restore_row(saved)
                saved.clear()

        return Change([f"Remove {self._name(row)} from the table"], do, undo, needs_draw=True)


class _Expression:
    """A combine expression whose aliases may only be known at Apply."""

    def __init__(self, refs, operator):
        self.refs, self.operator = refs, operator

    def text(self, ctx: ApplyContext) -> str:
        names = [ref if isinstance(ref, str) else ctx.resolve(ref) for ref in self.refs]
        return f"${{{names[0]}}} {self.operator} ${{{names[1]}}}"


def _relative(span: int):
    """(amount, unit seconds) for the relative time mode, or None if no unit fits its box."""
    for base in (86400, 3600, 60, 1):
        if span % base == 0 and span // base <= MAX_RELATIVE_AMOUNT:
            return span // base, base
    return None


def _parse_when(text: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(text)


def _ns(moment: datetime) -> int:
    delta = moment - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 10 ** 9 + delta.microseconds * 1000
