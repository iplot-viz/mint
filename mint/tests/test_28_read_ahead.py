"""Draw, the relative-time refresh and the workspace import read the data of all their
rows at once, through AccessHelper.pool (worker processes), and then build the canvas
from those results exactly as from reads made in the GUI thread."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

PULSE_ID = 'ITER:MCTB-TEST/111'
_read_in_this_process = AccessHelper._request_data


class _PoolStub:
    """Reads in this process, like the workers would, and records what it is asked."""

    def __init__(self, interrupted=False):
        self.requests = []
        self.cache_clears = 0
        self.interrupted = interrupted

    def fetch(self, requests, progress=None):
        requests = list(requests)
        self.requests.append(requests)
        if self.interrupted:
            return None
        results = {}
        for params in requests:
            try:
                results[AccessHelper.request_key(params)] = _read_in_this_process(**dict(params))
            except Exception as e:
                results[AccessHelper.request_key(params)] = e
        if progress is not None:
            progress(len(results), len(results))
        return results

    def clear_cache(self):
        self.cache_clears += 1


def _drawn_data(win):
    return {signal.name: np.asarray(signal.y_data).copy()
            for signal in win.canvasStack.currentWidget().get_signals(win.canvas)}


# Reading ahead ships in iplotlib; mint's CI installs iplotlib from develop,
# so these integration tests run only once that change reaches develop.
@unittest.skipUnless(hasattr(AccessHelper, 'prefetched'), "the installed iplotlib does not read ahead")
class ReadAheadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        self._pool = AccessHelper.pool
        self.addCleanup(setattr, AccessHelper, 'pool', self._pool)

    def _main_window(self, rows) -> MTMainWindow:
        win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version='test',
                           data_sources=AccessHelper.da.get_connected_data_source_names(),
                           blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl='matplotlib')
        self.addCleanup(win.close)
        win.dataRangeSelector.import_dict({'mode': MTGenericAccessMode.PULSE_NUMBER, 'pulse_nb': [PULSE_ID],
                                           'base': 'Second(s)', 't_start': '-5', 't_end': '4'})
        win.sigCfgWidget.model.set_dataframe(pd.DataFrame(rows))
        return win

    def _two_plots(self):
        return self._main_window({'DS': ['csv', 'csv'], 'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
                                  'Stack': ['1.1', '1.2'], 'Plot type': ['PlotXY', 'PlotXY']})

    def test_draw_reads_ahead_and_draws_the_same_data(self):
        AccessHelper.pool = None
        expected = self._two_plots()
        expected.draw_clicked()

        AccessHelper.pool = pool = _PoolStub()
        win = self._two_plots()
        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win.draw_clicked()

        self.assertEqual(len(pool.requests), 1)
        self.assertEqual({params['varname'] for params in pool.requests[0]}, {'MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'})
        drawn, reference = _drawn_data(win), _drawn_data(expected)
        self.assertEqual(set(drawn), set(reference))
        for name in reference:
            self.assertGreater(len(reference[name]), 0)
            np.testing.assert_array_equal(drawn[name], reference[name])

    def test_rows_that_are_not_read_are_not_read_ahead(self):
        AccessHelper.pool = pool = _PoolStub()
        win = self._main_window({'DS': ['csv', 'csv'], 'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
                                 'Stack': ['1.1', ''], 'Plot type': ['PlotXY', 'PlotXY']})

        win.draw_clicked()

        self.assertEqual([params['varname'] for params in pool.requests[0]], ['MAG-MCTB-F1:VAR1'])

    def test_an_interrupted_read_leaves_the_canvas_alone(self):
        win = self._two_plots()
        AccessHelper.pool = _PoolStub(interrupted=True)

        with patch.object(win.qtcanvas, 'set_canvas') as set_canvas:
            win.draw_clicked()

        set_canvas.assert_not_called()

    def test_a_refresh_tick_is_skipped_while_data_are_read(self):
        win = self._two_plots()
        win._reading_ahead = True

        with patch.object(win, 'build') as build:
            win.on_timeout()

        build.assert_not_called()

    def test_progress_is_shown_while_reading(self):
        AccessHelper.pool = _PoolStub()
        win = self._two_plots()
        with patch.object(win, '_report_read_progress', wraps=win._report_read_progress) as report:
            win.draw_clicked()

        report.assert_called_with(2, 2)

    def test_clear_cache_reaches_the_workers(self):
        AccessHelper.pool = pool = _PoolStub()
        win = self._two_plots()

        win.clear_cache()

        self.assertEqual(pool.cache_clears, 1)

    def test_workspace_import_reads_ahead(self):
        AccessHelper.pool = None
        source = self._two_plots()
        source.draw_clicked()
        path = os.path.join(tempfile.mkdtemp(), 'workspace.json')
        self.addCleanup(os.remove, path)
        with open(path, 'w') as f:
            json.dump(source.export_dict(), f)

        AccessHelper.pool = pool = _PoolStub()
        win = self._main_window({'DS': [], 'Variable': [], 'Stack': [], 'Plot type': []})
        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win.import_json(path)

        self.assertEqual(len(pool.requests), 1)
        drawn, reference = _drawn_data(win), _drawn_data(source)
        self.assertEqual(set(drawn), set(reference))
        for name in reference:
            np.testing.assert_array_equal(drawn[name], reference[name])

    def test_draw_with_worker_processes(self):
        from iplotlib.data_access import AccessPool
        AccessHelper.pool = pool = AccessPool(1)
        self.addCleanup(pool.shutdown)
        win = self._two_plots()

        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win.draw_clicked()

        drawn = _drawn_data(win)
        self.assertEqual(set(drawn), {'MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'})
        self.assertTrue(all(len(values) > 0 for values in drawn.values()))


if __name__ == '__main__':
    unittest.main()
