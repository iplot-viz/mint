"""Assistant commands applied to a real main window, and undone."""
import importlib.util
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import pandas as pd
from PySide6.QtCore import Qt
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.assistant import commands, files
from mint.assistant.actions import MAX_ADDED, ActionError, MissingValue, Planner
from mint.assistant.workspace import MintWorkspace
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

COLUMNS = ["DS", "Variable", "Stack", "Alias", "y", "Envelope", "Plot type"]


def build_window() -> MTMainWindow:
    data_sources = AccessHelper.da.get_connected_data_source_names()
    win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version="test", data_sources=data_sources,
                       blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl="matplotlib")
    win.sigCfgWidget.model.set_dataframe(pd.DataFrame({
        "DS": ["csv", "csv", "other", "csv"],
        "Variable": ["MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR2", "CRYO:MT0001", "MAG-MCTB-F1:VAR3"],
        "Stack": ["1.1", "1.1", "2.1", "3.1"],
        "Alias": ["pirani", "", "", ""],
        "y": ["", "", "", "${self}.data * 1000"],
        "Envelope": ["", "", "", "1"],
        "Plot type": ["PlotXY"] * 4,
    }))
    win.dataRangeSelector.import_dict({"mode": MTGenericAccessMode.RELATIVE_TIME, "relative": 2, "base": 3600,
                                       "auto_refresh": 5})
    return win


class _WindowCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        self.win = build_window()
        self.ws = MintWorkspace(self.win)

    def tearDown(self):
        self.win.close()

    def table(self):
        return self.ws.table()[COLUMNS + ["uid", "Comment"]].copy()

    def plan(self, text):
        return Planner(self.ws, self.ws.snapshot()).plan(commands.parse(text))

    def apply_and_undo(self, text):
        before = self.table()
        proposal = self.plan(text)
        proposal.apply()
        after = self.table()
        self.assertEqual(proposal.undo(), [])
        pd.testing.assert_frame_equal(self.table().reset_index(drop=True), before.reset_index(drop=True))
        return proposal, after


