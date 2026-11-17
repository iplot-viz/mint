"""What the canvas toolbar, the plots' menus and the Preferences window do, as cards of the planner: the view (zoom,
pan, Home, the canvas's undo, focus), rulers, tools, the time window, detach, the settings of a plot, a signal and the
canvas, shifting a signal, and the theme. Each is done the way MINT does it from its own buttons (see workspace.py).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from mint.assistant import actions as _actions
from mint.assistant import settings, when
# Imported by actions.py before its own end: what is defined after its Planner is reached through _actions.
from mint.assistant.actions import FIRST_YEAR, LAST_YEAR, ActionError, Change, _capital, _listed
from mint.assistant.commands import Command

SECONDS = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "d": 86400}
TOOL_MODES = {"select": "MM_SELECT", "crosshair": "MM_CROSSHAIR", "pan": "MM_PAN", "zoom": "MM_ZOOM",
              "dist": "MM_DIST", "marker": "MM_MARKER", "ruler": "MM_RULER"}
TOOL_WORDS = {"select": "Select", "crosshair": "Crosshair", "pan": "Pan", "zoom": "Zoom",
              "dist": "Distance (DIST)", "marker": "Marker", "ruler": "Ruler"}
THEME_NAMES = {"dark": "Dark", "light": "Light", "auto": "Auto", "none": "None"}
EXTREME_WORDS = {"max": "maximum", "min": "minimum", "first": "first sample", "last": "last sample"}


class CanvasActions:
    """Mixed into the Planner: self.ws (the workspace), self.snap (its snapshot), self._plot_info, self._row and
    self._name are the planner's."""

    # Where and when, as the plots have it

    def _drawn_plots(self, ids) -> list:
        plots = self.snap.plots if ids in ([], ["all"]) else [self._plot_info(pid) for pid in ids]
        if not plots:
            raise ActionError("There are no plots yet.")
        for plot in plots:
            if self.ws.canvas_plot(plot.row, plot.col) is None:
                if self._unreadable([r for r in self.snap.rows if r.plot == plot.id]):
                    raise ActionError(f"Nothing is drawn in {self.snap.place(plot.id)}: the data of its signals "
                                      f"couldn't be read, as their Status says.")
                raise ActionError(f"{_capital(self.snap.place(plot.id))} isn't drawn yet. Click Draw, then ask me "
                                  f"again.")
        return plots

    def _where(self, ids, plots) -> str:
        return "all plots" if ids in ([], ["all"]) or len(plots) == len(self.snap.plots) > 1 else \
            " and ".join(self.snap.place(p.id) for p in plots)

    def _x(self, plot, words) -> Tuple[float, str]:
        """An x of a plot from a command's moment: a time from the start of what is drawn (of the pulse, in a
        pulse) with its unit, or a date and time; and how a card says it."""
        is_date = self.ws.x_is_date(plot.row, plot.col)
        origin = self.ws.x_origin(plot.row, plot.col)
        if len(words) == 2:
            seconds = float(words[0]) * SECONDS[words[1]]
            if not is_date:
                return seconds, f"{words[0]} {words[1]}"
            return origin + seconds * 1e9, f"{words[0]} {words[1]}"
        if not is_date:
            raise ActionError("This plot counts from the start of the pulse: give times from it, like 40 to 60 s.")
        text = words[0].strip()
        try:
            if len(text) <= 8 and ":" in text:  # a time of the day drawn
                day = datetime.fromtimestamp(origin / 1e9, timezone.utc)
                clock = datetime.strptime(text, "%H:%M:%S" if text.count(":") == 2 else "%H:%M")
                moment = day.replace(hour=clock.hour, minute=clock.minute, second=clock.second, microsecond=0)
            else:
                moment = _actions._parse_when(text)
        except ValueError:
            raise ActionError("I couldn't read that time. Could you write it like 07:20 or 2026-11-03 07:20?")
        if not FIRST_YEAR <= moment.year <= LAST_YEAR:
            raise ActionError(f"Dates must be between {FIRST_YEAR} and {LAST_YEAR}.")
        return float(_actions._ns(moment)), when.at(moment, self.snap.now)

    def _span_words(self, plot, start: float, end: float, said: Tuple[str, str], words) -> str:
        if len(words) == 3:  # times from the start
            what = "the pulse" if not self.ws.x_is_date(plot.row, plot.col) else "what is drawn"
            return f"{said[0].split()[0]} to {said[1]} from the start of {what}"
        if self.ws.x_is_date(plot.row, plot.col):
            moments = [datetime.fromtimestamp(v / 1e9, timezone.utc) for v in (start, end)]
            return when.span(moments[0], moments[1], self.snap.now)
        return f"{said[0]} to {said[1]}"

    def _last(self, plot, number: str, unit: str) -> Tuple[float, float, str]:
        """The last stretch of what a plot drew, as a zoom from its x and to its x, and how a card says it."""
        amount = float(number)
        if amount <= 0:
            raise ActionError("Give how much of the end to show, like the last 10 min.")
        start, end = self.ws.x_drawn(plot.row, plot.col) or (None, None)
        if start is None or end <= start:
            raise ActionError(f"I can't tell where {self.snap.place(plot.id)} ends. Click Draw, then ask me again.")
        dates = self.ws.x_is_date(plot.row, plot.col)
        length = amount * SECONDS[unit] * (1e9 if dates else 1)
        what = "what is drawn" if dates else "the pulse"
        return max(start, end - length), end, f"the last {number} {unit} of {what}"

    def _views_change(self, plots, set_new, line: str, name: str = "Zoom") -> Change:
        """A change of what the plots show; undo shows again what they showed."""
        ws, before = self.ws, []

        def do():
            before.clear()
            before.extend((p.row, p.col, ws.view(p.row, p.col)) for p in plots)
            set_new()

        def undo():
            for row, col, view in before:
                if view is not None:
                    ws.set_view(row, col, view[0], view[1], name="Zoom")

        return Change([line], do, undo)

    # The view

    def _zoom(self, cmd: Command, proposal) -> str:
        plots = self._drawn_plots(cmd.ids)
        first = plots[0]
        ws = self.ws
        if cmd.words[0] == "last":
            a, b, span = self._last(first, cmd.words[1], cmd.words[2])
        else:
            unit = cmd.words[2:]
            a, said_a = self._x(first, [cmd.words[0]] + unit)
            b, said_b = self._x(first, [cmd.words[1]] + unit)
            if b <= a:
                raise ActionError("The end of a zoom must be after its start.")
            span = self._span_words(first, a, b, (said_a, said_b), cmd.words)

        def set_new():
            for p in plots:
                ws.set_view(p.row, p.col, a, b)

        proposal.changes.append(self._views_change(plots, set_new, f"Zoom {self._where(cmd.ids, plots)}: {span}"))
        return "Zoom"

    def _pan(self, cmd: Command, proposal) -> str:
        plots = self._drawn_plots(cmd.ids)
        amount, unit = float(cmd.words[0]), cmd.words[1]
        if amount == 0:
            raise ActionError("Moving the view by nothing changes nothing.")
        ws = self.ws

        def set_new():
            # Where each goes, before any moves: the plots sharing the time axis follow the first one.
            targets = []
            for p in plots:
                view = ws.view(p.row, p.col)
                if view is not None:
                    delta = amount * SECONDS[unit] * (1e9 if ws.x_is_date(p.row, p.col) else 1)
                    targets.append((p, view[0] + delta, view[1] + delta))
            for p, begin, end in targets:
                ws.set_view(p.row, p.col, begin, end, name="Pan")

        way = "later" if amount > 0 else "earlier"
        size = f"{cmd.words[0].lstrip('-')} {unit}"
        line = f"Move the view of {self._where(cmd.ids, plots)} {size} {way}"
        proposal.changes.append(self._views_change(plots, set_new, line, name="Pan"))
        return "Pan"

    def _home(self, cmd: Command, proposal) -> str:
        plots = self._drawn_plots(cmd.ids)
        ws = self.ws
        if cmd.ids:
            def set_new():
                for p in plots:
                    ws.reset_plot(p.row, p.col)
            line = f"{_capital(self._where(cmd.ids, plots))} back to the view it was drawn with"
        else:
            set_new = ws.home
            line = "All plots back to the view they were drawn with (Home)"
        proposal.changes.append(self._views_change(plots if cmd.ids else self._drawn_plots([]), set_new, line))
        return "Home"

    def _view(self, cmd: Command, proposal) -> str:
        redo = cmd.words == ["redo"]
        widget_has = self.ws._canvas_widget().can_redo() if redo else self.ws._canvas_widget().can_undo()
        if not widget_has:
            raise ActionError("There is no zoom or pan to redo." if redo else "There is no zoom or pan to undo.")
        ws = self.ws
        line = "Redo the last zoom or pan undone on the canvas" if redo else \
            "Undo the last zoom, pan or Home on the canvas"
        proposal.changes.append(Change([line], lambda: ws.view_history(redo), lambda: ws.view_history(not redo)))
        return "Canvas undo" if not redo else "Canvas redo"

    def _focus(self, cmd: Command, proposal) -> str:
        ws, now = self.ws, self.ws.focused()
        if cmd.words == ["off"]:
            if now is None:
                raise ActionError("All the plots are shown already.")
            line, target = "Show all the plots again", None
        else:
            plot, = self._drawn_plots(cmd.ids)
            if now == (plot.row, plot.col):
                raise ActionError(f"{_capital(self.snap.place(plot.id))} is the only one shown already.")
            line, target = f"Show only {self.snap.place(plot.id)}, on the whole canvas", (plot.row, plot.col)

        def do():
            if ws.focused() is not None and target is not None:
                ws.focus(None)
            ws.focus(*target) if target else ws.focus(None)

        def undo():
            if ws.focused() is not None:
                ws.focus(None)
            if now is not None:
                ws.focus(*now)

        proposal.changes.append(Change([line], do, undo))
        return "Focus"

    # Rulers, tools, the time window, the canvas's window

    def _ruler(self, cmd: Command, proposal) -> str:
        ws = self.ws
        if cmd.words == ["off"]:
            rulers = ws.rulers()
            if not rulers:
                raise ActionError("There are no rulers on the canvas.")

            def do():
                for r in rulers:
                    ws.remove_ruler(r["name"], r["plot"])

            def undo():
                for r in rulers:
                    ws.add_ruler(r["plot"][0], r["plot"][1], r["x"], r["y"], name=r["name"], color=r["color"])

            names = _listed([r["name"] for r in rulers])
            proposal.changes.append(Change([f"Remove the ruler{'s' if len(rulers) > 1 else ''} {names}"], do, undo))
            return "Rulers"
        target = cmd.ids[0]
        if target.startswith("r"):
            row = self._row(target)
            plot_info = self.snap.plot(row.plot) if row.plot else None
            if plot_info is None:
                raise ActionError(f"{self._name(row)} isn't in a plot.")
            self._drawn_plots([plot_info.id])
            summary = ws.data_summary(row.uid)
            if not summary or not summary.get("count"):
                raise ActionError(f"{self._name(row)} has no sample drawn to put a ruler on.")
            value, x = summary[cmd.words[0]]
            y = value
            unit = f" {summary['unit']}" if summary.get("unit") else ""
            moment = self._moment_words(plot_info, x)
            line = (f"A ruler on the {EXTREME_WORDS[cmd.words[0]]} of {self._name(row)}: "
                    f"{recipes_number(value)}{unit}, {moment}")
        else:
            plot_info, = self._drawn_plots([target])
            x, said = self._x(plot_info, cmd.words)
            y = None
            moment = self._moment_words(plot_info, x) if len(cmd.words) == 1 else f"{said} from the start"
            line = f"A ruler on {self.snap.place(plot_info.id)}, {moment}"
        added = []

        def do():
            added.clear()
            added.append(ws.add_ruler(plot_info.row, plot_info.col, x, y))

        def undo():
            for name in added:
                ws.remove_ruler(name, (plot_info.row, plot_info.col))

        proposal.changes.append(Change([line], do, undo))
        return "Ruler"

    def _moment_words(self, plot, x: float) -> str:
        if self.ws.x_is_date(plot.row, plot.col):
            return when.at(datetime.fromtimestamp(x / 1e9, timezone.utc), self.snap.now)
        return f"{recipes_number(x)} s"

    def _tool(self, cmd: Command, proposal) -> str:
        ws, mode = self.ws, TOOL_MODES[cmd.words[0]]
        before = ws.mouse_mode()
        if before == mode:
            raise ActionError(f"The {TOOL_WORDS[cmd.words[0]]} tool is on already.")
        proposal.changes.append(Change([f"{TOOL_WORDS[cmd.words[0]]} tool on, in the canvas toolbar"],
                                       lambda: ws.set_mouse_mode(mode), lambda: ws.set_mouse_mode(before)))
        return "Tool"

    def _timewindow(self, cmd: Command, proposal) -> str:
        plot, = self._drawn_plots(cmd.ids[:1] or [self.snap.plots[0].id] if self.snap.plots else [])
        ws, before = self.ws, {}
        view = ws.view(plot.row, plot.col)
        if view is None:
            raise ActionError(f"{_capital(self.snap.place(plot.id))} isn't drawn yet.")
        if ws.x_is_date(plot.row, plot.col):
            shown = when.span(*(datetime.fromtimestamp(v / 1e9, timezone.utc) for v in view), self.snap.now)
        else:
            shown = f"{recipes_number(view[0])} to {recipes_number(view[1])} s from the start of the pulse"

        def do():
            before.clear()
            before.update(range=ws.range_dict(), fields=ws.time_range_fields())
            ws.set_time_window(plot.row, plot.col)

        def undo():
            if before:
                ws.set_range_dict(before["range"])
                ws.set_time_range_fields(before["fields"])

        proposal.changes.append(Change([f"The time range becomes what {self.snap.place(plot.id)} shows: {shown}"],
                                       do, undo, needs_draw=True))
        return "Time window"

    def _detach(self, cmd: Command, proposal) -> str:
        ws, on = self.ws, cmd.words == ["on"]
        if ws.detached() == on:
            raise ActionError("The canvas is in its own window already." if on else
                              "The canvas is in the main window already.")
        line = "The canvas in a window of its own" if on else "The canvas back in the main window"
        proposal.changes.append(Change([line], lambda: ws.detach(on), lambda: ws.detach(not on)))
        return "Detach" if on else "Reattach"

    # Preferences

    def _settings_change(self, targets, catalogue, params, line: str) -> Change:
        """Properties set on objects found again at each step (a Draw replaces them), put back by undo."""
        values = {}
        for key, given in params.items():
            try:
                values[key] = settings.parse_value(catalogue, key, given)
            except ValueError as e:
                raise ActionError(f"{str(e)[0].upper()}{str(e)[1:]}.")
        old = []

        def found(find, key):
            obj = find(key)
            if obj is None:
                raise ActionError("That isn't drawn any more, so I couldn't change it.")
            return obj

        def do():
            old.clear()
            for find in targets:
                for key, (setting, value) in values.items():
                    obj = found(find, key)
                    old.append((find, key, setting.prop, getattr(obj, setting.prop, None)))
                    setattr(obj, setting.prop, value)
                    if setting.prop == "color":
                        old.append((find, key, "new_color", getattr(obj, "new_color", False)))
                        obj.new_color = True  # Draw keeps a colour only when it was set

        def undo():
            # A Draw since builds new objects: they are found again where they are.
            for find, key, prop, value in reversed(old):
                setattr(found(find, key), prop, value)

        return Change([line], do, undo, needs_refresh=True)

    @staticmethod
    def _said(catalogue, params) -> str:
        return ", ".join(catalogue[k].said(v) if k in catalogue else f"{k} {v}" for k, v in params.items())

    def _y_limits_show_data(self, plots, params):
        """Y limits must leave some of the data drawn in sight: an axis showing 1e3 in its corner reads "0 to 10"
        where the values go up to 10000."""
        low = float(params["ymin"]) if "ymin" in params else float("-inf")
        high = float(params["ymax"]) if "ymax" in params else float("inf")
        if low >= high:
            raise ActionError("The top of the y axis must be above its bottom.")
        for plot in plots:
            summaries = [self.ws.data_summary(r.uid) for r in self.snap.rows if r.plot == plot.id]
            values = [v for s in summaries if s and s.get("count") for v in (s["min"][0], s["max"][0])]
            if values and (high < min(values) or low > max(values)):
                raise ActionError(f"The signals of {self.snap.place(plot.id)} go from {recipes_number(min(values))} "
                                  f"to {recipes_number(max(values))}: nothing of them would show between "
                                  f"{params.get('ymin', 'the bottom')} and {params.get('ymax', 'the top')}.")

    def _plot(self, cmd: Command, proposal) -> str:
        plots = self._drawn_plots(cmd.ids)
        if "ymin" in cmd.params or "ymax" in cmd.params:
            self._y_limits_show_data(plots, cmd.params)
        ws = self.ws
        positions = [(p.row, p.col) for p in plots]

        def finder(row, col):
            def find(key):
                return ws.y_axis(row, col) if key in settings.AXIS_KEYS else ws.canvas_plot(row, col)
            return find

        line = f"{_capital(self._where(cmd.ids, plots))}: {self._said(settings.PLOT, cmd.params)}"
        proposal.changes.append(self._settings_change([finder(r, c) for r, c in positions], settings.PLOT,
                                                      cmd.params, line))
        return "Plot settings"

    def _style(self, cmd: Command, proposal) -> str:
        rows = [self._row(row_id) for row_id in cmd.ids]
        ws = self.ws
        for row in rows:
            if ws.drawn_signal(row.uid) is None:
                if self._unreadable([row]):
                    raise ActionError(f"{self._name(row)} has nothing drawn: its data couldn't be read, as the "
                                      f"Status says.")
                raise ActionError(f"{self._name(row)} isn't drawn. Click Draw, then ask me again.")
        finders = [(lambda uid: (lambda key: ws.drawn_signal(uid)))(row.uid) for row in rows]
        names = _listed([self._name(row) for row in rows])
        said = self._said(settings.SIGNAL, {k: settings.color_name(v) if k == "color" else v
                                            for k, v in cmd.params.items()})
        proposal.changes.append(self._settings_change(finders, settings.SIGNAL, cmd.params, f"{names}: {said}"))
        return "Signal settings"

    def _canvas(self, cmd: Command, proposal) -> str:
        ws = self.ws
        line = f"The whole canvas: {self._said(settings.CANVAS, cmd.params)}"
        proposal.changes.append(self._settings_change([lambda key: ws.canvas()], settings.CANVAS, cmd.params, line))
        return "Canvas settings"

    # A signal moved, and MINT's look

    def _shift(self, cmd: Command, proposal) -> str:
        row = self._row(cmd.ids[0])
        ws = self.ws
        if ws.drawn_signal(row.uid) is None:
            raise ActionError(f"{self._name(row)} isn't drawn. Click Draw, then ask me again.")
        plot = self.snap.plot(row.plot) if row.plot else None
        copy = "copy" in cmd.flags
        if cmd.words[0] == "time":
            amount, unit = float(cmd.words[1]), cmd.words[2]
            is_date = plot is not None and ws.x_is_date(plot.row, plot.col)
            dx, dy = amount * SECONDS[unit] * (1e9 if is_date else 1), 0.0
            said = f"{cmd.words[1].lstrip('-')} {unit} {'later' if amount > 0 else 'earlier'}"
        else:
            dx, dy = 0.0, float(cmd.words[1])
            said = f"{cmd.words[1].lstrip('-')} {'up' if dy > 0 else 'down'}"
        if dx == 0 and dy == 0:
            raise ActionError("Shifting by nothing changes nothing.")
        done = []

        def do():
            done.clear()
            ws.shift_signal(row.uid, dx, dy, copy)
            done.append(ws.last_canvas_command())

        def undo():
            if not (done and ws.undo_canvas_command(done[0])) and not copy:
                ws.shift_signal(row.uid, -dx, -dy, False)

        what = f"A copy of {self._name(row)}, shifted" if copy else f"{self._name(row)} shifted"
        proposal.changes.append(Change([f"{what} {said}"], do, undo))
        return "Shift"

    def _theme(self, cmd: Command, proposal) -> str:
        ws, name = self.ws, THEME_NAMES[cmd.words[0]]
        before = ws.theme()
        if before == name:
            raise ActionError(f"The theme is {name} already.")
        words = {"Dark": "dark colours", "Light": "the light theme", "Auto": "the colours of the system (Auto)",
                 "None": "the default look"}[name]
        proposal.changes.append(Change([f"MINT in {words}"], lambda: ws.set_theme(name),
                                       lambda: ws.set_theme(before)))
        return "Theme"


def recipes_number(value: float) -> str:
    from mint.assistant import recipes
    return recipes.number(round(value, 4) if abs(value) < 1e6 else value)
