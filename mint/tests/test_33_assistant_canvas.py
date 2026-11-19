"""The assistant's cards for the canvas, on a canvas drawn for real: the view (zoom, pan, Home), focus, rulers, the
toolbar's tools and a signal's preferences, each applied and undone as MINT's own buttons do it."""
import time
import unittest

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from PySide6.QtWidgets import QApplication

from mint.assistant import commands
from mint.assistant.actions import ActionError, Planner
from mint.assistant.workspace import MintWorkspace
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


class AssistantCanvasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        self.win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version="test",
                                data_sources=AccessHelper.da.get_connected_data_source_names(),
                                blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl="matplotlib")
        # A pulse: x is in seconds from its start, -5 to 4 s here.
        self.win.dataRangeSelector.import_dict({"mode": MTGenericAccessMode.PULSE_NUMBER,
                                                "pulse_nb": ["ITER:MCTB-TEST/111"], "base": "Second(s)",
                                                "t_start": "-5", "t_end": "4"})
        self.win.sigCfgWidget.model.set_dataframe(pd.DataFrame({
            "DS": ["csv", "csv"], "Variable": ["MAG-MCTB-F1:VAR1", "MAG-MCTB-F1:VAR2"], "Stack": ["1.1", "2.1"],
            "Plot type": ["PlotXY", "PlotXY"], "Alias": ["first", "second"]}))
        self.ws = MintWorkspace(self.win)
        self.win.draw_clicked()
        self.wait(lambda: self.ws.view(1, 1) is not None and self.ws.view(2, 1) is not None)
        self.drawn = self.ws.view(1, 1)

    def tearDown(self):
        self.win.close()

    def wait(self, ready, seconds=15.0):
        end = time.monotonic() + seconds
        while not ready() and time.monotonic() < end:
            QApplication.processEvents()
            time.sleep(0.01)
        self.assertTrue(ready(), "the canvas wasn't drawn in time")

    def plan(self, text):
        return Planner(self.ws, self.ws.snapshot()).plan(commands.parse(text))

    def rounded(self, view):
        return tuple(round(v, 3) for v in view)

    def test_a_zoom_in_a_pulse_is_in_seconds_from_its_start_and_moves_the_plots_sharing_its_time(self):
        proposal = self.plan("zoom all from 1 to 2 s")
        self.assertEqual(proposal.lines, ["Zoom all plots: 1 to 2 s from the start of the pulse"])
        proposal.apply()
        self.assertEqual([self.rounded(self.ws.view(r, 1)) for r in (1, 2)], [(1.0, 2.0), (1.0, 2.0)])
        proposal.undo()
        self.assertEqual(self.rounded(self.ws.view(1, 1)), self.rounded(self.drawn))
        with self.assertRaises(ActionError) as e:
            self.plan('zoom all from "07:20" to "07:30"')
        self.assertIn("from the start of the pulse", str(e.exception))

    def test_a_zoom_on_the_last_seconds_ends_where_the_pulse_drawn_ends(self):
        proposal = self.plan("zoom all last 2 s")
        self.assertEqual(proposal.lines, ["Zoom all plots: the last 2 s of the pulse"])
        proposal.apply()
        self.assertEqual(self.rounded(self.ws.view(1, 1)), (2.0, 4.0))
        proposal.undo()
        self.plan("zoom p2 last 1 min").apply()
        self.assertEqual(self.rounded(self.ws.view(2, 1)), (-5.0, 4.0), "no further back than the start")
        with self.assertRaises(ActionError):
            self.plan("zoom all last 0 s")

    def test_pan_and_home(self):
        self.plan("zoom all from 0 to 2 s").apply()
        proposal = self.plan("pan all by -500 ms")
        self.assertEqual(proposal.lines, ["Move the view of all plots 500 ms earlier"])
        proposal.apply()
        self.assertEqual(self.rounded(self.ws.view(1, 1)), (-0.5, 1.5))
        proposal.undo()
        self.assertEqual(self.rounded(self.ws.view(1, 1)), (0.0, 2.0))
        self.plan("home").apply()
        self.assertEqual(self.rounded(self.ws.view(1, 1)), self.rounded(self.drawn))

    def test_focus_one_plot_and_back(self):
        proposal = self.plan("focus p2")
        proposal.apply()
        self.assertEqual(self.ws.focused(), (2, 1))
        self.assertEqual(self.ws.snapshot().canvas, "p2 shown alone")
        with self.assertRaises(ActionError):
            self.plan("focus p2")
        proposal.undo()
        self.assertIsNone(self.ws.focused())
        with self.assertRaises(ActionError) as e:
            self.plan("focus off")
        self.assertIn("shown already", str(e.exception))

    def test_rulers_at_a_time_on_a_sample_and_removed(self):
        self.plan("ruler p1 at 1 s").apply()
        self.plan("ruler r2 at max").apply()
        rulers = self.ws.rulers()
        self.assertEqual([(r["name"], r["plot"]) for r in rulers], [("A", (1, 1)), ("B", (2, 1))])
        self.assertAlmostEqual(rulers[0]["x"], 1.0, places=3)
        self.assertEqual(self.ws.snapshot().canvas, "rulers A, B")
        proposal = self.plan("ruler off")
        self.assertEqual(proposal.lines, ["Remove the rulers A and B"])
        proposal.apply()
        self.assertEqual(self.ws.rulers(), [])
        proposal.undo()
        self.assertEqual(sorted(r["name"] for r in self.ws.rulers()), ["A", "B"])

    def test_a_tool_of_the_toolbar(self):
        proposal = self.plan("tool crosshair")
        proposal.apply()
        self.assertEqual(self.ws.mouse_mode(), Canvas.MOUSE_MODE_CROSSHAIR)
        self.assertTrue(self.win.toolBar._tool_actions[Canvas.MOUSE_MODE_CROSSHAIR].isChecked(), "its button shows it")
        proposal.undo()
        self.assertEqual(self.ws.mouse_mode(), Canvas.MOUSE_MODE_SELECT)

    def test_a_signal_preferences_and_draw_keeps_its_colour(self):
        uid = self.ws.snapshot().rows[0].uid
        proposal = self.plan("style r1 color=red width=3")
        self.assertEqual(proposal.lines, ["first: colour red, line width 3"])
        proposal.apply()
        signal = self.ws.drawn_signal(uid)
        self.assertEqual((signal.color, signal.line_size, signal.new_color), ("#d62728", 3, True))
        proposal.undo()
        signal = self.ws.drawn_signal(uid)
        self.assertNotEqual(signal.color, "#d62728")
        self.assertFalse(signal.new_color)

    def test_y_limits_that_would_show_none_of_the_data_are_refused(self):
        with self.assertRaises(ActionError) as e:
            self.plan("plot p1 ymin=1000 ymax=2000")
        self.assertIn("nothing of them would show", str(e.exception))
        proposal = self.plan('plot p1 ymin=0 ymax=5 ylabel="Volts"')
        proposal.apply()
        axis = self.ws.y_axis(1, 1)
        self.assertEqual((axis.begin, axis.end, axis.label), (0.0, 5.0, "Volts"))


if __name__ == "__main__":
    unittest.main()
