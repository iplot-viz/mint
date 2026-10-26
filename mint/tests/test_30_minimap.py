"""The mini-map of the main window shows the one plot of the canvas: it goes with the plot when
another workspace is imported, as the focus does, and comes back with the plot of a workspace that
shows it."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from PySide6.QtWidgets import QMessageBox
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

PULSE_ID = 'ITER:MCTB-TEST/111'
VAR1, VAR2 = 'MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'
BACKENDS = ('matplotlib', 'pyqt')


def _rows(*variables) -> dict:
    """A table with a plot per variable, one next to the other."""
    return {'DS': ['csv'] * len(variables), 'Variable': list(variables),
            'Stack': [f'1.{k + 1}' for k in range(len(variables))], 'Plot type': ['PlotXY'] * len(variables)}


def _minimap(win) -> tuple:
    """Whether the mini-map is shown, and how many curves it draws."""
    w = win.canvasStack.currentWidget()
    if hasattr(w, '_minimap_axes'):
        return w._minimap_renderer.isVisible(), len(w._minimap_axes.get_lines()) if w._minimap_axes is not None else 0
    return w._minimap_widget.isVisible(), len(w._minimap_plot.listDataItems())


class MinimapOnImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        self.addCleanup(setattr, AccessHelper, 'pool', AccessHelper.pool)
        AccessHelper.pool = None

    def _window(self, rows: dict, impl: str) -> MTMainWindow:
        """A main window with the plots of `rows` drawn."""
        win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version='test',
                           data_sources=AccessHelper.da.get_connected_data_source_names(),
                           blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl=impl)
        self.addCleanup(win.close)
        win.resize(1000, 800)
        win.show()
        win.dataRangeSelector.import_dict({'mode': MTGenericAccessMode.PULSE_NUMBER, 'pulse_nb': [PULSE_ID],
                                           'base': 'Second(s)', 't_start': '-5', 't_end': '4'})
        win.sigCfgWidget.model.set_dataframe(pd.DataFrame(rows))
        win.draw_clicked()
        self.app.processEvents()
        return win

    def _with_minimap(self, variable: str, impl: str) -> MTMainWindow:
        win = self._window(_rows(variable), impl)
        win.toolBar.minimapAction.setChecked(True)
        self.app.processEvents()
        self.assertEqual(_minimap(win), (True, 1))
        return win

    def _workspace(self, win: MTMainWindow, **changes) -> str:
        """The workspace of the window saved to a file, with `changes` to its top-level entries."""
        path = os.path.join(tempfile.mkdtemp(), 'workspace.json')
        self.addCleanup(shutil.rmtree, os.path.dirname(path))
        workspace = win.export_dict()
        workspace.update(changes)
        with open(path, 'w') as f:
            json.dump(workspace, f)
        return path

    def _import_watching_the_read(self, win: MTMainWindow, path: str) -> tuple:
        """Import the workspace; gives the mini-map and the mini-map button as they were while its data were read."""
        seen = []
        build = win.sigCfgWidget.build

        def build_watched(**kwargs):
            seen.append((_minimap(win), win.toolBar.minimapAction.isEnabled()))
            return build(**kwargs)

        with patch.object(win.sigCfgWidget, 'build', build_watched):
            win.import_json(path)
        self.app.processEvents()
        return seen[0]

    def test_the_mini_map_goes_with_the_plot_while_another_workspace_is_read(self):
        for impl in BACKENDS:
            with self.subTest(impl=impl):
                win = self._with_minimap(VAR1, impl)
                two_plots = self._workspace(self._window(_rows(VAR1, VAR2), impl))

                while_read = self._import_watching_the_read(win, two_plots)

                self.assertEqual(while_read, ((False, 0), False))
                # Two plots have no mini-map.
                self.assertEqual(_minimap(win), (False, 0))
                self.assertFalse(win.toolBar.minimapAction.isEnabled())

    def test_the_mini_map_comes_back_with_the_plot_of_a_workspace_that_shows_it(self):
        for impl in BACKENDS:
            with self.subTest(impl=impl):
                win = self._with_minimap(VAR1, impl)
                other = self._workspace(self._with_minimap(VAR2, impl))

                win.import_json(other)
                self.app.processEvents()

                self.assertEqual(_minimap(win), (True, 1))
                self.assertTrue(win.toolBar.minimapAction.isChecked())
                drawn = [signal.name for signal in win.canvasStack.currentWidget().get_signals(win.canvas)]
                self.assertEqual(drawn, [VAR2])

    def test_a_plot_in_focus_leaves_no_focus_on_the_workspace_imported(self):
        for impl in BACKENDS:
            with self.subTest(impl=impl):
                win = self._window(_rows(VAR1, VAR2), impl)
                w = win.canvasStack.currentWidget()
                w._full_screen_mode_on(w._parser._plot_impl_plot_lut[id(win.canvas.plots[0][0])][0])
                self.app.processEvents()
                self.assertEqual(len(w._parser._plot_impl_plot_lut), 1)
                other = self._workspace(self._window(_rows(VAR2, VAR1), impl))

                win.import_json(other)
                self.app.processEvents()

                self.assertIsNone(win.canvas.focus_plot)
                drawn = [signal.name for signal in w.get_signals(win.canvas)]
                self.assertEqual(drawn, [VAR2, VAR1])
                self.assertEqual(len(w._parser._plot_impl_plot_lut), 2)

    def test_an_import_that_fails_leaves_no_mini_map_behind(self):
        for impl in BACKENDS:
            with self.subTest(impl=impl):
                win = self._with_minimap(VAR1, impl)
                # A workspace without a table fails once the canvas is cleared.
                broken = self._workspace(win, signal_cfg={})

                with patch.object(QMessageBox, 'exec_', return_value=0, create=True), \
                        patch.object(QMessageBox, 'exec', return_value=0):
                    win.import_json(broken)
                self.app.processEvents()

                self.assertIsNone(win.canvasStack.currentWidget().get_canvas())
                self.assertEqual(_minimap(win), (False, 0))
                self.assertFalse(win.toolBar.minimapAction.isEnabled())


if __name__ == '__main__':
    unittest.main()
