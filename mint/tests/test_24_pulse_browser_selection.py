"""The pulse browser's Selected column follows what the canvas uses.

MTMainWindow is the single source of truth: the pulses of the current
access mode plus the PulseId column of the signals table. The browser is
a singleton shared by the pulse field, the time range and the table
context menu, so instead of each opener pushing its own view it asks the
window through a provider. These tests check the provider's answer and
that the window asks for a refresh whenever that answer may have changed.
The browser API is stubbed on the singleton so the tests do not depend on
the iplotwidgets version installed.
"""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from iplotWidgets.pulseBrowser.pulseBrowser import PulseBrowser
from PySide6.QtCore import Qt

from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


class PulseBrowserSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self) -> None:
        self.browser = PulseBrowser()
        self.providers = []
        self.refreshes = []
        self.browser.set_selected_pulses_provider = self.providers.append
        self.browser.refresh_selected_pulses = lambda: self.refreshes.append(True)
        for name in ('set_selected_pulses_provider', 'refresh_selected_pulses'):
            self.addCleanup(delattr, self.browser, name)
        self.win = self._build_main_window()
        self.addCleanup(self.win.close)

    @staticmethod
    def _build_main_window() -> MTMainWindow:
        data_sources = AccessHelper.da.get_connected_data_source_names()
        win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version='test',
                           data_sources=data_sources, blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT,
                           impl='matplotlib')
        win.dataRangeSelector.import_dict({
            'mode': MTGenericAccessMode.PULSE_NUMBER,
            'pulse_nb': ['ITER:A/1', 'ITER:B/2'],
            'base': 'Second(s)',
            't_start': '-5',
            't_end': '4',
        })
        return win

    def _set_table_cell(self, row, column, text):
        model = self.win.sigCfgWidget.model
        model.setData(model.index(row, column), text, Qt.ItemDataRole.EditRole)

    def test_provider_reports_the_selector_and_table_pulses(self):
        self.assertEqual(len(self.providers), 1)
        provider = self.providers[0]
        self.assertEqual(provider(), ['ITER:A/1', 'ITER:B/2'])
        self._set_table_cell(0, self.win.sigCfgWidget.model.pulse_column(), 'ITER:B/2, ITER:C/3')
        self.assertEqual(provider(), ['ITER:A/1', 'ITER:B/2', 'ITER:C/3'])

    def test_time_range_mode_reports_only_the_pulse_the_range_came_from(self):
        provider = self.providers[0]
        self.win.dataRangeSelector.select_page(0)
        self.assertEqual(provider(), [])
        self.win.dataRangeSelector.accessModes[0].pulseUsed.setText('ITER:D/4 (not found)')
        self.assertEqual(provider(), ['ITER:D/4'])

    def test_window_asks_for_a_refresh_when_the_answer_may_change(self):
        pulse_column = self.win.sigCfgWidget.model.pulse_column()
        del self.refreshes[:]
        self.win.dataRangeSelector.select_page(0)
        self.assertEqual(len(self.refreshes), 1)
        self.win.dataRangeSelector.accessModes[1].pulseNumber.setText('ITER:E/5')
        self.assertEqual(len(self.refreshes), 2)
        self._set_table_cell(0, pulse_column, 'ITER:F/6')
        self.assertEqual(len(self.refreshes), 3)
        self._set_table_cell(0, pulse_column + 1, '0')
        self.assertEqual(len(self.refreshes), 3, "other columns do not touch the selection")

    def test_draw_asks_for_a_refresh(self):
        del self.refreshes[:]
        self.win.draw_clicked(no_build=True)
        self.assertEqual(len(self.refreshes), 1)


if __name__ == '__main__':
    unittest.main()
