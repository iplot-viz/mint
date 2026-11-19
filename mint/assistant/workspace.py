"""The assistant's only door into MINT's main window."""
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QModelIndex, QSettings, Qt

from iplotlib.interface.iplotSignalAdapter import Result, Stage, StatusInfo
from iplotLogging import setupLogger
from mint.assistant import files, prompt, snapshot
from mint.assistant.actions import ActionError
from mint.assistant.snapshot import RowInfo

logger = setupLogger.get_logger(__name__)

READ_ONLY = ("Status", "Output Datatype")
NOT_COPIED = READ_ONLY + ("uid",)
# How the drawn signal of a row came out (see MintWorkspace.drawn_outcome).
DRAWN, EMPTY, NOT_COMPUTED = "drawn", "empty", "not computed"
# What the archive says about a variable's last sample (see MintWorkspace.latest_sample).
FOUND, NONE_BEFORE, UNKNOWN_VARIABLE, UNTOLD = "found", "none before", "unknown variable", "untold"
MAX_SEARCH_RESULTS = 40
PULSE_UNIT_WORDS = {1: "s", 60: "min", 3600: "h", 86400: "days"}
# Written like a code: "EC", "CRYO", "D1", "System1". The variable tree groups names by what comes
# before their first separator.
GROUP = re.compile(r"[A-Z][A-Z0-9]{1,7}|[A-Z][a-z]+[0-9]+")
SEPARATOR = "[-.:_]"


@dataclass
class VariableSearch:
    source: str
    found: List[Tuple[str, str]]  # (name, HMI description), the best MAX_SEARCH_RESULTS
    total: int  # how many there were before the cut
    words: List[str] = field(default_factory=list)  # what was looked for, besides the group
    group: str = ""  # what the names start with, when the request gave it
    missing: List[str] = field(default_factory=list)  # tags looked up one by one that nothing has


def _leaves(document: dict):
    """Variable names of a nested search result: the keys whose value is not a folder."""
    for key, value in document.items():
        if isinstance(value, dict):
            yield from _leaves(value)
        else:
            yield key


def _as_typed(word: str, request: str) -> str:
    # The model may change the case; the request has it as the user wrote it.
    match = re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", request, re.IGNORECASE) if request else None
    return match.group(0) if match else word


def _as_number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _named_source(words, request: str, sources) -> Optional[str]:
    """The data source the words or the request name, as MINT spells it."""
    known = {source.lower(): source for source in sources}
    for token in list(words) + re.findall(r"[\w.-]+", request):
        if token.lower() in known:
            return known[token.lower()]
    return None


def _group(words, request: str) -> str:
    """The first word written like a code, as written: it may be a group of the variable tree."""
    for word in words:
        typed = _as_typed(word, request)
        if GROUP.fullmatch(typed):
            return typed
    return ""


def _server_pattern(words) -> str:
    """The server filters on the most specific word that is in names; the others are checked here."""
    meant = {w.lower(): prompt.SAID.get(w.lower()) for w in words}
    key = max([w for w in words if not meant[w.lower()]] or words, key=lambda w: (any(c.isdigit() for c in w), len(w)))
    meaning = meant[key.lower()]
    return f".*{prompt.MEASURES[meaning][0]}[0-9].*" if meaning else f".*{re.escape(key)}.*"


