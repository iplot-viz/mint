"""Workspace rendering integration tests — the core ask from issue #87.

Programmatically drive MINT end to end: populate the signals table with
CSV-backed variables, trigger the draw, grab the resulting canvas pixmap
and compare it against a committed baseline. Parametrised over matplotlib
and pyqtgraph. The baseline for pyqt is Linux-canonical (Qt's native
rendering drifts across OSes even in offscreen), so pyqt visual tests
skip on non-Linux with a clear reason.
"""

import os
import sys
import unittest

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import BASELINE_DIR, write_csv_datasource_config
from mint.tests.imageCompare import (
    compare_figure_to_baseline, compare_pyqtgraph_scene_to_baseline,
)
from mint.tests.qAppSingleton import ensure_qapp

PYQT_CANONICAL_PLATFORM = 'linux'
BASELINE_TOLERANCE = 5.0
# Fixed render size. For matplotlib we drive the Figure directly, bypassing
# Qt layout so the PNG is deterministic across runs. For pyqt we grab the
# widget (Linux-only).
RENDER_FIGSIZE = (10.0, 7.0)
RENDER_DPI = 100
PYQT_GRAB_SIZE = (1000, 700)


PULSE_ID = 'ITER:MCTB-TEST/111'
# CSV fixture spans -5.0 to 3.5 seconds — pick a window that covers the whole trace.
PULSE_T_START = '-5'
PULSE_T_END = '4'


def _build_main_window(impl: str) -> MTMainWindow:
    canvas = Canvas()
    # Start with an empty time_model; we populate the pulse range via the
    # selector's import_dict below so the radio button, stacked widget and
    # mapper end up in a mutually consistent state (setting mappings in the
    # constructor alone leaves the stack pointing at TIME_RANGE).
    time_model = {"range": {}}
    data_sources = AccessHelper.da.get_connected_data_source_names()
    win = MTMainWindow(
        canvas,
        AccessHelper.da,
        time_model,
        app_version='test',
        data_sources=data_sources,
        blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT,
        impl=impl,
    )
    win.dataRangeSelector.import_dict({
        'mode': MTGenericAccessMode.PULSE_NUMBER,
        'pulse_nb': [PULSE_ID],
        'base': 'Second(s)',
        't_start': PULSE_T_START,
        't_end': PULSE_T_END,
    })
    return win


def _populate_two_signals(win: MTMainWindow) -> None:
    df = pd.DataFrame({
        'DS': ['csv', 'csv'],
        'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
        'Stack': ['1.1', '1.2'],
        'Plot type': ['PlotXY', 'PlotXY'],
    })
    win.sigCfgWidget.model.set_dataframe(df)


class WorkspaceRenderingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()
        os.makedirs(BASELINE_DIR, exist_ok=True)

    def _render_and_compare(self, impl: str, name: str) -> None:
        if impl == 'pyqt' and not sys.platform.startswith(PYQT_CANONICAL_PLATFORM):
            self.skipTest("pyqt visual baselines are canonical on Linux only")

        win = _build_main_window(impl)
        try:
            _populate_two_signals(win)
            win.draw_clicked()
            self.app.processEvents()

            baseline = os.path.join(BASELINE_DIR, f"{name}_{impl}.png")
            if impl == 'matplotlib':
                compare_figure_to_baseline(
                    win.qtcanvas._parser.figure, baseline,
                    tol=BASELINE_TOLERANCE,
                    figsize=RENDER_FIGSIZE, dpi=RENDER_DPI)
            else:
                scene = win.qtcanvas._parser.figure.scene()
                compare_pyqtgraph_scene_to_baseline(
                    scene, baseline,
                    tol=BASELINE_TOLERANCE, width=PYQT_GRAB_SIZE[0])
        finally:
            win.close()

    def test_two_signals_stacked_matplotlib(self):
        self._render_and_compare('matplotlib', "two_signals_stacked")

    def test_two_signals_stacked_pyqtgraph(self):
        self._render_and_compare('pyqt', "two_signals_stacked")


if __name__ == '__main__':
    unittest.main()
