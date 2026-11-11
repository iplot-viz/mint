"""The assistant's only door into MINT's main window."""
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QModelIndex, Qt

from iplotlib.interface.iplotSignalAdapter import Result, Stage, StatusInfo
from iplotLogging import setupLogger
from mint.assistant import prompt, snapshot
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
        return snapshot.build(self.table(), self.selected_indices(), canvas=self.window.canvas, range_text=text,
                              range_seconds=seconds, pulse_mode=pulse_mode, last_action=last_action)

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
            return f"pulse {pulses}", seconds if seconds and seconds > 0 else None, True
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

    def refresh_plots(self):
        self.window.update_canvas_preferences()


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

    def search_variables(self, words, request: str = "") -> VariableSearch:
        """Variables of the named (else the default) data source whose name or HMI description holds all the words.

        A code-like word ("CRYO", "System1") is first tried as the tree group names start with, then anywhere in names.
        """
        words = [w for w in words if w]
        name = _named_source(words, request, self.data_source_names())
        if name:
            words = [w for w in words if w.lower() != name.lower()]
            source = self.data_source(name)
        else:
            name, source = self.default_data_source()
            if source is None:
                raise ActionError("MINT isn't connected to any data source yet, so I can't search for variables.")
        if not words:
            raise ActionError(f"What should I look for in {name}? A system such as CRYO, or part of a name.")
        group = _group(words, request)
        if group:
            rest = [w for w in words if w.lower() != group.lower()]
            found = self._matching(name, source, f"{re.escape(group)}{SEPARATOR}.*", rest, group)
            if found:
                return VariableSearch(name, found[:MAX_SEARCH_RESULTS], len(found), rest, group)
        found = self._matching(name, source, _server_pattern(words), words)
        return VariableSearch(name, found[:MAX_SEARCH_RESULTS], len(found), words)

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
