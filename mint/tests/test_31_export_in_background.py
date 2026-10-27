"""The export of the data to parquet or hdf5 runs in a worker process of its own while MINT goes on drawing. It
exports the table as it was when it started, reports its progress apart from the other tasks, and ends with the
same message as before; one runs at a time, and quitting MINT meanwhile asks first. Without worker processes it
runs in the GUI thread, as before.

The export script of iplotDataAccess reads from UDA: a stand-in takes its place, in the worker process that exports
too, except in ExportInAWorkerProcessTest."""

import importlib.util
import os
import shutil
import sys
import tempfile
import time
import unittest
from functools import partial
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pandas as pd
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
import iplotlib.data_access as iplot_data_access
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp
from mint.tools.data_export import export_data_source

EXPORT_SCRIPT = 'iplotDataAccess.dataHandling.exportData.exportData'
PULSE_ID = 'ITER:MCTB-TEST/111'
UDA = 'codacuda'
VAR1, VAR2 = 'UDA-TEST:VAR1', 'UDA-TEST:VAR2'
# A variable of the CSV data source of the tests, which MINT draws.
DRAWN = 'MAG-MCTB-F1:VAR1'
T0 = 1_788_873_880_000_000_000
T1 = T0 + 3600 * 10 ** 9


class _ExportScript:
    """Stands in for the export script of iplotDataAccess: writes the variables it is asked for to the output
    file, telling each as it starts and taking `hold` seconds for each, and keeps what it was asked."""

    def __init__(self, hold: float = 0.0):
        self.hold = hold
        self.calls = []
        self.fail = None
        # Called as each call starts.
        self.on_call = None
        self.module = ModuleType(EXPORT_SCRIPT)
        self.module.generateData = self.generateData
        self.module.connectUDA = self.connectUDA

    def generateData(self, logfile, conn, csvfile, formatType, startTime, endTime, outputFolder, chunkS=100000,
                     progressCallback=None, relativeTime=False, resampleFreq=None):
        if self.on_call is not None:
            self.on_call()
        with open(csvfile) as f:
            variables = [line.strip() for line in f if line.strip()]
        self.calls.append(dict(conn=conn, csvfile=csvfile, variables=variables, formatType=formatType,
                               startTime=startTime, endTime=endTime, outputFolder=str(outputFolder),
                               relativeTime=relativeTime, resampleFreq=resampleFreq))
        for line in variables:
            if progressCallback is not None:
                progressCallback(line.split(',')[0])
            time.sleep(self.hold)
        if self.fail:
            return False, self.fail
        with open(outputFolder, 'w') as f:
            f.write('\n'.join(variables))
        return True, ""

    @staticmethod
    def connectUDA(host, port=3090):
        return SimpleNamespace(UCR=None, errc=0 if host == 'export-server' else -1, host=host)


def _uda_source(pulses: dict = None, uda_for_export=None):
    """A UDA data source as the export finds it, with `pulses`: their start and end by name."""
    pulses = {PULSE_ID: (T0, T1)} if pulses is None else pulses

    def get_pulse_info(pulse):
        if pulse not in pulses:
            return None
        return SimpleNamespace(timeFrom=pulses[pulse][0], timeTo=pulses[pulse][1])

    return SimpleNamespace(source_type='CODAC_UDA', uda_for_export=uda_for_export, port=3090,
                           get_pulse_info=get_pulse_info)


def _iso(t_ns: int) -> str:
    return pd.to_datetime(t_ns).isoformat().replace(':', '-')


def _put_back(name: str, module):
    """Put back the module `name` as it was in sys.modules: none, if `module` is None."""
    if module is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = module


