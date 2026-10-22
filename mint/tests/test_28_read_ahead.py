"""Draw, the relative-time refresh and the workspace import read the data of all their
rows at once, through AccessHelper.pool (worker processes), and then build the canvas
from those results exactly as from reads made in the GUI thread."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper, ParserHelper
from mint.app.createApp import data_access_workers
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import CSV_DIR, write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

PULSE_ID = 'ITER:MCTB-TEST/111'
OTHER_PULSE_ID = 'ITER:MCTB-TEST/222'
VAR1, VAR2 = 'MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'
_read_in_this_process = AccessHelper._request_data


class _PoolStub:
    """Reads in this process, like the workers would, and records what it is asked."""

    def __init__(self, interrupted=False):
        self.requests = []
        self.cache_clears = 0
        self.interrupted = interrupted
        self.shut_down = False

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

    def shutdown(self):
        self.shut_down = True


def _drawn_data(win):
    return {signal.name: np.asarray(signal.y_data).copy()
            for signal in win.canvasStack.currentWidget().get_signals(win.canvas)}


def _drawn(win):
    """Label and values of every signal drawn, in drawing order."""
    return [(signal.label, np.asarray(signal.y_data).tolist())
            for signal in win.canvasStack.currentWidget().get_signals(win.canvas)]


def _status(win):
    return win.sigCfgWidget.model.get_dataframe()['Status'].tolist()


class _MainWindowTestCase(unittest.TestCase):
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

    def _workspace_file(self, workspace: dict) -> str:
        path = os.path.join(tempfile.mkdtemp(), 'workspace.json')
        self.addCleanup(shutil.rmtree, os.path.dirname(path))
        with open(path, 'w') as f:
            json.dump(workspace, f)
        return path


@unittest.skipUnless(hasattr(AccessHelper, 'prefetched'), "the installed iplotlib does not read ahead")
class ReadAheadTest(_MainWindowTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def _two_plots(self):
        return self._main_window({'DS': ['csv', 'csv'], 'Variable': [VAR1, VAR2],
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
        self.assertEqual({params['varname'] for params in pool.requests[0]}, {VAR1, VAR2})
        drawn, reference = _drawn_data(win), _drawn_data(expected)
        self.assertEqual(set(drawn), set(reference))
        for name in reference:
            self.assertGreater(len(reference[name]), 0)
            np.testing.assert_array_equal(drawn[name], reference[name])

    def test_rows_that_are_not_read_are_not_read_ahead(self):
        AccessHelper.pool = pool = _PoolStub()
        win = self._main_window({'DS': ['csv', 'csv'], 'Variable': [VAR1, VAR2],
                                 'Stack': ['1.1', ''], 'Plot type': ['PlotXY', 'PlotXY']})

        win.draw_clicked()

        self.assertEqual([params['varname'] for params in pool.requests[0]], [VAR1])

    def test_a_row_that_uses_an_alias_that_failed_is_not_drawn(self):
        rows = {'DS': ['csv', 'csv'], 'Variable': ['NO-SUCH-VAR', ''], 'Alias': ['B', 'C'],
                'y': ['', '${B}.data*2'], 'Stack': ['', '1.1'], 'Plot type': ['PlotXY', 'PlotXY']}
        for pool in (None, _PoolStub()):
            with self.subTest(pool=pool):
                AccessHelper.pool = pool
                win = self._main_window(rows)

                win.draw_clicked()

                self.assertEqual(_status(win)[1], 'Ready')
                self.assertEqual(win.sigCfgWidget.model._table_fails.at[1, 'y'], 2)
                self.assertEqual(_drawn(win), [])

    def test_an_interrupted_read_leaves_the_canvas_alone(self):
        win = self._two_plots()
        AccessHelper.pool = _PoolStub(interrupted=True)

        with patch.object(win.qtcanvas, 'set_canvas') as set_canvas:
            win.draw_clicked()

        set_canvas.assert_not_called()

    def test_a_refresh_tick_that_comes_while_reading_is_skipped(self):
        win = self._two_plots()
        AccessHelper.pool = pool = _PoolStub()

        def fetch_during_a_tick(requests, progress=None):
            win.on_timeout()
            return _PoolStub.fetch(pool, requests, progress)

        pool.fetch = fetch_during_a_tick
        with patch.object(win, 'build', wraps=win.build) as build:
            win.draw_clicked()

        self.assertEqual(build.call_count, 1)
        self.assertFalse(win._reading_ahead)

    def test_a_refresh_tick_reads_ahead(self):
        AccessHelper.pool = pool = _PoolStub()
        win = self._two_plots()
        win.draw_clicked()

        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win.on_timeout()

        self.assertEqual(len(pool.requests), 2)
        self.assertEqual(len(_drawn(win)), 2)

    def test_progress_is_shown_while_reading(self):
        AccessHelper.pool = _PoolStub()
        win = self._two_plots()
        with patch.object(win, '_report_read_progress', wraps=win._report_read_progress) as report:
            win.draw_clicked()

        report.assert_called_with(2, 2)

    def test_a_pool_that_fails_leaves_the_reads_to_this_process(self):
        AccessHelper.pool = None
        expected = self._two_plots()
        expected.draw_clicked()

        class _FailingPool(_PoolStub):
            def fetch(self, requests, progress=None):
                raise RuntimeError("the workers cannot start")

        AccessHelper.pool = pool = _FailingPool()
        win = self._two_plots()
        win.draw_clicked()

        self.assertIsNone(AccessHelper.pool)
        self.assertTrue(pool.shut_down)
        self.assertEqual(_drawn(win), _drawn(expected))
        self.assertTrue(win._progressBar.isHidden())
        self.assertFalse(win._reading_ahead)

    def test_the_copy_of_a_duplicate_is_read_ahead(self):
        AccessHelper.pool = pool = _PoolStub()
        win = self._two_plots()
        win.draw_clicked()
        uid = win.sigCfgWidget.model.get_dataframe().at[0, 'uid']
        original, _ = win._find_signal_in_canvas(uid)

        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win._on_signal_shift_requested(uid, original.name, original.data_source, str(original.pulse_nb),
                                           0.0, 2.5, True)

        self.assertEqual(len(pool.requests), 2)
        copy = win.canvas.plots[0][0].signals[1][-1]
        self.assertIsNot(copy, original)
        np.testing.assert_allclose(copy.y_data, np.asarray(original.y_data) + 2.5)

    def test_the_copy_of_a_duplicate_ends_the_progress_of_its_reads(self):
        AccessHelper.pool = _PoolStub()
        win = self._two_plots()
        win.draw_clicked()
        uid = win.sigCfgWidget.model.get_dataframe().at[0, 'uid']
        original, _ = win._find_signal_in_canvas(uid)

        win._on_signal_shift_requested(uid, original.name, original.data_source, str(original.pulse_nb),
                                       0.0, 2.5, True)

        self.assertTrue(win._progressBar.isHidden())
        self.assertEqual(win.statusBar().currentMessage(), 'Ready.')

    def test_the_clear_cache_menu_action_reaches_the_workers(self):
        AccessHelper.pool = pool = _PoolStub()
        win = self._two_plots()
        action = next(action for action in win.findChildren(QAction) if action.text() == "Clear cache")

        with patch.object(win.da, 'clear_cache') as clear_cache:
            action.trigger()

        self.assertEqual(pool.cache_clears, 1)
        clear_cache.assert_called_once()

    def test_workspace_import_reads_ahead(self):
        AccessHelper.pool = None
        source = self._two_plots()
        source.draw_clicked()
        path = self._workspace_file(source.export_dict())

        AccessHelper.pool = pool = _PoolStub()
        win = self._main_window({'DS': [], 'Variable': [], 'Stack': [], 'Plot type': []})
        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win.import_json(path)

        self.assertEqual(len(pool.requests), 1)
        drawn, reference = _drawn_data(win), _drawn_data(source)
        self.assertEqual(set(drawn), set(reference))
        for name in reference:
            np.testing.assert_array_equal(drawn[name], reference[name])

    def test_workspace_import_reads_ahead_the_ranges_the_signals_were_saved_with(self):
        AccessHelper.pool = None
        source = self._two_plots()
        source.draw_clicked()
        workspace = source.export_dict()
        # As saved after a zoom that read the data again.
        for column in workspace['main_canvas']['plots']:
            for plot in column:
                for stack in plot['signals'].values():
                    for signal in stack:
                        signal.update(ts_start=-3.0, ts_end=2.0)
        path = self._workspace_file(workspace)
        empty = {'DS': [], 'Variable': [], 'Stack': [], 'Plot type': []}
        expected = self._main_window(empty)
        expected.import_json(path)

        AccessHelper.pool = _PoolStub()
        win = self._main_window(empty)
        progress_maxima = []
        win.sigCfgWidget.progressChanged.connect(lambda _value: progress_maxima.append(win._progressBar.maximum()))
        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win.import_json(path)

        self.assertEqual(_drawn(win), _drawn(expected))
        self.assertEqual([len(values) for label, values in _drawn(win)], [6, 6])
        # The import counts its own progress out of 100 once the data are read (0: the bar only shows activity).
        self.assertLessEqual(set(progress_maxima), {0, 100})
        self.assertIn(100, progress_maxima)

    def test_draw_with_worker_processes(self):
        from iplotlib.data_access import AccessPool
        AccessHelper.pool = None
        expected = self._two_plots()
        expected.draw_clicked()

        AccessHelper.pool = pool = AccessPool(1)
        self.addCleanup(pool.shutdown)
        win = self._two_plots()
        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read in the GUI thread")):
            win.draw_clicked()

        self.assertEqual(_status(win), _status(expected))
        drawn, reference = (win.canvasStack.currentWidget().get_signals(window.canvas) for window in (win, expected))
        self.assertEqual(len(drawn), 2)
        for signal, signal_expected in zip(drawn, reference):
            self.assertEqual(signal.label, signal_expected.label)
            self.assertEqual(signal.isDownsampled, signal_expected.isDownsampled)
            for data, data_expected in ((signal.x_data, signal_expected.x_data), (signal.y_data, signal_expected.y_data)):
                np.testing.assert_array_equal(data, data_expected)
                self.assertEqual(np.asarray(data).dtype, np.asarray(data_expected).dtype)
                self.assertEqual(getattr(data, 'unit', None), getattr(data_expected, 'unit', None))


@unittest.skipUnless(hasattr(AccessHelper, 'prefetched'), "the installed iplotlib does not read ahead")
class ReadAheadContractTest(_MainWindowTestCase):
    """Whatever the table, Draw asks the workers for every read it makes in the GUI thread
    without them, reads nothing in the GUI thread, and ends the same."""

    TABLES = {
        'plain': {'Variable': [VAR1, VAR2], 'Stack': ['1.1', '1.2']},
        'a row with no stack': {'Variable': [VAR1, VAR2], 'Stack': ['1.1', '']},
        'an expression': {'Variable': ['${%s} + ${%s}' % (VAR1, VAR2)], 'Stack': ['1.1']},
        'an alias in an expression': {'Variable': [VAR1, '${a} * 2'], 'Alias': ['a', ''], 'Stack': ['', '1.1']},
        'an expression of an expression': {'Variable': [VAR1, '${a} * 2', '${b} + 1'], 'Alias': ['a', 'b', ''],
                                           'Stack': ['', '', '1.1']},
        'x versus y': {'Variable': [VAR1, VAR2, ''], 'Alias': ['a', 'b', 'xy'],
                       'x': ['', '', '${a}.data'], 'y': ['', '', '${b}.data'], 'Stack': ['', '', '1.1']},
        'x versus y, narrower than its aliases': {'Variable': [VAR1, VAR2, ''], 'Alias': ['a', 'b', 'xy'],
                                                  'x': ['', '', '${a}.data'], 'y': ['', '', '${b}.data'],
                                                  'StartTime': ['', '', '-3'], 'EndTime': ['', '', '2'],
                                                  'Stack': ['', '', '1.1']},
        'x versus y, wider than its aliases': {'Variable': [VAR1, VAR2, ''], 'Alias': ['a', 'b', 'xy'],
                                               'x': ['', '', '${a}.data'], 'y': ['', '', '${b}.data'],
                                               'StartTime': ['-3', '-3', ''], 'EndTime': ['2', '2', ''],
                                               'Stack': ['', '', '1.1']},
        'y on a narrower alias': {'Variable': [VAR1, VAR2], 'Alias': ['a', ''], 'y': ['', '${a}.data * 2'],
                                  'StartTime': ['-3', ''], 'EndTime': ['2', ''], 'Stack': ['', '1.1']},
        'rows with ranges of their own': {'Variable': [VAR1, VAR1], 'StartTime': ['-3', ''], 'EndTime': ['2', ''],
                                          'Stack': ['1.1', '1.2']},
        'two pulses in a row': {'Variable': [VAR1], 'PulseId': [f'{PULSE_ID},{OTHER_PULSE_ID}'], 'Stack': ['1.1']},
        'one variable in two pulses': {'Variable': [VAR1, VAR1], 'PulseId': [PULSE_ID, OTHER_PULSE_ID],
                                       'Stack': ['1.1', '1.2']},
        'a variable that does not exist': {'Variable': ['NO-SUCH-VAR', VAR1], 'Stack': ['1.1', '1.2']},
        'an expression of a variable that does not exist': {'Variable': ['${NO-SUCH-VAR} + ${%s}' % VAR1],
                                                           'Stack': ['1.1']},
        'y on an alias that failed': {'Variable': ['NO-SUCH-VAR', ''], 'Alias': ['b', ''], 'y': ['', '${b}.data*2'],
                                      'Stack': ['', '1.1']},
    }

    # Tables whose only plot fails on purpose.
    NOT_DRAWN = {'an expression of a variable that does not exist', 'y on an alias that failed'}

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        # The test pulse, and a second one with other values.
        cls.folder = tempfile.mkdtemp()
        pulses = os.path.join(cls.folder, 'ITER', 'MCTB-TEST')
        os.makedirs(pulses)
        data = pd.read_csv(os.path.join(CSV_DIR, 'MCTB-TEST', 'data_111.csv'))
        data.to_csv(os.path.join(pulses, 'data_111.csv'), index=False)
        data.iloc[:, 1:] += 100
        data.to_csv(os.path.join(pulses, 'data_222.csv'), index=False)
        config = os.path.join(cls.folder, 'sources.cfg')
        with open(config, 'w') as f:
            json.dump({'pulses': {'path': os.path.join(cls.folder, 'ITER').replace('\\', '/'), 'type': 'CSV'}}, f)
        AppDataAccess.initialize(config)
        AccessHelper.da = AppDataAccess.get_data_access()

    @classmethod
    def tearDownClass(cls) -> None:
        AccessHelper.da.ds_list.pop('pulses', None)
        shutil.rmtree(cls.folder)

    def _draw(self, table: dict, pool):
        rows = dict(table, **{'DS': ['pulses'] * len(table['Variable']),
                              'Plot type': ['PlotXY'] * len(table['Variable'])})
        AccessHelper.pool = pool
        ParserHelper.env.clear()
        win = self._main_window(rows)
        reads = []

        def read_in_the_gui_thread(**params):
            reads.append(AccessHelper.request_key(params))
            return _read_in_this_process(**params)

        with patch.object(AccessHelper, '_request_data', side_effect=read_in_the_gui_thread):
            win.draw_clicked()
        return reads, _status(win), _drawn(win)

    def test_draw_reads_everything_in_the_workers(self):
        for name, table in self.TABLES.items():
            with self.subTest(table=name):
                reads, expected_status, expected = self._draw(table, None)
                self.assertNotEqual(bool(expected), name in self.NOT_DRAWN)
                pool = _PoolStub()

                reads_in_gui_thread, status, drawn = self._draw(table, pool)

                self.assertEqual(reads_in_gui_thread, [])
                asked = {AccessHelper.request_key(params) for requests in pool.requests for params in requests}
                self.assertLessEqual(set(reads), asked)
                self.assertEqual(status, expected_status)
                self.assertEqual(drawn, expected)


class _PoolStartingStub(_PoolStub):
    """Records the data sources it is asked to start the workers of."""

    def __init__(self):
        super().__init__()
        self.prepared = []

    def prepare(self, data_source_names):
        self.prepared.append(set(data_source_names))


@unittest.skipUnless(hasattr(AccessHelper, 'pool'), "the installed iplotlib reads in the GUI thread")
class WorkersStartTest(_MainWindowTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def test_the_workers_of_the_data_sources_in_the_table_start_before_the_draw(self):
        AccessHelper.pool = pool = _PoolStartingStub()

        self._main_window({'DS': ['csv', 'codacuda'], 'Variable': [VAR1, ''],
                           'Stack': ['1.1', '1.2'], 'Plot type': ['PlotXY', 'PlotXY']})
        self.app.processEvents()

        self.assertEqual(pool.prepared[-1], {'csv'})
        self.assertEqual(pool.requests, [])

    def test_a_variable_typed_in_starts_the_workers_of_its_data_source(self):
        AccessHelper.pool = pool = _PoolStartingStub()
        win = self._main_window({'DS': ['csv'], 'Variable': [''], 'Stack': ['1.1'], 'Plot type': ['PlotXY']})
        self.app.processEvents()
        model = win.sigCfgWidget.model
        before = set().union(*pool.prepared)

        model.setData(model.index(0, model._table.columns.get_loc('Variable')), VAR1, Qt.ItemDataRole.EditRole)
        self.app.processEvents()

        self.assertNotIn('csv', before)
        self.assertEqual(pool.prepared[-1], {'csv'})


class DataAccessWorkersTest(unittest.TestCase):
    def test_the_environment_variable_sets_the_number_of_workers(self):
        cases = {None: 2, '': 2, '3': 3, ' 3 ': 3, '0': 0, '8': 8, '9': 8, '-1': 0, 'two': 2, '2.5': 2}
        for value, workers in cases.items():
            with self.subTest(value=value), patch.dict(os.environ):
                os.environ.pop('MINT_DATA_ACCESS_WORKERS', None)
                if value is not None:
                    os.environ['MINT_DATA_ACCESS_WORKERS'] = value
                self.assertEqual(data_access_workers(), workers)


if __name__ == '__main__':
    unittest.main()
