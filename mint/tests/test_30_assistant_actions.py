"""Assistant commands applied to a real main window, and undone."""
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

import pandas as pd
from PySide6.QtCore import Qt
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.assistant import commands
from mint.assistant.actions import ActionError, MissingValue, Planner
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

    def test_undo_finds_its_rows_after_other_edits(self):
        proposal = self.plan("process r2 derivative")
        proposal.apply()
        self.ws.insert_row_at(0, {"DS": "csv", "Variable": "X", "Stack": "5.1"})
        self.assertEqual(proposal.undo(), [])
        self.assertEqual(list(self.table()["Variable"]),
                         ["X", "MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR2", "CRYO:MT0001", "MAG-MCTB-F1:VAR3"])


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