class _ExportProcess:
    """Stands in for the worker process that exports: makes the calls of call_later() in this process when the
    test lets it, as the worker would have meanwhile."""

    def __init__(self, data_access):
        self.data_access = data_access
        self.waiting = []
        self.prepared = []
        self.cache_clears = 0
        self.shut_down = False

    def prepare(self, data_source_names):
        self.prepared.extend(data_source_names)

    def clear_cache(self):
        self.cache_clears += 1

    def call_later(self, method, data_s_name, on_done, progress=None, **kwargs):
        call = SimpleNamespace(cancelled=False)
        call.cancel = lambda: setattr(call, 'cancelled', True)
        self.waiting.append((call, method, data_s_name, on_done, progress, kwargs))
        return call

    def make_calls(self, outcome=None):
        """Make the calls waiting; `outcome`, if given, is what they end in, as when the process stops."""
        while self.waiting:
            call, method, data_s_name, on_done, progress, kwargs = self.waiting.pop(0)
            if call.cancelled:
                continue
            on_done(outcome if outcome is not None else method(self.data_access, data_s_name, progress=progress,
                                                                 **kwargs))

    def shutdown(self):
        self.shut_down = True


def _rows(*rows) -> pd.DataFrame:
    """A table of the rows, data source and variable each, with a plot each."""
    return pd.DataFrame({'DS': [ds for ds, _ in rows], 'Variable': [variable for _, variable in rows],
                         'Stack': [f'{k + 1}.1' for k in range(len(rows))],
                         'Comment': [f'about {variable}' for _, variable in rows]})


class _ExportTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        # The data of the plots are read in this thread, also with the iplotlib releases that read them in
        # worker processes.
        if hasattr(AccessHelper, 'pool'):
            self.addCleanup(setattr, AccessHelper, 'pool', AccessHelper.pool)
            AccessHelper.pool = None
        self.script = _ExportScript()
        # Only this module: patch.dict would take back every module imported meanwhile, which would be imported again
        # as other modules.
        self.addCleanup(_put_back, EXPORT_SCRIPT, sys.modules.get(EXPORT_SCRIPT))
        sys.modules[EXPORT_SCRIPT] = self.script.module
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)


class _ExportInWindowTestCase(_ExportTestCase):

    def _window(self, table: pd.DataFrame, process: bool = True) -> MTMainWindow:
        """A main window with the table, in pulse mode, and with an export process that waits for the test unless
        not `process`. Its popups are kept in self.popups."""
        win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version='test',
                           data_sources=AccessHelper.da.get_connected_data_source_names(),
                           blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl='matplotlib')
        self.addCleanup(win.close)
        # An export that a failed test left running would ask whether to quit, and wait for an answer.
        self.addCleanup(setattr, win, '_export', None)
        win.dataRangeSelector.import_dict({'mode': MTGenericAccessMode.PULSE_NUMBER, 'pulse_nb': [PULSE_ID],
                                           'base': 'Second(s)', 't_start': '-5', 't_end': '4'})
        win.sigCfgWidget.model.set_dataframe(table)
        # The UDA data source that the export finds.
        uda = patch.dict(win.da.ds_list, {UDA: _uda_source()})
        uda.start()
        self.addCleanup(uda.stop)
        if process:
            win._exportPool = self.process = _ExportProcess(win.da)
        self.popups = []
        popup = patch.object(win, 'show_popup_msg', side_effect=lambda *args: self.popups.append(args))
        popup.start()
        self.addCleanup(popup.stop)
        self.progress = []
        show = win._show_export_progress
        progress = patch.object(win, '_show_export_progress',
                                side_effect=lambda name=None: (show(name), self.progress.append(
                                    win._exportLabel.toolTip())))
        progress.start()
        self.addCleanup(progress.stop)
        return win

    def _export(self, win: MTMainWindow, **settings):
        data = dict(format='.parquet', chunks=1000, output_path=os.path.join(self.folder, 'out.parquet'),
                    relative_time=False, resample_freq=None)
        data.update(settings)
        win.on_export_started(data)

    #: What the window shows while an export runs, and once none does (see _shown).
    EXPORTING = (True, True, False, "Exporting...")
    IDLE = (False, False, True, "Export")

    @staticmethod
    def _shown(win: MTMainWindow) -> tuple:
        """Whether the progress of the export shows, and whether the Export button can be clicked, with its label."""
        return (not win._exportLabel.isHidden(), not win._exportProgress.isHidden(), win.exportBtn.isEnabled(),
                win.exportBtn.text())

    def _run_events(self, until=lambda: False, timeout: float = 300.0):
        """Run the Qt events until `until` holds, or for `timeout` seconds."""
        deadline = time.monotonic() + timeout
        while not until() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)


