"""Tests for the export dialog's time-mode selection.

The exportStarted payload drives on_export_started in the main window:
'relative_time' must follow the Time combo so time-range exports can be
written as seconds from the window start. The pulse branch ignores the
flag downstream, so only the payload contract is tested here.
"""

import unittest

from mint.gui.mtExportConfigurator import MTExportConfigurator
from mint.tests.qAppSingleton import ensure_qapp


class ExportConfiguratorTimeModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()

    def _payload(self, dialog) -> dict:
        received = []
        dialog.exportStarted.connect(received.append)
        dialog.on_data_exported()
        self.assertEqual(len(received), 1)
        return received[0]

    def test_defaults_to_absolute_time(self):
        dlg = MTExportConfigurator()
        try:
            dlg.ui.pathLineEdit.setText("out.parquet")
            data = self._payload(dlg)
            self.assertFalse(data['relative_time'])
        finally:
            dlg.close()

    def test_relative_selection_sets_flag(self):
        dlg = MTExportConfigurator()
        try:
            dlg.ui.pathLineEdit.setText("out.parquet")
            dlg.ui.timeComboBox.setCurrentIndex(1)
            data = self._payload(dlg)
            self.assertTrue(data['relative_time'])
        finally:
            dlg.close()


if __name__ == "__main__":
    unittest.main()
