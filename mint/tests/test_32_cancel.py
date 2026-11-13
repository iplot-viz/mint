"""The Cancel of a Draw, an import and an export (mint#234): the Draw and Export buttons say Cancel while what they
started reads its data in the background, and clicking them stops it."""

import os
import shutil
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from iplotlib.qt.gui.iplotQtCanvas import IplotQtCanvas

from mint.gui.mtMainWindow import CANCELLED
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp
from mint.tests.test_28_read_ahead import VAR1, VAR2, _drawn_data, _drawn_when_done, _MainWindowTestCase, \
    _PendingStub, _PoolStub, _status
from mint.tools.data_export import ExportStop, export_data_source


class _StoppablePendingStub(_PendingStub):
    """A read in the background whose cancel can stop the reads in progress, as AccessPool's."""

    def cancel(self, stop_reading=False):
        super().cancel()
        self.stopped_reading = stop_reading


class _StoppablePoolStub(_PoolStub):
    def fetch_later(self, requests, on_done, on_stopped=None, progress=None):
        requests = list(requests)
        self.requests.append(requests)
        pending = _StoppablePendingStub(self, requests, on_done, on_stopped, progress)
        self.pending.append(pending)
        self.all = getattr(self, 'all', []) + [pending]
        return pending


#: iplotlib releases that predate it leave the places of the plots not drawn empty.
_says_cancelled = unittest.skipUnless(hasattr(IplotQtCanvas, 'cancel_pending_places'),
                                      "the installed iplotlib does not say Cancelled where the plots were to be")


def _place_texts(win) -> dict:
    """What each place of the canvas that has no plot drawn says."""
    parser = win.canvasStack.currentWidget()._parser
    return {place: text.get_text() for place, text in parser._pending_texts.items()}