class ExportInBackgroundTest(_ExportInWindowTestCase):

    def test_the_export_runs_in_its_process_and_ends_with_the_same_message(self):
        win = self._window(_rows((UDA, VAR1), (UDA, VAR2)))

        self._export(win)

        # Nothing is exported yet: the export runs in its process while MINT goes on.
        self.assertEqual(self.script.calls, [])
        self.assertEqual(self._shown(win), self.EXPORTING)
        self.assertEqual(self.popups, [])

        self.process.make_calls()

        call, = self.script.calls
        self.assertEqual(call['variables'], [f'{VAR1},about {VAR1}', f'{VAR2},about {VAR2}'])
        self.assertEqual((call['formatType'], call['startTime'], call['endTime']), ('parquet', str(T0), str(T1)))
        self.assertEqual(call['outputFolder'], os.path.join(self.folder, f'{UDA}_{_iso(T0)}_out.parquet'))
        self.assertTrue(os.path.exists(call['outputFolder']))
        # The variables went to the script in a file of the export's own, removed after.
        self.assertFalse(os.path.exists(call['csvfile']))
        self.assertEqual(self.progress, ["Exporting ..", f"Exporting {VAR1} (1/2) ..", f"Exporting {VAR2} (2/2) .."])
        self.assertEqual(self.popups, [("Export completed", "The data export process finished successfully",
                                        QMessageBox.Icon.Information)])
        self.assertEqual(self._shown(win), self.IDLE)

    def test_mint_draws_while_the_export_runs_and_the_export_keeps_the_table_it_started_from(self):
        win = self._window(_rows((UDA, VAR1), (UDA, VAR2)))
        self._export(win)

        win.sigCfgWidget.model.set_dataframe(_rows(('csv', DRAWN)))
        win.draw_clicked()

        drawn = [signal.name for signal in win.canvasStack.currentWidget().get_signals(win.canvas)]
        self.assertEqual(drawn, [DRAWN])
        # The Draw leaves the progress of the export alone.
        self.assertEqual(self._shown(win), self.EXPORTING)

        self.process.make_calls()

        self.assertEqual(self.script.calls[0]['variables'], [f'{VAR1},about {VAR1}', f'{VAR2},about {VAR2}'])
        self.assertEqual(self.popups[0][0], "Export completed")

    def test_an_export_runs_at_a_time(self):
        win = self._window(_rows((UDA, VAR1)))

        self._export(win)
        self._export(win, output_path=os.path.join(self.folder, 'other.parquet'))

        self.assertEqual(len(self.process.waiting), 1)
        self.process.make_calls()
        self.assertEqual(len(self.script.calls), 1)
        self.assertEqual(len(self.popups), 1)
        self.assertEqual(self._shown(win), self.IDLE)

    def test_the_process_that_exports_starts_when_the_export_dialog_opens(self):
        win = self._window(_rows((UDA, VAR1)))

        win.export_clicked()
        win.exportCfgWidget.hide()

        self.assertEqual(self.process.prepared, [UDA])

    def test_a_process_that_exports_that_cannot_start_leaves_the_export_to_the_gui_thread(self):
        win = self._window(_rows((UDA, VAR1)))
        cannot_start = OSError(12, 'Cannot allocate memory')

        with patch.object(self.process, 'prepare', side_effect=cannot_start):
            win.export_clicked()
        win.exportCfgWidget.hide()
        with patch.object(self.process, 'call_later', side_effect=cannot_start):
            self._export(win)

        self.assertEqual(len(self.script.calls), 1)
        self.assertEqual(self.popups[0][0], "Export completed")
        self.assertEqual(self._shown(win), self.IDLE)

    def test_clearing_the_cache_clears_that_of_the_process_that_exports_too(self):
        win = self._window(_rows((UDA, VAR1)))

        with patch.object(win.da, 'clear_cache'):
            win.clear_cache()

        self.assertEqual(self.process.cache_clears, 1)

    def test_without_worker_processes_the_export_runs_in_the_gui_thread_as_before(self):
        win = self._window(_rows((UDA, VAR1)), process=False)

        self._export(win)

        self.assertEqual(len(self.script.calls), 1)
        self.assertEqual(self.popups[0][0], "Export completed")
        self.assertEqual(self._shown(win), self.IDLE)

    def test_without_worker_processes_mint_shows_the_export_before_it_starts(self):
        win = self._window(_rows((UDA, VAR1)), process=False)
        handled = []
        # Stands for the events that paint what shows the export.
        QTimer.singleShot(0, lambda: handled.append('painted'))
        self.script.on_call = lambda: handled.append('export started')

        self._export(win)

        self.assertEqual(handled, ['painted', 'export started'])

    def test_without_worker_processes_quitting_during_the_export_lets_it_end_first_as_before(self):
        win = self._window(_rows((UDA, VAR1)), process=False)
        # The GUI thread that runs the export cannot stop it.
        QTimer.singleShot(0, win.close)

        with patch.object(QMessageBox, 'question') as question:
            self._export(win)

        question.assert_not_called()
        self.assertEqual(len(self.script.calls), 1)
        self.assertEqual(self.popups[0][0], "Export completed")

    def test_an_export_that_fails_says_why(self):
        self.script.fail = "Permission denied: out.parquet"
        win = self._window(_rows((UDA, VAR1)))

        self._export(win)
        self.process.make_calls()

        title, message, icon = self.popups[0]
        self.assertEqual((title, icon), ("Export failed", QMessageBox.Icon.Critical))
        self.assertIn("Permission denied: out.parquet", message)
        self.assertEqual(self._shown(win), self.IDLE)

    def test_an_export_whose_process_stops_says_so(self):
        win = self._window(_rows((UDA, VAR1)))

        self._export(win)
        self.process.make_calls(RuntimeError("The data access process stopped while reading the data"))

        title, message, _ = self.popups[0]
        self.assertEqual(title, "Export failed")
        self.assertIn(f"Export failed for data source '{UDA}': The data access process stopped", message)

    def test_an_export_script_that_cannot_be_loaded_says_so_and_frees_the_export_button(self):
        # As without the UDA client: the export fails, and the next one can start.
        sys.modules[EXPORT_SCRIPT] = None
        win = self._window(_rows((UDA, VAR1)), process=False)

        self._export(win)

        title, message, _ = self.popups[0]
        self.assertEqual(title, "Export failed")
        self.assertIn(f"Export failed for data source '{UDA}'", message)
        self.assertEqual(self._shown(win), self.IDLE)

    def test_the_rows_of_other_data_sources_are_left_out_and_said_so(self):
        win = self._window(_rows((UDA, VAR1), ('csv', DRAWN)))

        self._export(win)
        self.process.make_calls()

        self.assertEqual(self.script.calls[0]['variables'], [f'{VAR1},about {VAR1}'])
        title, message, _ = self.popups[0]
        self.assertEqual(title, "Export completed with issues")
        self.assertIn("The data source: 'csv' is invalid. Only CODAC UDA data sources can be exported", message)

    def test_quitting_while_an_export_runs_asks_first(self):
        win = self._window(_rows((UDA, VAR1)))
        self._export(win)

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            stayed = not win.close()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            closed = win.close()
        self.process.make_calls()

        self.assertTrue(stayed)
        self.assertTrue(closed)
        self.assertTrue(self.process.shut_down)
        self.assertEqual(self.script.calls, [])
        self.assertEqual(self.popups, [])

    def test_an_export_that_ends_while_mint_asks_whether_to_quit_lets_it_quit(self):
        win = self._window(_rows((UDA, VAR1)))
        self._export(win)

        def answer(*args):
            # The export ends while the question waits for the answer.
            self.process.make_calls()
            return QMessageBox.StandardButton.Yes

        with patch.object(QMessageBox, 'question', side_effect=answer):
            closed = win.close()

        self.assertTrue(closed)
        self.assertTrue(self.process.shut_down)
        self.assertEqual(self.popups[0][0], "Export completed")