class MintWorkspace:
    def __init__(self, window):
        self.window = window


    @property
    def model(self):
        return self.window.sigCfgWidget.model

    def table(self):
        return self.model.get_dataframe()

    def selected_indices(self):
        rows = set()
        for item in self.window.sigCfgWidget.item_widgets:
            selection = item.view().selectionModel()
            if selection is not None:
                rows.update(index.row() for index in selection.selectedIndexes())
        return rows

    def snapshot(self, last_action: str = "") -> snapshot.Snapshot:
        self.ensure_uids()
        text, seconds, pulse_mode = self.range_summary()
        snap = snapshot.build(self.table(), self.selected_indices(), canvas=self.window.canvas, range_text=text,
                              range_seconds=seconds, pulse_mode=pulse_mode, last_action=last_action,
                              data_sources=self.data_source_choices())
        snap.canvas = self.canvas_state(snap)
        return snap

    def canvas_state(self, snap) -> str:
        """The canvas as the model must know it to undo it: a plot shown alone, rulers, a tool, its own window."""
        parts = []
        try:
            focused = self.focused()
            plot = next((p for p in snap.plots if (p.row, p.col) == focused), None) if focused else None
            if plot is not None:
                parts.append(f"{plot.id} shown alone")
            names = sorted({r["name"] for r in self.rulers()})
            if names:
                parts.append(f"ruler{'s' if len(names) > 1 else ''} " + ", ".join(names))
            mode = self.mouse_mode()
            if mode and mode != "MM_SELECT":
                parts.append(f"{mode[3:].lower()} tool on")
            if self.detached():
                parts.append("in a window of its own")
        except Exception as e:  # a canvas being rebuilt: the plots alone are enough
            logger.debug(f"Assistant: no canvas state: {e}")
        return ", ".join(parts)

    def ensure_uids(self):
        """Give a uid to rows that have none or share one.

        A workspace saved without the uid column loads with every uid empty, and the first would match all.
        """
        table = self.table()
        if "uid" not in table.columns:
            return
        seen = set()
        fixes = []
        for i, uid in enumerate(table["uid"]):
            uid = str(uid or "").strip()
            if not uid or uid in seen:
                fixes.append(i)
            seen.add(uid)
        if fixes:
            column = self._column("uid")
            with self.model.activate_fast_mode():
                for i in fixes:
                    self.model.setData(self.model.index(i, column), str(uuid.uuid4()), Qt.ItemDataRole.EditRole)

    def aliases(self) -> set:
        table = self.table()
        return {str(a).strip() for a in table["Alias"] if str(a or "").strip()} if "Alias" in table.columns else set()

    def next_free_plot_row(self) -> int:
        rows = [snapshot.parse_stack(str(s)) for s in self.table().get("Stack", [])]
        return max((r[0] for r in rows if r), default=0) + 1

    def range_summary(self):
        selector = self.window.dataRangeSelector
        try:
            current = selector.export_dict()
        except Exception as e:
            logger.debug(f"Assistant: no time range to describe: {e}")
            return "", None, False
        mode = current.get("mode")
        if mode == "RELATIVE_TIME":
            amount, base = int(current.get("relative") or 0), int(current.get("base") or 1)
            unit = {1: "seconds", 60: "minutes", 3600: "hours", 86400: "days"}.get(base, f"x{base} s")
            return f"last {amount} {unit}", float(amount * base) or None, False
        if mode == "PULSE_NUMBER":
            pulses = ", ".join(p for p in current.get("pulse_nb") or [] if p) or "none set"
            seconds = None
            try:
                seconds = (float(current.get("t_end")) - float(current.get("t_start"))) * float(current.get("base") or 1)
            except (TypeError, ValueError):
                pass
            # Its times count from the start of the pulse: "40 to 60 s" is a part of it, not a time of day.
            start, end = str(current.get("t_start") or "").strip(), str(current.get("t_end") or "").strip()
            unit = PULSE_UNIT_WORDS.get(_as_number(current.get("base")) or 1, "s")
            times = f", {start or 'start'} to {end or 'end'} {unit} from its start" if start or end else \
                ", times in s from its start"
            return f"pulse {pulses}{times}", seconds if seconds and seconds > 0 else None, True
        try:
            start, end = selector.get_time_range()
            start_s, end_s = int(start) / 1e9, int(end) / 1e9
            fmt = "%Y-%m-%d %H:%M"
            text = (f"{datetime.fromtimestamp(start_s, timezone.utc):{fmt}} to "
                    f"{datetime.fromtimestamp(end_s, timezone.utc):{fmt}} UTC")
            return text, (end_s - start_s) or None, False
        except Exception as e:
            logger.debug(f"Assistant: no time range to describe: {e}")
            return "not set", None, False

    def time_range_ns(self) -> Optional[Tuple[int, int]]:
        """The time range in ns since the epoch (the last hours end now); None for pulses."""
        selector = self.window.dataRangeSelector
        try:
            if selector.export_dict().get("mode") == "PULSE_NUMBER":
                return None
            start, end = selector.get_time_range()
            return int(start), int(end)
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Assistant: no time range: {e}")
            return None

    def latest_sample(self, source_name: str, variable: str, before_ns: int) -> Tuple[str, Optional[int]]:
        """Last sample before ``before_ns``: (FOUND, ns), or (NONE_BEFORE | UNKNOWN_VARIABLE | UNTOLD, None).

        Asked only of CODAC_UDA sources, which answer a one-sample "last" query in tens of milliseconds.
        """
        from iplotDataAccess.appDataAccess import AppDataAccess
        try:
            source = AppDataAccess.da.get_data_source(source_name)
            if getattr(source, "source_type", None) != "CODAC_UDA":
                return UNTOLD, None
            data = source.get_data(varname=variable, tsS="0", tsE=str(int(before_ns)), nbp=1, decType="last")
        except Exception as e:  # an archive that fails here must not undo what was applied
            logger.warning(f"Assistant: no latest sample of {source_name}:{variable}: {e!r}")
            return UNTOLD, None
        code, said = getattr(data, "errcode", None), str(getattr(data, "errdesc", "") or "")
        x = getattr(data, "xdata", None)
        # Only the answers UDA gives to exactly these cases; any other error says nothing about the data.
        if code == 0 and x is not None and len(x):
            answer = FOUND, int(x[-1])
        elif "variable does not exist" in said.lower():
            answer = UNKNOWN_VARIABLE, None
        elif "interval is empty" in said.lower():
            answer = NONE_BEFORE, None
        else:
            answer = UNTOLD, None
        logger.info(f"Assistant: latest sample of {source_name}:{variable} before {before_ns}: {code} {said!r} "
                    f"-> {answer[0]}")
        return answer

    def canvas_plot(self, row: int, col: int):
        return snapshot.canvas_plot(self.window.canvas, row, col)

    def plot_x_span_seconds(self, info):
        if info is None:
            return None
        plot = self.canvas_plot(info.row, info.col)
        try:
            axis = plot.axes[0]
            begin = axis.original_begin if axis.original_begin is not None else axis.begin
            end = axis.original_end if axis.original_end is not None else axis.end
            span = float(end) - float(begin)
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        if span <= 0:
            return None
        return span / 1e9 if abs(float(begin)) > 1e12 else span

    def _drawn_signal(self, uid: str):
        signals = self.window.canvasStack.currentWidget().get_signals(self.window.canvas)
        return next((s for s in signals if getattr(s, "uid", None) == uid), None)

    def sample_period_seconds(self, row) -> Optional[float]:
        """The median time between the samples of a drawn row, from the data already read; None if not drawn."""
        # By uid: a snapshot taken before rows were added or removed still points at the right one.
        uid = getattr(row, "uid", "") or self.uid_of(row.index)
        try:
            x = getattr(self._drawn_signal(uid), "x_data", None)
            if x is None or len(x) < 3:
                return None
            x = np.asarray(x, dtype=float)
            period = float(np.median(np.diff(x)))
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Assistant: no sample period for row {row.id}: {e}")
            return None
        if not np.isfinite(period) or period <= 0:
            return None
        return period / 1e9 if abs(x[0]) > 1e12 else period

    def drawn_outcome(self, uid: str) -> Optional[str]:
        """How the drawn signal of a row came out: NOT_COMPUTED (MINT could not work it out), EMPTY (no sample
        with a value to draw) or DRAWN. None while it is not drawn or its data are still being read."""
        try:
            signal = self._drawn_signal(uid)
            if signal is None:
                return self._failed_off_canvas(uid)
            result = signal.status_info.result
            if result == Result.FAIL:
                return NOT_COMPUTED
            if result != Result.SUCCESS:
                return None
            y = signal.y_data
            if y is None or len(y) == 0:
                return EMPTY
            drawable = np.isfinite(np.asarray(y, dtype=float))
            x = signal.x_data
            if x is not None and len(x) == len(drawable):
                drawable &= np.isfinite(np.asarray(x, dtype=float))
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Assistant: can't tell how {uid} came out: {e}")
            return None
        return DRAWN if drawable.any() else EMPTY

    def unreadable(self, uid: str) -> bool:
        return self.drawn_outcome(uid) == NOT_COMPUTED

    def _failed_off_canvas(self, uid: str) -> Optional[str]:
        """NOT_COMPUTED when the row's Status says reading or computing it failed: MINT leaves those signals off
        the canvas. None for anything else (not drawn, still being read)."""
        try:
            status = str(self.row_values(self._position(uid)).get("Status") or "")
        except ActionError:
            return None
        stage = status.partition(StatusInfo.sep)[0]
        return NOT_COMPUTED if stage in (Stage.DA, Stage.PROC, Stage.INIT) else None

    def name_of(self, uid: str) -> str:
        """A row as the table shows it: by its alias, else its variable."""
        values = self.row_values(self._position(uid))
        return str(values.get("Alias") or "").strip() or str(values.get("Variable") or "")

    def is_streaming(self) -> bool:
        return bool(self.window.streamerCfgWidget.is_activated())


    @staticmethod
    def check_expression(expr: str, is_expression: bool = False):
        from iplotProcessing.common import InvalidExpression
        from iplotProcessing.tools import Parser
        parser = Parser()
        try:
            parser.clear_expr()
            parser.set_expression(expr, is_expression=is_expression)
            if not parser.is_valid:
                raise InvalidExpression(expr)
        except InvalidExpression as e:
            logger.warning(f"Assistant: MINT rejects {expr!r}: {e}")
            raise ActionError("I couldn't build a formula MINT accepts for that. Could you ask in another way?")
        finally:
            parser.clear_expr()


    def _column(self, label: str) -> int:
        return list(self.model.get_dataframe().columns).index(label)

    def _position(self, uid: str) -> int:
        table = self.table()
        matches = table.index[table["uid"] == uid].tolist()
        if not matches:
            raise ActionError("That signal is no longer in the table.")
        return int(matches[0])

    def uid_of(self, index: int) -> str:
        return str(self.table().iat[index, self._column("uid")])

    def row_values(self, index: int) -> dict:
        row = self.table().iloc[index]
        return {label: ("" if row[label] is None else row[label]) for label in row.index}

    def copyable_values(self, uid: str) -> dict:
        return {k: v for k, v in self.row_values(self._position(uid)).items() if k not in NOT_COPIED}

    def _write(self, position: int, values: dict):
        model = self.model
        with model.activate_fast_mode():
            for label, value in values.items():
                if label in READ_ONLY:
                    continue
                model.setData(model.index(position, self._column(label)), value, Qt.ItemDataRole.EditRole)

    def set_cells(self, uid: str, values: dict) -> dict:
        position = self._position(uid)
        current = self.row_values(position)
        old = {label: current.get(label, "") for label in values}
        try:
            self._write(position, values)
        except Exception:
            self._write(position, old)
            raise
        return old

    def insert_row_at(self, position: int, values: dict) -> str:
        position = max(0, min(position, len(self.table().index)))
        self.model.insertRows(position, 1, QModelIndex())
        try:
            self._write(position, values)
        except Exception:
            self.model.removeRows(position, 1, QModelIndex())
            raise
        return self.uid_of(position)

    def insert_row_after(self, anchor_uid: str, values: dict) -> str:
        return self.insert_row_at(self._position(anchor_uid) + 1, values)

    def append_row(self, values: dict) -> str:
        return self.insert_row_at(len(self.table().index), values)

    def remove_row(self, uid: str) -> dict:
        position = self._position(uid)
        values = self.row_values(position)
        table = self.table()
        following = str(table.iat[position + 1, self._column("uid")]) if position + 1 < len(table.index) else ""
        self.model.removeRows(position, 1, QModelIndex())
        return {"position": position, "values": values, "before_uid": following}

    def restore_row(self, saved: dict) -> str:
        """Put a removed row back in front of the row that followed it, wherever that row is now."""
        table = self.table()
        following = saved.get("before_uid")
        matches = table.index[table["uid"] == following].tolist() if following else []
        position = int(matches[0]) if matches else saved["position"]
        return self.insert_row_at(position, saved["values"])


    def range_dict(self) -> dict:
        return self.window.dataRangeSelector.export_dict()

    def set_range_dict(self, values: dict):
        self.window.dataRangeSelector.import_dict(values)

    def time_range_fields(self) -> dict:
        """What the From/To fields hold, whichever mode is in use."""
        return self.window.dataRangeSelector.accessModes[0].to_dict()

    def set_time_range_fields(self, fields: dict):
        self.window.dataRangeSelector.accessModes[0].from_dict(fields)

    def show_time_range_ns(self, start_ns: int, end_ns: int):
        """From/To show this span, without leaving the mode in use."""
        self.window.dataRangeSelector.accessModes[0].set_from_ns(start_ns, end_ns)

    def set_time_range_ns(self, start_ns: int, end_ns: int):
        selector = self.window.dataRangeSelector
        selector.force_apply_canvas_range_ns(start_ns, end_ns)
        # The range is set by hand, not by a pulse; import_dict clears the pulse the same way.
        selector.accessModes[0].pulseUsed.setText("")

    def relative_auto_refresh(self) -> int:
        try:
            return int(self.window.dataRangeSelector.accessModes[2].properties().get("auto_refresh") or 0)
        except (AttributeError, IndexError, TypeError, ValueError):
            return 0


    def draw(self):
        self.window.draw_clicked()

    def open_statistics(self) -> bool:
        """Opens Statistics on the signals drawn; False when none is drawn."""
        if not self.window.canvasStack.currentWidget().get_signals(self.window.canvas):
            return False
        self.window.show_stats()
        return True

    def minimap(self, on: bool) -> Optional[bool]:
        """Turns the mini-map on or off. Whether it already was, or None when it can't be shown now."""
        action = self.window.toolBar.minimapAction
        if action.isChecked() == on:
            return True
        if not action.isEnabled():
            return None
        action.setChecked(on)
        return False

    def open_search_vars(self):
        self.window.sigCfgWidget.on_tree_view()

    def open_help(self, anchor: str):
        """The manual, at a section."""
        self.window._open_manual(anchor=anchor)

    def data_summary(self, uid: str) -> Optional[dict]:
        """The samples drawn for a row: how many, the first and last, the extremes and the mean, with the x of each.

        None when it isn't drawn. An envelope gives its min, max and average curves, as Statistics reads them.
        """
        signal = self._drawn_signal(uid)
        if signal is None:
            return None
        try:
            x = np.asarray(signal.x_data, dtype=float).ravel()
            store = getattr(signal, "data_store", None) or []
            if len(store) > 3 and np.asarray(store[2]).size and np.asarray(store[3]).size:
                low, high, mean = (np.asarray(store[i], dtype=float).ravel() for i in (1, 2, 3))
            else:
                low = high = mean = np.asarray(signal.y_data, dtype=float).ravel()
            n = min(x.size, low.size, high.size, mean.size)
            x, low, high, mean = x[:n], low[:n], high[:n], mean[:n]
            shown = np.isfinite(mean) & np.isfinite(x)
        except (TypeError, ValueError) as e:
            logger.debug(f"Assistant: no summary of {uid}: {e}")
            return None
        unit = str(getattr(signal.y_data, "unit", "") or "")
        if not shown.any():
            return {"count": 0, "unit": unit}
        where = np.flatnonzero(shown)
        first, last = where[0], where[-1]
        top = where[np.nanargmax(high[where])]
        bottom = where[np.nanargmin(low[where])]
        return {"count": int(where.size), "unit": unit, "first": (float(mean[first]), float(x[first])),
                "last": (float(mean[last]), float(x[last])), "max": (float(high[top]), float(x[top])),
                "min": (float(low[bottom]), float(x[bottom])), "mean": float(np.nanmean(mean[where]))}

    def is_hidden(self, uid: str) -> Optional[bool]:
        """Whether the drawn signal of a row is hidden from its legend; None when it isn't drawn."""
        signal = self._drawn_signal(uid)
        return None if signal is None else bool(getattr(signal, "hidden", False))

    def set_hidden(self, uid: str, hidden: bool):
        """Hides or shows a drawn signal as a click on its legend entry does, so Draw keeps it."""
        signal = self._drawn_signal(uid)
        if signal is None:
            raise ActionError(f"{self.name_of(uid)} isn't drawn any more, so I couldn't change it.")
        signal.hidden = hidden

    def refresh_plots(self):
        self.window.update_canvas_preferences()

    # The canvas, as its toolbar and its plots' menus work it: the same calls, so its undo history, the plots
    # sharing its time and the data read for a new view follow as they do for the mouse.

    def _canvas_widget(self):
        return self.window.canvasStack.currentWidget()

    def _impl(self, row: int, col: int):
        plot = self.canvas_plot(row, col)
        impl = self._canvas_widget()._get_impl_plot_for_plot(plot) if plot is not None else None
        if impl is None:
            raise ActionError("That plot isn't on the canvas now.")
        return plot, impl

    def x_is_date(self, row: int, col: int) -> Optional[bool]:
        """Whether a plot's x is dates (ns since the epoch) or seconds from the start of a pulse; None if not drawn."""
        plot = self.canvas_plot(row, col)
        try:
            return bool(plot.axes[0].is_date)
        except (AttributeError, IndexError, TypeError):
            return None

    def view(self, row: int, col: int) -> Optional[Tuple[float, float]]:
        """The x interval a plot shows: ns since the epoch, or s from the start of a pulse."""
        try:
            plot, impl = self._impl(row, col)
            begin, end = self._canvas_widget()._parser.get_oaw_axis_limits(impl, 0)
            return float(begin), float(end)
        except (ActionError, TypeError, ValueError):
            return None

    def set_view(self, row: int, col: int, begin: float, end: float, name: str = "Zoom"):
        """Shows [begin, end] of x as the zoom tool does: one step of the canvas's undo, the plots sharing its time
        follow, and the data of that interval is read."""
        widget = self._canvas_widget()
        _, impl = self._impl(row, col)
        widget.stage_view_lim_cmd(impl, name=name)
        widget._parser.set_oaw_axis_limits(impl, 0, (begin, end))
        while widget._staging_cmds:
            widget.commit_view_lim_cmd(impl)
        while widget._commitd_cmds:
            widget.push_view_lim_cmd()
        widget._flush_view()
        widget.stats(self.window.canvas)
        sync = getattr(widget, "_sync_minimap_viewport", None)
        if sync is not None:
            sync()

    def home(self):
        self.window.home()

    def view_history(self, redo: bool) -> bool:
        """The canvas's own undo or redo of its views (zoom, pan, Home); False when there is none."""
        widget = self._canvas_widget()
        if not (widget.can_redo() if redo else widget.can_undo()):
            return False
        (self.window.redo if redo else self.window.undo)()
        return True

    def focused(self) -> Optional[Tuple[int, int]]:
        """The plot shown alone on the canvas, as (row, col); None when all are."""
        plot = getattr(self._canvas_widget()._parser, "_focus_plot", None)
        return (plot.row, plot.col) if plot is not None else None

    def focus(self, row: Optional[int], col: Optional[int] = None):
        """One plot alone on the canvas, as "Focus on plot" does; None shows them all again."""
        widget = self._canvas_widget()
        if row is None:
            widget._full_screen_mode_off()
            return
        _, impl = self._impl(row, col)
        widget._full_screen_mode_on(impl)

    def rulers(self) -> List[dict]:
        """The rulers on the canvas: their name, plot (row, col), x and y as the data has them, and colour."""
        out = []
        for row_plots in self.window.canvas.plots or []:
            for plot in row_plots or []:
                for ruler in getattr(plot, "rulers", None) or []:
                    x, y = (list(ruler.xy) + [None, None])[:2]
                    out.append({"name": ruler.name, "plot": (plot.row, plot.col), "x": x, "y": y,
                                "color": ruler.color})
        return out

    def add_ruler(self, row: int, col: int, x: float, y: Optional[float] = None, name: str = None,
                  color: str = None) -> str:
        """A ruler at x (as the data has it), as a double-click in RULER mode drops one: named by the Rulers
        window, on every plot sharing the time axis. Returns its name."""
        widget = self._canvas_widget()
        plot, impl = self._impl(row, col)
        parser = widget._parser
        if y is None:
            low, high = parser.get_oaw_axis_limits(impl, 1)
            y = (float(low) + float(high)) / 2
        before = {r["name"] for r in self.rulers()}
        widget._add_ruler_at(impl, plot, parser.transform_value(impl, 0, x, inverse=True),
                             parser.transform_value(impl, 1, y, inverse=True), name=name, color=color)
        render = getattr(widget, "render", None)
        if render is not None:
            render()
        added = [r["name"] for r in self.rulers() if r["name"] not in before]
        return added[0] if added else (name or "")

    def remove_ruler(self, name: str, plot: Tuple[int, int]):
        self._canvas_widget()._remove_ruler_from_menu(name, plot)
        render = getattr(self._canvas_widget(), "render", None)
        if render is not None:
            render()

    def mouse_mode(self) -> str:
        return self._canvas_widget()._mmode

    def set_mouse_mode(self, mode: str):
        """A tool of the canvas toolbar (Canvas.MOUSE_MODE_*), as clicking its button: the button shows it."""
        self.window.toolBar._tool_actions[mode].trigger()

    def set_time_window(self, row: int, col: int):
        """The x interval a plot shows becomes the time range, as "Set as time window" does (not drawn yet)."""
        self.window.on_set_time_window(self.canvas_plot(row, col))

    def x_origin(self, row: int, col: int) -> Optional[float]:
        """Where the x of a plot started when drawn: ns since the epoch for dates, 0 for a pulse."""
        plot = self.canvas_plot(row, col)
        try:
            axis = plot.axes[0]
            if not axis.is_date:
                return 0.0
            begin = axis.original_begin if axis.original_begin is not None else axis.begin
            return float(begin)
        except (AttributeError, IndexError, TypeError, ValueError):
            return None

    def x_drawn(self, row: int, col: int) -> Optional[Tuple[float, float]]:
        """Where the x of a plot began and ended when drawn: ns since the epoch for dates, s from the start of a
        pulse (before it too)."""
        plot = self.canvas_plot(row, col)
        try:
            axis = plot.axes[0]
            begin = axis.original_begin if axis.original_begin is not None else axis.begin
            end = axis.original_end if axis.original_end is not None else axis.end
            return float(begin), float(end)
        except (AttributeError, IndexError, TypeError, ValueError):
            return None

    def reset_plot(self, row: int, col: int):
        """A plot back to its view when drawn, as its "Reset zoom/pan" does (the plots sharing its time too)."""
        _, impl = self._impl(row, col)
        self._canvas_widget().reset_plot_view(impl)

    def y_axis(self, row: int, col: int):
        """The y axis of a plot (its first), whose limits and label the preferences set."""
        plot = self.canvas_plot(row, col)
        axes = getattr(plot, "axes", None) or []
        y = axes[1] if len(axes) > 1 else None
        return y[0] if isinstance(y, (list, tuple)) and y else y

    def drawn_signal(self, uid: str):
        return self._drawn_signal(uid)

    def canvas(self):
        return self.window.canvas

    def last_canvas_command(self):
        """The last step of the canvas's own undo history (a zoom, a shift...); None when there is none."""
        stack = getattr(self._canvas_widget()._parser._hm, "_undo_stack", None)
        return stack[-1] if stack else None

    def undo_canvas_command(self, command) -> bool:
        """Undoes a step of the canvas's history if it is still the last one; False otherwise."""
        if command is None or self.last_canvas_command() is not command:
            return False
        self.window.undo()
        return True

    def shift_signal(self, uid: str, dx: float, dy: float, copy: bool):
        """Moves a drawn signal in x (the axis's units) and y as the DIST window's Shift does; a copy keeps it."""
        signal = self._drawn_signal(uid)
        if signal is None:
            raise ActionError(f"{self.name_of(uid)} isn't drawn, so I can't shift it.")
        if getattr(signal, "envelope", False):
            raise ActionError("An envelope can't be shifted.")
        self.window._on_signal_shift_requested(uid, "", "", "", dx, dy, copy)

    def theme(self) -> str:
        from mint.gui import mtAppearance
        return str(getattr(mtAppearance, "_theme", None) or
                   QSettings().value(mtAppearance.THEME_KEY, mtAppearance.THEME_NONE))

    def set_theme(self, name: str):
        """A theme as the View > Appearance > Theme menu sets it, its tick included."""
        from mint.gui import mtAppearance
        for menu in self.window.menuBar().findChildren(mtAppearance.MTAppearanceMenu):
            for action in menu._theme_menu.actions():
                if action.text() == name:
                    action.trigger()
                    return
        mtAppearance.apply_theme(name)

    def open_window(self, name: str) -> bool:
        """A window or dialog of MINT, where the user finishes what they asked; False when it can't open now."""
        window = self.window
        if name == "export":
            window.export_clicked()
        elif name == "image":
            window.save_canvas_image()
        elif name == "csv":
            window.on_export_data()
        elif name == "save_workspace":
            window.on_export()
        elif name == "open_workspace":
            window.on_import()
        elif name == "preferences":
            window.toolBar.configureAction.trigger()
        elif name == "rulers":
            ruler_window = getattr(self._canvas_widget(), "_ruler_window", None)
            if ruler_window is None:
                return False
            ruler_window.show()
            ruler_window.raise_()
        else:
            return False
        return True

    def detached(self) -> bool:
        return self.window.toolBar.detachAction.text() == "Reattach"

    def detach(self, on: bool):
        if self.detached() != on:
            self.window.toolBar.detachAction.trigger()


    def data_source_choices(self) -> List[str]:
        """The data sources a row can use here: those the table checks its DS cells against."""
        return list(getattr(self.model, "data_sources", None) or [])

    def data_source_names(self) -> List[str]:
        from iplotDataAccess.appDataAccess import AppDataAccess
        return list(getattr(AppDataAccess.da, "ds_list", None) or {})

    def default_data_source(self):
        from iplotDataAccess.appDataAccess import AppDataAccess
        name = AppDataAccess.da.get_default_ds_name()
        return name, AppDataAccess.da.get_data_source(name)

    def data_source(self, name: str):
        from iplotDataAccess.appDataAccess import AppDataAccess
        source = AppDataAccess.da.get_data_source(name)
        connected = getattr(source, "is_connected", None)
        if source is None or (connected is not None and not connected()):
            raise ActionError(f"{name} isn't connected right now, so I can't search it. "
                              "Check it in Search Vars, or try another data source.")
        return source

    def search_variables(self, words, request: str = "", source: str = "") -> VariableSearch:
        """Variables of the named data source (else ``source``, else the default) whose name or HMI description holds
        all the words.

        A code-like word ("CRYO", "System1") is first tried as the tree group names start with, then anywhere in names.
        """
        words = [w for w in words if w]
        name = _named_source(words, request, self.data_source_names()) or \
            _named_source([source], "", self.data_source_names())
        if name:
            words = [w for w in words if w.lower() != name.lower()]
            source = self.data_source(name)
        else:
            name, source = self.default_data_source()
            if source is None:
                raise ActionError("MINT isn't connected to any data source yet, so I can't search for variables.")
        if not words:
            raise ActionError(f"What should I look for in {name}? A system such as CRYO, or part of a name.")
        names = [w for w in words if files.NAME.fullmatch(w)]
        if len(names) > 1:
            return self._exactly(name, source, names)
        group = _group(words, request)
        if group:
            rest = [w for w in words if w.lower() != group.lower()]
            found = self._matching(name, source, f"{re.escape(group)}{SEPARATOR}.*", rest, group)
            if found:
                return VariableSearch(name, found[:MAX_SEARCH_RESULTS], len(found), rest, group)
        found = self._matching(name, source, _server_pattern(words), words)
        return VariableSearch(name, found[:MAX_SEARCH_RESULTS], len(found), words)

    def _exactly(self, name, source, names) -> VariableSearch:
        """These full names in the source, each looked up on its own; those it hasn't are missing."""
        found, missing = [], []
        for wanted in names:
            hits = [hit for hit in self._matching(name, source, re.escape(wanted), [wanted]) if hit[0] == wanted]
            found += [hit for hit in hits if hit not in found]
            if not hits:
                missing.append(wanted)
        return VariableSearch(name, found[:MAX_SEARCH_RESULTS], len(found), list(names), missing=missing)

    def search_codes(self, codes) -> VariableSearch:
        """Variables of the default data source for each tag (MT0021): those with that very tag, else all holding it."""
        name, source = self.default_data_source()
        if source is None:
            raise ActionError("MINT isn't connected to any data source yet, so I can't search for variables.")
        found, total, missing = [], 0, []
        for code in codes:
            holding = self._matching(name, source, f".*{re.escape(code)}.*", [code])
            hits = [hit for hit in holding if hit[0].split(":")[-1] == code] or holding
            if not hits:
                missing.append(code)
            total += len(hits)
            found += [hit for hit in hits if hit not in found]
        return VariableSearch(name, found[:MAX_SEARCH_RESULTS], max(total, len(found)), list(codes), missing=missing)

    def _matching(self, name, source, pattern, words, group=""):
        """The source's variables for the server pattern, ranked by how many of the words they hold.

        Only those holding them all when there are any; the HMI descriptions count as part of the name.
        """
        lowered = [w.lower() for w in words]
        # "temperature" also finds the temperature sensors by their code (MT..., -TT-), as in the hints.
        meant = {w: prompt.SAID.get(w) for w in lowered}

        def holds(var, description, word):
            text = f"{var} {description}".lower()
            if word in text:
                return True
            meaning = meant.get(word)
            return bool(meaning) and (meaning in text
                                      or prompt.measures(RowInfo(id="", index=0, variable=var)) == meaning)

        found = {}
        try:
            # Positional: the UDA source calls it 'pattern' and the CSV source 'patt'.
            names = source.get_var_list(pattern) if hasattr(source, "get_var_list") else \
                _leaves(source.get_var_dict(pattern=pattern) or {})
            for var in names or []:
                found[str(var)] = ""
        except Exception as e:
            logger.warning(f"Assistant variable search failed: {e}")
            raise ActionError(f"I couldn't search {name} just now. Try again in a moment, or use Search Vars.")
        getter = getattr(source, "get_hmi_var_dict", None)
        if getter is not None:
            starts = re.compile(f"{re.escape(group)}{SEPARATOR}") if group else None
            try:
                for var, meta in (getter() or {}).items():
                    if starts is not None and not starts.match(var):
                        continue
                    if all(holds(var, meta.get("description", ""), w) for w in lowered):
                        found[var] = meta.get("description", "")
            except Exception as e:
                logger.debug(f"Assistant: no HMI metadata for the search: {e}")

        def score(item):
            return (-sum(holds(item[0], item[1], w) for w in lowered), len(item[0]))

        ranked = sorted(found.items(), key=score)
        matching = [item for item in ranked if all(holds(item[0], item[1], w) for w in lowered)]
        return matching or ranked
