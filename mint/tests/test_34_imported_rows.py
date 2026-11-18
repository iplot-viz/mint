"""A row whose data can't be read, in a workspace saved without its signal, says so in its Status once imported, as
after a Draw: its Variable red and why, not Ready, and the other rows of its plot with their own data."""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp
from mint.tests.test_28_read_ahead import VAR1, VAR2, _drawn_when_done, _MainWindowTestCase, _PoolStub

#: A variable the data source doesn't have.
MISSING = 'MAG-MCTB-F1:MISSING'


class ImportedRowThatCannotBeReadTest(_MainWindowTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def _saved_without_the_row_that_cannot_be_read(self) -> dict:
        """The workspace of one plot of VAR1, MISSING and VAR2, as MINT saved it while MISSING had no data: without
        a signal for that row."""
        AccessHelper.pool = None
        win = self._main_window({'DS': ['csv'] * 3, 'Variable': [VAR1, MISSING, VAR2], 'Stack': ['1.1'] * 3,
                                 'Plot type': ['PlotXY'] * 3})
        win.draw_clicked()
        workspace = win.export_dict()
        for column in workspace['main_canvas']['plots']:
            for plot in column:
                for signals in (plot or {}).get('signals', {}).values():
                    signals[:] = [signal for signal in signals if signal['name'] != MISSING]
        return workspace

    def _imported(self, pool):
        workspace = self._saved_without_the_row_that_cannot_be_read()
        AccessHelper.pool = pool
        win = self._main_window({'DS': [], 'Variable': [], 'Stack': [], 'Plot type': []})
        win.import_json(self._workspace_file(workspace))
        return _drawn_when_done(win)

    def _assert_each_row_says_what_it_has(self, win):
        model = win.sigCfgWidget.model
        table = model.get_dataframe()
        rows = {table.at[i, 'Variable']: (table.at[i, 'Status'], bool(model._table_fails.at[i, 'Variable']))
                for i in range(len(table)) if table.at[i, 'Variable']}
        self.assertEqual(rows, {VAR1: ('Success|11 points', False), MISSING: ('Data-Access|0 points', True),
                                VAR2: ('Success|11 points', False)})
        plotted = [(signal.name, float(signal.y_data[0]) if signal.y_data is not None and len(signal.y_data) else None)
                   for signals in win.canvas.plots[0][0].signals.values() for signal in signals]
        self.assertEqual(plotted, [(VAR1, 0.0), (MISSING, None), (VAR2, 1.0)])

    def test_its_status_says_why_when_the_import_reads_in_this_thread(self):
        self._assert_each_row_says_what_it_has(self._imported(pool=None))

    def test_its_status_says_why_when_the_import_reads_in_the_background(self):
        self._assert_each_row_says_what_it_has(self._imported(pool=_PoolStub()))


if __name__ == '__main__':
    unittest.main()