class AssistantActionsTest(_WindowCase):
    def test_snapshot_reads_rows_plots_and_range(self):
        snap = self.ws.snapshot()
        self.assertEqual([r.id for r in snap.rows], ["r1", "r2", "r3", "r4"])
        self.assertEqual([(r.id, r.plot) for r in snap.rows], [("r1", "p1"), ("r2", "p1"), ("r3", "p2"), ("r4", "p3")])
        self.assertEqual([(p.id, p.row, p.col) for p in snap.plots], [("p1", 1, 1), ("p2", 2, 1), ("p3", 3, 1)])
        self.assertEqual(snap.range_text, "last 2 hours")
        self.assertEqual(snap.range_seconds, 7200)

    def test_process_adds_a_processed_copy_after_the_row(self):
        proposal, after = self.apply_and_undo("process r1 moving_average seconds=30")
        self.assertEqual(len(after), 5)
        new = after.iloc[1]
        self.assertEqual((new["DS"], new["Variable"], new["Stack"]), ("csv", "MAG-MCTB-F1:VAR1", "1.1"))
        self.assertEqual(new["Alias"], "pirani_avg_30s")
        self.assertIn("uniform_filter1d(${self}.data, size=", new["y"])
        self.assertTrue(new["Comment"].startswith("Assistant: moving average over 30 s"))
        self.assertNotEqual(new["uid"], after.iloc[0]["uid"])

    def test_cards_speak_plainly(self):
        # Names and places as the user sees them on screen; no r1/p1, no jargon.
        self.assertEqual(self.plan("process r1 moving_average window=15min").lines,
                         ["pirani — smoothed with a 15 min average → new signal pirani_avg_900s, in the top plot"])
        self.win.canvas.plots = [[PlotXY(row=r, col=1) for r in (1, 2, 3)]]
        self.assertEqual(self.plan("plot p2 log=on").lines, ["The second plot from the top: log scale on"])
        self.assertEqual(self.plan("move r3 to p3").lines, ["Move CRYO:MT0001 to the bottom plot"])
        self.assertEqual(self.plan("move r1 r2 to new").lines,
                         ["Move pirani and MAG-MCTB-F1:VAR2 together to a new plot"])
        self.assertEqual(self.plan("remove r2").lines, ["Remove MAG-MCTB-F1:VAR2 from the table"])
        self.assertEqual(self.plan("process r2 scale factor=3.6").lines,
                         ["MAG-MCTB-F1:VAR2 — values × 3.6 → new signal VAR2_x3p6, in the top plot"])
        self.assertTrue(self.plan("process r2 scale offset=-2").lines[0].startswith("MAG-MCTB-F1:VAR2 — values × 1 − 2 →"))
        self.assertEqual(self.plan("combine divide r2 r1").lines,
                         ["New signal VAR2_over_pirani = MAG-MCTB-F1:VAR2 over pirani, in a new plot"])
        self.assertEqual(self.plan("range last 1 hours").lines, ["Time range: the last hour"])
        self.assertEqual(self.plan("range last 6 hours").lines, ["Time range: the last 6 hours"])
        # Dates as people read them (another year than this one shows it).
        self.assertEqual(self.plan('range from "2024-10-29 07:05" to "2024-10-30 07:05"').lines,
                         ["Time range: 29 Oct 2024 07:05 → 30 Oct 2024 07:05 UTC"])
        self.assertEqual(self.plan("range day 2024-10-29").lines, ["Time range: 29 Oct 2024, all day UTC"])
        self.assertEqual(self.plan("range month 2024-10").lines, ["Time range: October 2024"])
        self.assertEqual(self.plan("process r1 median").title, "Spike removal")
        self.assertEqual(self.plan("move r1 to p2\nmove r2 to p3").title, "Move", "a title once")
        # The x axis of a plot changes for all its rows, and the card says why for the others.
        self.assertEqual(self.plan("process r1 relative_time").lines[1],
                         "MAG-MCTB-F1:VAR2 — time counted in seconds from the first point, so the plot keeps one "
                         "time axis")

    def test_rows_with_the_same_name_are_told_apart_by_where_they_are(self):
        # The table shows no row numbers: twins are told by their plot, else by their order.
        self.ws.set_cells(self.ws.snapshot().rows[3].uid, {"Variable": "MAG-MCTB-F1:VAR2"})
        self.assertEqual(self.plan("remove r2").lines, ["Remove MAG-MCTB-F1:VAR2 (in the top plot) from the table"])
        self.ws.set_cells(self.ws.snapshot().rows[3].uid, {"Stack": "1.1"})
        self.assertEqual(self.plan("remove r4").lines,
                         ["Remove MAG-MCTB-F1:VAR2 (the second one in the table) from the table"])

    def test_ids_the_model_lets_slip_into_its_words_become_names(self):
        proposal = self.plan('ask "Which one: the pirani (r1), r2 or the one in p3?"')
        self.assertEqual(proposal.messages, ["Which one: the pirani, MAG-MCTB-F1:VAR2 or the one in the bottom plot?"])
        self.assertTrue(proposal.question)
        self.assertFalse(self.plan('say "Hello!"').question)

    def test_a_missing_number_says_which_command_and_value_it_needs(self):
        with self.assertRaises(MissingValue) as ctx:
            self.plan("remove r2\nprocess r1 lowpass")
        self.assertEqual((ctx.exception.param, ctx.exception.command.verb), ("hz", "process"))
        self.assertTrue(str(ctx.exception).endswith("?"))

    def test_window_defaults_to_a_hundredth_of_the_time_range(self):
        proposal = self.plan("process r2 median")
        self.assertIn("np.round(100 / ", proposal.detail)

    def test_replace_composes_with_the_existing_expression(self):
        self.win.sigCfgWidget.model.setData(self.win.sigCfgWidget.model.index(3, 5), "", 2)
        proposal, after = self.apply_and_undo("process r4 abs replace")
        self.assertEqual(len(after), 4)
        self.assertEqual(after.iloc[3]["y"], "np.abs((${self}.data * 1000))")

    def test_relative_time_changes_every_row_of_the_plot(self):
        proposal, after = self.apply_and_undo("process r1 relative_time")
        self.assertEqual(len(proposal.changes), 2)

    def test_combine_across_data_sources_is_refused(self):
        # iplotlib marks an expression whose aliases live in another data source as a conflict.
        with self.assertRaises(ActionError) as ctx:
            self.plan("combine subtract r1 r3")
        self.assertIn("same source", str(ctx.exception))

    def test_combine_in_the_same_source_uses_variable_names(self):
        proposal, after = self.apply_and_undo("combine divide r2 r1")
        new = after.iloc[2]
        self.assertEqual(new["Variable"], "${MAG-MCTB-F1:VAR2} / ${pirani}")
        self.assertEqual((new["DS"], new["Stack"]), ("csv", "4.1"))

    def test_move_and_remove(self):
        _, after = self.apply_and_undo("move r3 to p1")
        self.assertEqual(after.iloc[2]["Stack"], "1.1")
        _, after = self.apply_and_undo("move r1 r2 to new")
        self.assertEqual(list(after["Stack"][:2]), ["4.1", "4.1"])
        _, after = self.apply_and_undo("remove r2 r3")
        self.assertEqual(list(after["Variable"]), ["MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR3"])

    def test_time_ranges(self):
        before = self.ws.range_dict()
        for text, mode in (("range last 6 hours", "RELATIVE_TIME"), ("range day 2026-10-03", "TIME_RANGE"),
                           ("range month 2026-02", "TIME_RANGE"), ('range from "2026-10-01 08:00" to '
                                                                   '"2026-10-01 12:30"', "TIME_RANGE"),
                           ("range pulse ITER:MCTB_PSS-TF07_FD/11", "PULSE_NUMBER")):
            with self.subTest(text=text):
                change = self.plan(text).changes[0]
                change.do()
                self.assertNotEqual(self.ws.range_dict(), before)
                self.assertEqual(self.ws.range_dict()["mode"], mode)
                if text.startswith("range day"):
                    start, end = self.win.dataRangeSelector.get_time_range()
                    self.assertEqual(int(start), int(datetime(2026, 10, 3, tzinfo=timezone.utc).timestamp()) * 10 ** 9)
                    self.assertEqual(int(end) - int(start), 86400 * 10 ** 9)
                if text.startswith("range month"):
                    start, end = self.win.dataRangeSelector.get_time_range()
                    self.assertEqual(int(end) - int(start), 28 * 86400 * 10 ** 9)
                change.undo()
                self.assertEqual(self.ws.range_dict(), before)

    def test_plot_settings_need_a_drawn_plot_and_are_undone(self):
        with self.assertRaises(ActionError):
            self.plan("plot p1 log=on")
        self.win.canvas.plots = [[PlotXY(row=1, col=1)]]
        proposal = self.plan('plot p1 log=on grid=off title="Vacuum"')
        # A Draw between the card and Apply builds new plot objects.
        plot = PlotXY(row=1, col=1)
        self.win.canvas.plots = [[plot]]
        proposal.apply()
        self.assertEqual((plot.log_scale, plot.grid, plot.plot_title), (True, False, "Vacuum"))
        redrawn = PlotXY(row=1, col=1, log_scale=True, grid=False, plot_title="Vacuum")
        self.win.canvas.plots = [[redrawn]]
        self.assertEqual(proposal.undo(), [])
        self.assertEqual((redrawn.log_scale, redrawn.grid, redrawn.plot_title), (None, None, None))

    def test_refusals(self):
        for text, fragment in (("process r9 abs", "no row 9"), ("process r4 abs", "min/max band"),
                               ("process r1 lowpass", "frequency"), ("range day 1950-01-01", "between"),
                               ("range last 999999 days", "100 years"),
                               ("combine add r1 r1", "two different"), ("range day 2026-02-30", "dates"),
                               ('range from "2026-10-02 00:00" to "2026-10-01 00:00"', "after its start"),
                               ("move r1 to p7", "no plot p7")):
            with self.subTest(text=text):
                with self.assertRaises(ActionError) as ctx:
                    self.plan(text)
                self.assertIn(fragment, str(ctx.exception))

    def test_a_change_the_samples_are_too_far_apart_to_show_is_asked_again(self):
        # Archived on change: a sample about every 12 s.
        self.ws.sample_period_seconds = lambda row: 11.654
        for text, param, fragment in (("process r1 moving_average seconds=10", "seconds", "For example 50 s."),
                                      ("process r1 median seconds=5", "seconds", "over 5 s it would stay as it is"),
                                      ("process r1 lowpass hz=2", "hz", "For example 0.009 Hz.")):
            with self.subTest(text=text):
                with self.assertRaises(MissingValue) as ctx:
                    self.plan(text)
                self.assertEqual(ctx.exception.param, param)
                self.assertIn("a sample about every 12 s", str(ctx.exception))
                self.assertIn(fragment, str(ctx.exception))
        for text in ("process r1 moving_average seconds=60", "process r1 lowpass hz=0.005",
                     "process r1 gaussian seconds=5", "process r1 derivative"):
            with self.subTest(text=text):
                self.assertTrue(self.plan(text).changes)

    def test_the_sample_period_comes_from_the_data_already_drawn(self):
        from types import SimpleNamespace
        import numpy as np
        row = SimpleNamespace(index=0, id="r1")
        drawn = SimpleNamespace(uid=self.ws.uid_of(0), x_data=1.73e18 + np.arange(0, 100e9, 11.654e9))
        canvas = SimpleNamespace(get_signals=lambda canvas: [SimpleNamespace(uid="other", x_data=[0, 1, 2]), drawn])
        with mock.patch.object(self.ws.window.canvasStack, "currentWidget", return_value=canvas):
            self.assertAlmostEqual(self.ws.sample_period_seconds(row), 11.654, places=3)
            drawn.x_data = None
            self.assertIsNone(self.ws.sample_period_seconds(row), "not drawn yet: nothing to say")

    def test_how_a_drawn_signal_came_out(self):
        from types import SimpleNamespace
        import numpy as np
        from iplotlib.interface.iplotSignalAdapter import Result
        from mint.assistant.workspace import DRAWN, EMPTY, NOT_COMPUTED
        uid = self.ws.uid_of(0)
        drawn = SimpleNamespace(uid=uid, status_info=SimpleNamespace(result=Result.SUCCESS))
        canvas = SimpleNamespace(get_signals=lambda canvas: [SimpleNamespace(uid="other"), drawn])
        time, nan = np.arange(5.0), np.full(5, np.nan)
        with mock.patch.object(self.ws.window.canvasStack, "currentWidget", return_value=canvas):
            for result, x, y, outcome, why in (
                    (Result.SUCCESS, time, time, DRAWN, "values to draw"),
                    (Result.SUCCESS, time, np.array([np.nan, 1, np.nan, np.inf, np.nan]), DRAWN, "one is enough"),
                    (Result.SUCCESS, [], [], EMPTY, "no samples"),
                    (Result.SUCCESS, time, nan, EMPTY, "no value, as the log10 of a signal below zero"),
                    (Result.SUCCESS, nan, time, EMPTY, "no time to place the values at"),
                    (Result.FAIL, None, None, NOT_COMPUTED, "MINT could not work it out"),
                    (Result.BUSY, None, None, None, "still being read: nothing to tell yet"),
                    (Result.READY, None, None, None, "not read yet")):
                with self.subTest(why=why):
                    drawn.status_info.result, drawn.x_data, drawn.y_data = result, x, y
                    self.assertEqual(self.ws.drawn_outcome(uid), outcome)
            self.assertIsNone(self.ws.drawn_outcome("not drawn"), "a row that isn't drawn: nothing to tell")
        # MINT leaves a signal that failed off the canvas: its Status says so.
        uid = self.ws.uid_of(1)
        status = self.ws._column("Status")
        for shown, outcome in (("Data-Access|0 points", NOT_COMPUTED), ("Processing|0 points", NOT_COMPUTED),
                               ("Busy|Data-Access", None), ("Ready", None), ("", None)):
            with self.subTest(status=shown):
                self.ws.model.setData(self.ws.model.index(1, status), shown, Qt.ItemDataRole.DisplayRole)
                self.assertEqual(self.ws.drawn_outcome(uid), outcome)

    def test_the_latest_sample_comes_from_one_request_to_the_archive(self):
        from types import SimpleNamespace
        import numpy as np
        from mint.assistant.workspace import FOUND, NONE_BEFORE, UNKNOWN_VARIABLE, UNTOLD
        asked = []

        def archive(errcode=0, xdata=None, errdesc="OK"):
            def get_data(**kwargs):
                asked.append(kwargs)
                if isinstance(errcode, Exception):
                    raise errcode
                return SimpleNamespace(errcode=errcode, xdata=xdata, errdesc=errdesc)
            return SimpleNamespace(source_type="CODAC_UDA", get_data=get_data)

        last = 1_778_403_827_000_000_000
        for source, answer in ((archive(0, np.array([last], dtype=np.uint64)), (FOUND, last)),
                               (archive(-1, None, "ERROR udaPlugin: Requested interval is empty"), (NONE_BEFORE, None)),
                               (archive(-1, None, "ERROR udaPlugin: Requested variable does not exist"),
                                (UNKNOWN_VARIABLE, None)),
                               (archive(RuntimeError("server down")), (UNTOLD, None)),
                               (archive(-3, None, "Requested data cannot be located"), (UNTOLD, None)),
                               (archive(-1, None, "ERROR: plugin file does not exist"), (UNTOLD, None)),
                               (SimpleNamespace(source_type="CSV", get_data=lambda **kw: asked.append(kw)), (UNTOLD, None))):
            with self.subTest(answer=answer), mock.patch.object(AppDataAccess.da, "get_data_source", return_value=source):
                self.assertEqual(self.ws.latest_sample("codacuda", "CRYO:MT0001", 2_000), answer)
        self.assertEqual(len(asked), 6, "a source that can't say is not asked")
        self.assertEqual(asked[0], {"varname": "CRYO:MT0001", "tsS": "0", "tsE": "2000", "nbp": 1, "decType": "last"})

    def test_the_time_range_in_ns(self):
        start, end = self.ws.time_range_ns()
        self.assertEqual(end - start, 2 * 3600 * 10**9, "the last 2 hours, as build_window sets them")
        self.ws.set_range_dict({"mode": MTGenericAccessMode.PULSE_NUMBER, "pulse_nb": ["ITER:MCTB-TEST/111"], "base": 1,
                                "t_start": "", "t_end": ""})
        self.assertIsNone(self.ws.time_range_ns(), "a pulse has no dates")

    def test_a_processing_or_a_combination_says_which_row_it_computes(self):
        for text, computed in (("process r1 moving_average seconds=30", "pirani_avg_30s"),
                               ("process r2 abs replace", "MAG-MCTB-F1:VAR2"),
                               ("combine divide r2 r1", "VAR2_over_pirani"), ("move r1 to new", None)):
            with self.subTest(text=text):
                proposal = self.plan(text)
                proposal.apply()
                uids = [c.computes() for c in proposal.changes if c.computes]
                if computed is None:
                    self.assertEqual(uids, [], "a move computes nothing")
                else:
                    self.assertEqual([self.ws.name_of(uid) for uid in uids], [computed])
                self.assertEqual(proposal.undo(), [])

    def test_variable_search_uses_the_data_source(self):
        search = self.ws.search_variables(["MCTB", "VAR2"])
        self.assertEqual(search.source, AppDataAccess.da.get_default_ds_name())
        self.assertTrue(search.found)
        self.assertTrue(all("var2" in name.lower() and "mctb" in name.lower() for name, _ in search.found), search)

    def test_variable_search_goes_to_the_data_source_named_and_reads_a_group(self):
        class Source:
            patterns = []

            def get_var_list(self, pattern):
                self.patterns.append(pattern)
                names = ["EC-GYA-01:PSU-YSTA", "EC-GYB-02:PSU-YSTA", "SPEC-01:EC-V", "CRYO-CP3:MT0012-XI"]
                return [n for n in names if re.fullmatch(pattern, n)]

        source = Source()
        opened = []
        self.ws.data_source_names = lambda: ["codacuda", "sdnuda"]
        self.ws.data_source = lambda name: (opened.append(name), source)[1]
        request = "I need a workspace with 2 signals from EC in sdnuda, whatever you want"
        for words in (["EC", "sdnuda"], ["ec"]):
            with self.subTest(words=words):
                search = self.ws.search_variables(words, request)
                self.assertEqual((search.source, search.group, opened[-1]), ("sdnuda", "EC", "sdnuda"))
                self.assertEqual(source.patterns[-1], "EC[-.:_].*", "the names that start with the group")
                self.assertEqual([name for name, _ in search.found], ["EC-GYA-01:PSU-YSTA", "EC-GYB-02:PSU-YSTA"])
        search = self.ws.search_variables(["MT0012"], "find MT0012 in sdnuda")
        self.assertEqual(source.patterns[-2:], ["MT0012[-.:_].*", ".*MT0012.*"], "no group of that name: anywhere")
        self.assertEqual(([name for name, _ in search.found], search.group), (["CRYO-CP3:MT0012-XI"], ""))
        with self.assertRaises(ActionError) as ctx:
            self.ws.search_variables(["sdnuda"], "variables in sdnuda")
        self.assertIn("What should I look for in sdnuda", str(ctx.exception))

    def test_full_names_are_each_looked_up(self):
        class Source:
            def get_var_list(self, pattern):
                names = ["CRYO-CA-SQB:PC-6200-DP12", "CRYO-CA-SQB:PC-6200-DP13", "CRYO-CA-SQB:MZ6290-XI0",
                         "CRYO-CA-SQB:MZ6290-XI"]
                return [n for n in names if re.fullmatch(pattern, n)]

        self.ws.default_data_source = lambda: ("codacuda", Source())
        names = ["CRYO-CA-SQB:PC-6200-DP12", "CRYO-CA-SQB:MZ6290-XI0", "CRYO-CA-SQB:MPD6200-XI"]
        search = self.ws.search_variables(names, "add " + ", ".join(names))
        self.assertEqual([name for name, _ in search.found], names[:2], "each one, not those holding them all")
        self.assertEqual(search.missing, names[2:])

    def test_the_data_source_of_rows_changes_among_those_here(self):
        proposal, after = self.apply_and_undo("source r3 to csv")
        self.assertEqual(proposal.lines, ["CRYO:MT0001: other → csv"])
        self.assertEqual(proposal.commands, ["source r3 to csv"])
        self.assertEqual(list(after["DS"]), ["csv"] * 4)
        with self.assertRaises(ActionError) as ctx:
            self.plan("source r1 to imaspy")
        self.assertIn("imaspy isn't one of the data sources here", str(ctx.exception))

    def test_the_same_signal_of_two_pulses_is_told_by_its_pulse(self):
        from mint.assistant.snapshot import PlotInfo, RowInfo, Snapshot
        coil = "pf_active/coil[1]/current/data"
        rows = [RowInfo(id="r1", index=0, variable=coil, stack="1", plot="p1",
                        pulse="imas:hdf5?path=/home/ITER/user/public/imasdb/test/105027/pf_active_5k"),
                RowInfo(id="r2", index=1, variable=coil, stack="1", plot="p1")]
        planner = Planner(self.ws, Snapshot(rows=rows, plots=[PlotInfo(id="p1", row=1, col=1)]))
        self.assertEqual([planner.name(row) for row in rows],
                         [f"{coil} (pulse pf_active_5k)", f"{coil} (the workspace's pulse)"])

    def test_hiding_a_drawn_signal_keeps_its_row_and_undo_shows_it(self):
        hidden = {}
        uids = {r.id: r.uid for r in self.ws.snapshot().rows}
        self.ws.is_hidden = lambda uid: hidden.get(uid, False) if uid != uids["r3"] else None
        self.ws.set_hidden = lambda uid, value: hidden.__setitem__(uid, value)
        proposal = Planner(self.ws, self.ws.snapshot()).plan(commands.parse("hide r1 r2"))
        self.assertEqual(proposal.title, "Hide")
        self.assertEqual(proposal.lines, ["Hide pirani and MAG-MCTB-F1:VAR2 on the plot (the legend still lists them)"])
        rows = len(self.ws.table().index)
        proposal.apply()
        self.assertEqual(hidden, {uids["r1"]: True, uids["r2"]: True})
        self.assertEqual(len(self.ws.table().index), rows, "the rows stay in the table")
        proposal.undo()
        self.assertEqual(hidden, {uids["r1"]: False, uids["r2"]: False})
        with self.assertRaises(ActionError) as e:
            Planner(self.ws, self.ws.snapshot()).plan(commands.parse("hide r3"))
        self.assertIn("isn't drawn", str(e.exception))
        hidden[uids["r1"]] = True
        self.assertEqual(Planner(self.ws, self.ws.snapshot()).plan(commands.parse("show r1")).lines,
                         ["Show pirani again"])

    def test_a_relative_range_shows_its_span_in_from_and_to(self):
        fields = self.win.dataRangeSelector.accessModes[0]
        before = fields.to_dict()
        snap = self.ws.snapshot()
        proposal = Planner(self.ws, snap).plan(commands.parse("range last 6 hours"))
        proposal.apply()
        self.assertEqual(self.ws.range_dict()["mode"], "RELATIVE_TIME")
        end = snap.now.astimezone(timezone.utc).replace(tzinfo=None)
        shown = [datetime.fromisoformat(fields.to_dict()[key]) for key in ("ts_start", "ts_end")]
        self.assertLess(abs((shown[1] - end).total_seconds()), 1)
        self.assertLess(abs((shown[1] - shown[0]).total_seconds() - 6 * 3600), 1)
        self.assertEqual(proposal.undo(), [])
        self.assertEqual(fields.to_dict(), before, "Undo puts From and To back too")

    def test_variable_search_in_a_source_that_is_not_connected_says_so(self):
        self.ws.data_source_names = lambda: ["sdnuda"]
        with mock.patch.object(AppDataAccess, "da") as da:
            da.get_data_source.return_value.is_connected.return_value = False
            with self.assertRaises(ActionError) as ctx:
                self.ws.search_variables(["EC"], "EC in sdnuda")
        self.assertIn("sdnuda isn't connected", str(ctx.exception))

    def test_variable_search_understands_what_a_signal_measures(self):
        class Source:
            patterns = []

            def get_var_list(self, pattern):
                self.patterns.append(pattern)
                names = ["CRYO-CP3:MT0012-XI", "CRYO-CP3:MP0013-XI", "CRYO-CP4:MT0014-XI", "CRYO-CP3:TV0001-XI"]
                return [n for n in names if re.fullmatch(pattern, n)]

            def get_hmi_var_dict(self):
                return {"CRYO-CP3:TV0001-XI": {"description": "CP3 valve temperature"}}

        source = Source()
        self.ws.default_data_source = lambda: ("codacuda", source)
        found = self.ws.search_variables(["CP3", "temperature"]).found
        self.assertEqual(sorted(name for name, _ in found), ["CRYO-CP3:MT0012-XI", "CRYO-CP3:TV0001-XI"],
                         "by the code, or by the description")
        self.assertEqual(source.patterns[-1], ".*CP3.*", "the server filters on a word of the names")
        found = self.ws.search_variables(["température"]).found
        self.assertEqual(source.patterns[-1], ".*MT[0-9].*")
        self.assertIn("CRYO-CP4:MT0014-XI", [name for name, _ in found])

    def test_tags_are_looked_up_one_by_one(self):
        class Source:
            patterns = []

            def get_var_list(self, pattern):
                self.patterns.append(pattern)
                names = ["CRYO-CP3:MT0012-XI", "CRYO-CP4:MT0012-XI", "CRYO-CH-MM-CRST:MLT1000-AA-IN",
                         "CRYO-CH-MM-CRST:MLT1000-AA-IN-ALEN", "BUIL-B15:MLT1000-AA-INX"]
                return [n for n in names if re.fullmatch(pattern, n)]

        source = Source()
        self.ws.default_data_source = lambda: ("codacuda", source)
        search = self.ws.search_codes(["MLT1000-AA-IN", "MT0012", "PT-1101"])
        self.assertEqual(source.patterns, [f".*{re.escape(code)}.*" for code in ("MLT1000-AA-IN", "MT0012", "PT-1101")],
                         "one request each: the server takes no alternatives")
        self.assertEqual([name for name, _ in search.found],
                         ["CRYO-CH-MM-CRST:MLT1000-AA-IN", "CRYO-CP3:MT0012-XI", "CRYO-CP4:MT0012-XI"],
                         "the variable with that very tag, else all that hold it")
        self.assertEqual((search.source, search.missing), ("codacuda", ["PT-1101"]))

    def test_undo_finds_its_rows_after_other_edits(self):
        proposal = self.plan("process r2 derivative")
        proposal.apply()
        self.ws.insert_row_at(0, {"DS": "csv", "Variable": "X", "Stack": "5.1"})
        self.assertEqual(proposal.undo(), [])
        self.assertEqual(list(self.table()["Variable"]),
                         ["X", "MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR2", "CRYO:MT0001", "MAG-MCTB-F1:VAR3"])