class ExportDataSourceTest(_ExportTestCase):
    """What the export makes of the data of a data source, in the process that runs it."""

    def _export(self, source, **kwargs) -> dict:
        settings = dict(variables=[(VAR1, 'first')], export_format='hdf5', chunks=10,
                        output_path=os.path.join(self.folder, 'out.hdf5'))
        settings.update(kwargs)
        return export_data_source(SimpleNamespace(ds_list={UDA: source}), UDA, **settings)

    def test_a_pulse_export_writes_a_file_for_each_pulse_named_after_its_start(self):
        progress = []
        source = _uda_source({'P1': (T0, T1), 'P2': (T1, T1 + 10)})

        outcome = self._export(source, pulses=['P1', 'P2', 'P3'], progress=progress.append)

        self.assertEqual((outcome['attempts'], outcome['exported']), (3, 2))
        self.assertEqual(outcome['errors'],
                         [f"Export failed for data source '{UDA}' (pulse P3): the data source has no such pulse"])
        self.assertEqual([(call['startTime'], call['endTime'], os.path.basename(call['outputFolder']))
                          for call in self.script.calls],
                         [(str(T0), str(T1), f'{UDA}_{_iso(T0)}_out.hdf5'),
                          (str(T1), str(T1 + 10), f'{UDA}_{_iso(T1)}_out.hdf5')])
        self.assertEqual(progress, [VAR1, VAR1])

    def test_a_time_range_export_writes_one_file_with_the_time_and_sampling_asked_for(self):
        outcome = self._export(_uda_source(), ts=T0, te=T1, relative_time=True, resample_freq=10)

        call, = self.script.calls
        self.assertEqual((outcome['attempts'], outcome['exported'], outcome['errors']), (1, 1, []))
        self.assertEqual(os.path.basename(call['outputFolder']), f'{UDA}_out.hdf5')
        self.assertEqual((call['relativeTime'], call['resampleFreq']), (True, 10))

    def test_a_pulse_export_keeps_absolute_time(self):
        self._export(_uda_source(), pulses=[PULSE_ID], relative_time=True)

        self.assertFalse(self.script.calls[0]['relativeTime'])

    def test_the_export_server_of_the_data_source_reads_the_data(self):
        self._export(_uda_source(uda_for_export='export-server'), ts=T0, te=T1)

        self.assertEqual(self.script.calls[0]['conn'].host, 'export-server')

    def test_an_export_server_that_does_not_answer_is_said(self):
        outcome = self._export(_uda_source(uda_for_export='down'), ts=T0, te=T1)

        self.assertEqual(outcome, dict(attempts=0, exported=0, errors=[
            f"Export failed for data source '{UDA}': could not connect to export server 'down'"]))
        self.assertEqual(self.script.calls, [])