class CancelDrawTest(_MainWindowTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def _two_plots(self):
        return self._main_window({'DS': ['csv', 'csv'], 'Variable': [VAR1, VAR2],
                                  'Stack': ['1.1', '1.2'], 'Plot type': ['PlotXY', 'PlotXY']})

    def test_draw_says_cancel_while_the_data_are_read_and_draw_once_they_are_drawn(self):
        AccessHelper.pool = pool = _StoppablePoolStub(held=True)
        win = self._two_plots()

        win.draw_clicked()
        reading = win.drawBtn.text()
        pool.arrive(len(pool.pending))
        _drawn_when_done(win)

        self.assertEqual((reading, win.drawBtn.text()), ("Cancel", "Draw"))

    @_says_cancelled
    def test_cancel_keeps_the_plots_drawn_and_says_cancelled_where_the_others_were_to_be(self):
        AccessHelper.pool = pool = _StoppablePoolStub(held=True)
        win = self._two_plots()
        win.draw_clicked()
        pool.arrive()

        win.drawBtn.click()
        self.app.processEvents()
        pool.arrive(len(pool.pending))
        self.app.processEvents()

        self.assertEqual(list(_drawn_data(win)), [VAR1])
        self.assertEqual(_place_texts(win), {(1, 0): CANCELLED})
        self.assertEqual(win.canvasStack.currentWidget()._parser.pending_places, {})
        status = _status(win)
        self.assertTrue(status[0].startswith('Success'))
        self.assertEqual(status[1], CANCELLED)
        self.assertEqual(win.statusBar().currentMessage(), f"{CANCELLED}.")
        self.assertEqual(win.drawBtn.text(), "Draw")
        self.assertIsNone(win._drawing)
        self.assertTrue(pool.all[1].cancelled)
        self.assertTrue(pool.all[1].stopped_reading)

    @_says_cancelled
    def test_a_cancel_while_a_plot_is_drawn_draws_no_other(self):
        AccessHelper.pool = pool = _StoppablePoolStub(held=True)
        win = self._two_plots()
        win.draw_clicked()
        place_plot = win._place_plot

        def place_and_cancel(*args):
            place_plot(*args)
            win.drawBtn.click()

        win._place_plot = place_and_cancel
        # The data of the second plot arrive first: both are there once those of the first arrive.
        pool.pending[1].arrive()
        pool.pending[0].arrive()
        self.app.processEvents()

        self.assertEqual(list(_drawn_data(win)), [VAR1])
        self.assertEqual(_place_texts(win), {(1, 0): CANCELLED})
        self.assertEqual(_status(win)[1], CANCELLED)
        self.assertEqual(win.statusBar().currentMessage(), f"{CANCELLED}.")

    def test_an_iplotlib_that_cannot_stop_reads_still_cancels(self):
        AccessHelper.pool = pool = _PoolStub(held=True)
        win = self._two_plots()
        win.draw_clicked()

        win.drawBtn.click()
        self.app.processEvents()

        self.assertTrue(all(pending.cancelled for pending in pool.pending))
        self.assertEqual(_status(win)[:2], [CANCELLED, CANCELLED])
        self.assertEqual(win.drawBtn.text(), "Draw")

    def test_a_draw_after_a_cancel_draws_every_plot_with_the_properties_it_had(self):
        AccessHelper.pool = None
        win = self._two_plots()
        win.draw_clicked()
        plot = win.canvas.plots[1][0]
        plot.plot_title = 'Title of 1.2'

        AccessHelper.pool = pool = _StoppablePoolStub(held=True)
        win.draw_clicked()
        pool.arrive()
        win.drawBtn.click()
        self.app.processEvents()
        AccessHelper.pool = _PoolStub()
        win.drawBtn.click()
        _drawn_when_done(win)

        self.assertEqual(list(_drawn_data(win)), [VAR1, VAR2])
        self.assertEqual(win.canvas.plots[1][0].plot_title, 'Title of 1.2')
        self.assertEqual(_place_texts(win), {})
        self.assertTrue(all(status.startswith('Success') for status in _status(win)[:2]))

    @_says_cancelled
    def test_cancel_of_an_import_keeps_the_plots_drawn(self):
        AccessHelper.pool = None
        source = self._two_plots()
        source.draw_clicked()
        path = self._workspace_file(source.export_dict())

        AccessHelper.pool = pool = _StoppablePoolStub(held=True)
        win = self._main_window({'DS': [], 'Variable': [], 'Stack': [], 'Plot type': []})
        win.import_json(path)
        pool.arrive()
        reading = win.drawBtn.text()
        win.drawBtn.click()
        self.app.processEvents()

        self.assertEqual(reading, "Cancel")
        self.assertEqual(_place_texts(win), {(1, 0): CANCELLED})
        self.assertEqual(_status(win)[1], CANCELLED)
        self.assertEqual(win.drawBtn.text(), "Draw")


class _Reader:
    def __init__(self):
        self.cancels = 0

    def cancelAPI(self):
        self.cancels += 1


class ExportStopTest(unittest.TestCase):
    """The export function stops once its export is cancelled, and stops the read in progress where it can."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)

    def _script(self, stop: ExportStop, cancel_at: str):
        calls = []

        def generate_data(logfile, conn, csvfile, formatType, startTime, endTime, outputFolder, chunkS=100000,
                          progressCallback=None, relativeTime=False, resampleFreq=None):
            calls.append(startTime)
            try:
                for name in ('A', 'B'):
                    progressCallback(name)
                    if name == cancel_at:
                        stop.stop()
            except Exception as exc:
                return False, repr(exc)
            return True, ""

        script = SimpleNamespace(generateData=generate_data, connectUDA=None)
        return script, calls

    def test_a_cancel_stops_the_export_before_its_next_variable_and_pulse(self):
        stop, reader, told = ExportStop(), _Reader(), []
        script, calls = self._script(stop, cancel_at='A')
        source = SimpleNamespace(UCR=reader, uda_for_export=None, port=3090,
                                 get_pulse_info=lambda pulse: SimpleNamespace(timeFrom=1, timeTo=2))
        data_access = SimpleNamespace(ds_list={'uda': source})

        with patch.dict('sys.modules', {'iplotDataAccess.dataHandling.exportData.exportData': script}):
            outcome = export_data_source(data_access, 'uda', [('A', ''), ('B', '')], 'parquet', 1000,
                                         os.path.join(self.folder, 'out.parquet'), pulses=['p1', 'p2'],
                                         progress=told.append, stop=stop)

        self.assertEqual(told, ['A'])
        self.assertEqual(calls, ['1'])
        self.assertEqual(reader.cancels, 1)
        self.assertEqual(outcome['exported'], 0)

    def test_a_stop_after_the_export_stops_the_reader_it_reads_with_from_then_on(self):
        stop, reader = ExportStop(), _Reader()
        stop.stop()
        stop.reads_with(reader)
        self.assertEqual(reader.cancels, 1)
        self.assertTrue(stop.stopped)

    def test_a_reader_that_cannot_cancel_is_left_alone(self):
        stop = ExportStop()
        stop.reads_with(object())
        stop.stop()
        self.assertTrue(stop.stopped)


if __name__ == '__main__':
    unittest.main()