REPORT = ["Signals of the TF07 cool-down, 2024-10-29 07:05 to 2024-10-30 07:05",
          "MAG-MCTB-F1:VAR2 | coil current | kA",
          "CRYO-CP-03:MT0021-XI | inlet temperature | K"]


def write_pdf(path, lines=()):
    """One page with a line of text for each item, or with only a drawing, as a scan is."""
    # Written by hand: what Qt writes depends on the fonts the process has, so its text isn't always extractable.
    shown = "".join("({}) Tj 0 -16 Td ".format(re.sub(r"([\\()])", r"\\\1", line)) for line in lines)
    content = f"BT /F1 11 Tf 50 780 Td {shown}ET" if lines else "100 100 300 200 re S"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >>"
               " /Contents 4 0 R >>",
               f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    data, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    data += (f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
             + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{len(data)}\n%%EOF\n").encode("latin-1")
    with open(path, "wb") as f:
        f.write(data)


class FileReadingTest(unittest.TestCase):
    """The kinds of files the assistant reads, and what it says of those it can't."""

    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def path(self, name):
        return os.path.join(self.dir.name, name)

    def assert_report(self, found):
        self.assertEqual([n for n, _ in found.variables], ["MAG-MCTB-F1:VAR2", "CRYO-CP-03:MT0021-XI"])
        self.assertEqual(found.times, ["2024-10-29 07:05", "2024-10-30 07:05"])

    def test_csv_and_text(self):
        path = self.path("report.csv")
        with open(path, "w", encoding="cp1252") as f:
            f.write("\n".join(REPORT).replace(" | ", ";") + "\nnote;température\n")
        self.assert_report(files.read(path))
        signal_set = self.path("saved.scsv")  # a signal set MINT saved
        with open(signal_set, "w", encoding="utf-8") as f:
            f.write("DS;Variable;Stack\ncodacuda;MAG-MCTB-F1:VAR2;1.1\ncodacuda;CRYO-CP-03:MT0021-XI;2.1\n")
        self.assertEqual([name for name, _ in files.read(signal_set).variables],
                         ["MAG-MCTB-F1:VAR2", "CRYO-CP-03:MT0021-XI"])

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl is not installed")
    def test_excel(self):
        import openpyxl
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(["Signals of the TF07 cool-down", datetime(2024, 10, 29, 7, 5), datetime(2024, 10, 30, 7, 5)])
        for line in REPORT[1:]:
            sheet.append(line.split(" | "))
        path = self.path("report.xlsx")
        book.save(path)
        self.assert_report(files.read(path))

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf is not installed")
    def test_pdf(self):
        path = self.path("report.pdf")
        write_pdf(path, REPORT)
        self.assert_report(files.read(path))
        scanned = self.path("scan.pdf")
        write_pdf(scanned)
        with self.assertRaisesRegex(files.FileError, "no text I can read: it may be a scanned image"):
            files.read(scanned)

    def test_the_words_of_a_pdf_may_come_apart_with_tabs(self):
        found = files.find(["Signals of the TF07 cool-down, 2024-10-29\t07:05 to 2024-10-30\t\t07:05"])
        self.assertEqual(found.times, ["2024-10-29 07:05", "2024-10-30 07:05"])

    def test_tags_without_their_system_are_kept_to_look_up(self):
        found = files.find(["Inlet MT0021 and PT-1101; the level is MLT1000-AA-IN.", "ISO-8601 dates, TF07, MT0021.5 K",
                            "CRYO-CP-03:MT0022-XI is named in full", "Shield MT0111-TTCB01-XI0"])
        self.assertEqual(found.codes, ["MT0021", "PT-1101", "MLT1000-AA-IN", "MT0111-TTCB01-XI0"])
        self.assertEqual([name for name, _ in found.variables], ["CRYO-CP-03:MT0022-XI"])

    def test_a_list_pasted_in_a_message(self):
        found, request = files.pasted("add these to one plot:\nCRYO-CH-MM-CRST:MLT1000-AA-IN\tlevel\n"
                                      "CRYO-CH-CB3-HESC:VOL3600-XI\tvolume\n")
        self.assertEqual([name for name, _ in found.variables],
                         ["CRYO-CH-MM-CRST:MLT1000-AA-IN", "CRYO-CH-CB3-HESC:VOL3600-XI"])
        self.assertEqual(request, "add these to one plot:", "the words around the list are the request")
        found, request = files.pasted("Signal;Unit\nCRYO-A-1:X1;K\nCRYO-A-1:X2;K\nChecked on 29 Oct 2024 07:05")
        self.assertEqual((len(found.variables), found.times, request), (2, ["2024-10-29 07:05"], ""),
                         "a table and its date are what was pasted, not a request")
        self.assertIsNone(files.pasted("smooth CRYO-A-1:X1 and CRYO-A-1:X2", ["CRYO-A-1:X1", "CRYO-A-1:X2"]),
                          "rows of the table named in a request are not a list")
        for message in ("smooth it\nCRYO-A-1:X1", "hello\nthere", "smooth CRYO-A-1:X1 over 30 s"):
            self.assertIsNone(files.pasted(message), message)

    def test_names_written_in_a_line_are_a_list(self):
        found, request = files.pasted("make me a workspace with these three variables CRYO-CA-SQB:PC-6200-DP12, "
                                      "CRYO-CA-SQB:MZ6290-XI0,CRYO-CA-SQB:MPD6200-XI and put three plots")
        self.assertEqual([name for name, _ in found.variables],
                         ["CRYO-CA-SQB:PC-6200-DP12", "CRYO-CA-SQB:MZ6290-XI0", "CRYO-CA-SQB:MPD6200-XI"])
        self.assertEqual(request, "make me a workspace with these three variables and put three plots")
        self.assertEqual(files.pasted("add CRYO-A-1:X1, CRYO-A-1:X2 and CRYO-A-1:X3, one plot each")[1],
                         "add them, one plot each")
        self.assertEqual(files.pasted("CRYO-A-1:X1, CRYO-A-1:X2")[1], "", "only names: the list alone")

    def test_a_pdf_table_keeps_each_row_on_one_line(self):
        class Page:
            def __init__(self, layout):
                self.layout = layout

            def extract_text(self, extraction_mode="plain"):
                if extraction_mode == "layout":
                    if self.layout is None:
                        raise ValueError("this page breaks the layout mode")
                    return self.layout
                return "SYS-A:X1\nlevel"

        self.assertEqual(files._page_text(Page("SYS-A:X1     level")), "SYS-A:X1     level")
        self.assertEqual(files._page_text(Page(None)), "SYS-A:X1\nlevel", "the plain text, if layout fails")

    def test_what_cannot_be_read_says_why(self):
        image = self.path("photo.png")
        open(image, "wb").close()
        with self.assertRaisesRegex(files.FileError, "CSV, Excel and PDF files, not .png files"):
            files.read(image)
        big = self.path("big.csv")
        open(big, "wb").close()
        with mock.patch.object(files.os.path, "getsize", return_value=files.MAX_BYTES + 1), \
                self.assertRaisesRegex(files.FileError, "I read files up to 20 MB"):
            files.read(big)
        broken = self.path("broken.pdf")
        with open(broken, "wb") as f:
            f.write(b"not a pdf")
        # pypdf comes with the assistant's extra, which not every environment has: then that is what it says.
        said = "can't read broken.pdf as a PDF" if importlib.util.find_spec("pypdf") else "needs pypdf"
        with self.assertRaisesRegex(files.FileError, said):
            files.read(broken)
        open(self.path("sheet.xlsx"), "wb").close()
        with mock.patch.dict("sys.modules", {"openpyxl": None}), \
                self.assertRaisesRegex(files.FileError, "pip install openpyxl"):
            files.read(self.path("sheet.xlsx"))


class FileActionsTest(_WindowCase):
    """The commands that use an attached file: added variables and its times."""

    def snap(self, count=2, times=("2024-10-29 07:05", "2024-10-30"), source="csv"):
        snap = self.ws.snapshot()
        found = files.Found([("MAG-MCTB-F1:VAR2", "current"), ("CRYO:MT0001", "")] +
                            [(f"SYS-{i}:X{i}", "") for i in range(count - 2)], list(times), [])
        snap.file = files.info("report.pdf", found, source)
        return snap

    def plan(self, text, snap=None):
        return Planner(self.ws, snap or self.snap()).plan(commands.parse(text))

    def test_variables_of_the_file_are_added_each_in_a_new_plot_or_together(self):
        proposal = self.plan("add v1 v2")
        self.assertEqual(proposal.title, "Add from report.pdf")
        self.assertEqual(proposal.lines, ["Add MAG-MCTB-F1:VAR2", "Add CRYO:MT0001", "Each in a new plot"])
        before = len(self.table())
        proposal.apply()
        added = self.table().iloc[before:]
        self.assertEqual(list(added["DS"]), ["csv", "csv"])
        self.assertEqual(list(added["Stack"]), ["4.1", "5.1"], "below the plots there are")
        self.assertEqual(proposal.undo(), [])
        self.assertEqual(len(self.table()), before)
        together = self.plan("add all together")
        self.assertEqual(together.lines[-1], "All in one new plot")
        together.apply()
        self.assertEqual(list(self.table().iloc[before:]["Stack"]), ["4.1", "4.1"])
        self.assertEqual(self.plan("add v2").lines, ["Add CRYO:MT0001", "In a new plot"])

    def test_what_add_cannot_do_is_said(self):
        with self.assertRaisesRegex(ActionError, "no file with signal names"):
            Planner(self.ws, self.ws.snapshot()).plan(commands.parse("add v1"))
        with self.assertRaisesRegex(ActionError, "too many for one card"):
            self.plan("add all", self.snap(MAX_ADDED + 1))
        with self.assertRaisesRegex(ActionError, "isn't connected to any data source"):
            self.plan("add v1", self.snap(source=""))
        with self.assertRaisesRegex(ActionError, "doesn't name that variable"):
            self.plan("add v7")

    def test_the_times_of_the_file_set_the_range(self):
        def spans(text):
            proposal = self.plan(text)
            proposal.apply()
            start, end = self.ws.time_range_ns()
            proposal.undo()
            return [datetime.fromtimestamp(t / 1e9, timezone.utc).strftime("%Y-%m-%d %H:%M") for t in (start, end)]

        self.assertEqual(spans("range from t1 to t2"), ["2024-10-29 07:05", "2024-10-31 00:00"],
                         "a date alone at the end: up to the end of that day")
        self.assertEqual(spans("range day t1"), ["2024-10-29 00:00", "2024-10-30 00:00"])
        self.assertEqual(spans('range from t1 to "2024-10-29 08:00"'), ["2024-10-29 07:05", "2024-10-29 08:00"])
        with self.assertRaisesRegex(ActionError, "no such time"):
            self.plan("range day t3")


class AssistantStateChangesTest(_WindowCase):
    """The table, the plots or other cards changed between planning and Apply or Undo."""

    def variables(self):
        return list(self.table()["Variable"])

    def test_apply_targets_the_planned_row_after_the_table_changed(self):
        proposal = self.plan("remove r2")
        self.ws.remove_row(self.ws.uid_of(0))
        proposal.apply()
        self.assertEqual(self.variables(), ["CRYO:MT0001", "MAG-MCTB-F1:VAR3"])

    def test_apply_on_a_row_deleted_meanwhile_is_refused(self):
        proposal = self.plan("move r2 to p2")
        self.ws.remove_row(self.ws.uid_of(1))
        with self.assertRaises(ActionError):
            proposal.apply()

    def test_rows_without_uid_get_one(self):
        model = self.win.sigCfgWidget.model
        column = list(self.table().columns).index("uid")
        for i in range(4):
            model.setData(model.index(i, column), "", 2)
        self.plan("remove r3").apply()
        self.assertEqual(self.variables(), ["MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR2", "MAG-MCTB-F1:VAR3"])
        self.assertEqual(len(set(self.table()["uid"])), 3)

    def test_two_cards_planned_together_get_distinct_names_and_plots(self):
        first, second = self.plan("process r1 abs"), self.plan("process r1 abs")
        first.apply()
        second.apply()
        aliases = list(self.table()["Alias"])
        self.assertEqual(aliases.count("pirani_abs"), 1)
        self.assertIn("pirani_abs_2", aliases)
        a, b = self.plan("move r1 to new"), self.plan("move r2 to new")
        a.apply()
        b.apply()
        self.assertEqual(list(self.table()["Stack"][:2]), ["4.1", "5.1"])

    def test_undo_skips_what_is_gone_and_does_the_rest(self):
        proposal = self.plan("move r1 r3 to new")
        proposal.apply()
        self.ws.remove_row(self.ws.uid_of(2))
        problems = proposal.undo()
        self.assertEqual(len(problems), 1)
        self.assertEqual(self.table()["Stack"].iloc[0], "1.1")

    def test_removed_rows_come_back_in_place_whatever_the_undo_order(self):
        before = self.variables()
        first, second = self.plan("remove r1"), self.plan("remove r3")
        first.apply()
        second.apply()
        first.undo()
        second.undo()
        self.assertEqual(self.variables(), before)

    def test_long_relative_ranges_keep_their_length(self):
        self.plan("range last 120 minutes").apply()
        self.assertEqual((self.ws.range_dict()["relative"], self.ws.range_dict()["base"]), (2, 3600))
        self.plan("range last 500 seconds").apply()
        start, end = self.win.dataRangeSelector.get_time_range()
        self.assertEqual(self.ws.range_dict()["mode"], "TIME_RANGE")
        self.assertAlmostEqual((int(end) - int(start)) / 1e9, 500, delta=1)

    def test_range_undo_goes_back_to_the_range_before_this_card(self):
        six_hours, one_day = self.plan("range last 6 hours"), self.plan("range last 1 days")
        six_hours.apply()
        one_day.apply()
        one_day.undo()
        self.assertEqual((self.ws.range_dict()["relative"], self.ws.range_dict()["base"]), (6, 3600))

    def test_a_card_that_fails_halfway_puts_back_all_it_did(self):
        before = self.table()
        proposal = self.plan("remove r1\nmove r2 to new")
        move = proposal.changes[1]
        do = move.do

        def half_then_fail():
            do()
            raise RuntimeError("refused halfway")

        move.do = half_then_fail
        with self.assertRaises(RuntimeError):
            proposal.apply()
        pd.testing.assert_frame_equal(self.table().reset_index(drop=True), before.reset_index(drop=True))

    def test_a_failed_write_leaves_the_table_as_it_was(self):
        write, calls = self.ws._write, []

        def fails_once(position, values):
            calls.append(position)
            if len(calls) == 1:
                write(position, dict(list(values.items())[:1]))
                raise RuntimeError("refused")
            write(position, values)

        self.ws._write = fails_once
        before = self.table()
        with self.assertRaises(RuntimeError):
            self.ws.insert_row_at(0, {"DS": "csv", "Variable": "X", "Stack": "5.1"})
        calls.clear()
        with self.assertRaises(RuntimeError):
            self.ws.set_cells(self.ws.uid_of(0), {"Alias": "new", "Stack": "7.1"})
        pd.testing.assert_frame_equal(self.table().reset_index(drop=True), before.reset_index(drop=True))

    def test_an_unexpected_failure_in_undo_does_not_stop_the_rest(self):
        proposal = self.plan("remove r1\nremove r3")
        proposal.apply()

        def broken():
            raise RuntimeError("broken")

        proposal.changes[1].undo = broken
        self.assertEqual(proposal.undo(), ["One change couldn't be put back."])
        self.assertIn("MAG-MCTB-F1:VAR1", self.variables(), "the other change was still undone")


if __name__ == "__main__":
    unittest.main()