def _worker_with_the_script(hold: float = 0.0):
    """The data access of the worker process that exports, with the stand-in of the export script in it, which
    takes `hold` seconds for each variable."""
    sys.modules[EXPORT_SCRIPT] = _ExportScript(hold).module
    return SimpleNamespace(ds_list={UDA: _uda_source()}, get_connected_data_source_names=lambda: [UDA])


@unittest.skipUnless(hasattr(getattr(iplot_data_access, 'AccessPool', None), 'call_later'),
                     "the installed iplotlib cannot make calls in its worker processes in the background")
class ExportInAProcessOfItsOwnTest(_ExportInWindowTestCase):
    """The export as the window runs it, in a worker process of its own (see ExportInBackgroundTest)."""

    def _window_and_process(self, table: pd.DataFrame, hold: float = 0.0) -> MTMainWindow:
        # The window starts the process that exports while the data of the plots are read in worker processes,
        # which these tests leave alone.
        AccessHelper.pool = SimpleNamespace(prepare=lambda names: None, clear_cache=lambda: None)
        factory = partial(_worker_with_the_script, hold)

        class ExportPool(iplot_data_access.AccessPool):
            def __init__(self, workers):
                super().__init__(workers, data_access_factory=factory)

        pool_class = patch.object(iplot_data_access, 'AccessPool', ExportPool)
        pool_class.start()
        self.addCleanup(pool_class.stop)
        win = self._window(table, process=False)
        self.addCleanup(lambda: win._exportPool is not None and win._exportPool.shutdown())
        return win

    def test_the_export_runs_in_a_process_of_its_own_and_ends_with_the_same_message(self):
        win = self._window_and_process(_rows((UDA, VAR1), (UDA, VAR2)))

        win.export_clicked()
        win.exportCfgWidget.hide()
        self._export(win)
        exporting = self._shown(win)
        self._run_events(until=lambda: self.popups)

        self.assertEqual(exporting, self.EXPORTING)
        self.assertEqual(self.popups, [("Export completed", "The data export process finished successfully",
                                        QMessageBox.Icon.Information)])
        with open(os.path.join(self.folder, f'{UDA}_{_iso(T0)}_out.parquet')) as f:
            self.assertEqual(f.read().splitlines(), [f'{VAR1},about {VAR1}', f'{VAR2},about {VAR2}'])
        self.assertEqual(self.progress, ["Exporting ..", f"Exporting {VAR1} (1/2) ..", f"Exporting {VAR2} (2/2) .."])
        self.assertEqual(self._shown(win), self.IDLE)
        # The stand-in of the export script of this process exported nothing.
        self.assertEqual(self.script.calls, [])

    def test_quitting_while_the_export_runs_stops_its_process(self):
        win = self._window_and_process(_rows((UDA, VAR1)), hold=60)
        self._export(win)
        # The process exports the variable.
        self._run_events(until=lambda: len(self.progress) > 1)
        worker, = [process for executor in win._exportPool._executors.values()
                   for process in executor._processes.values()]

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            closed = win.close()
        worker.join(30)
        self._run_events(timeout=1)

        self.assertTrue(closed)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.popups, [])


def _worker_data_access():
    """The data access of the worker process that exports: a UDA data source whose client fails to read."""
    source = _uda_source()
    source.UCR = SimpleNamespace()
    return SimpleNamespace(ds_list={UDA: source}, get_connected_data_source_names=lambda: [UDA])


@unittest.skipUnless(hasattr(getattr(iplot_data_access, 'AccessPool', None), 'call_later'),
                     "the installed iplotlib cannot make calls in its worker processes in the background")
@unittest.skipUnless(importlib.util.find_spec('uda_client_reader') is not None,
                     "the export script of iplotDataAccess needs the UDA client")
class ExportInAWorkerProcessTest(unittest.TestCase):
    """The export as MINT runs it, in a worker process of its own, with the export script of iplotDataAccess."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()

    def test_the_export_runs_in_a_worker_process_and_reports_its_progress_there(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        # The worker keeps the file it began to write open until it stops.
        pool = iplot_data_access.AccessPool(1, data_access_factory=_worker_data_access)
        self.addCleanup(pool.shutdown)
        done, reported = [], []

        pool.call_later(export_data_source, UDA, done.append, progress=reported.append, variables=[(VAR1, 'first')],
                        export_format='parquet', chunks=10, output_path=os.path.join(folder, 'out.parquet'),
                        ts=T0, te=T1)
        deadline = time.monotonic() + 600
        while not done and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)

        outcome, = done
        # The client of the worker cannot read: the script says so.
        self.assertEqual((outcome['attempts'], outcome['exported']), (1, 0))
        self.assertIn(f"Export failed for data source '{UDA}'", outcome['errors'][0])
        self.assertEqual(reported, [VAR1])


if __name__ == '__main__':
    unittest.main()
