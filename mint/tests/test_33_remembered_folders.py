"""The dialogs that open and save workspaces and signal sets open where the last one of its kind was picked, in the next
sessions too (mint#255)."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QFileDialog
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.tests.fixtures import SettingsInTempDir, write_csv_datasource_config
from mint.tests.test_28_read_ahead import VAR1, _MainWindowTestCase

ROWS = {'DS': ['csv'], 'Variable': [VAR1], 'Stack': ['1'], 'Plot type': ['PlotXY']}


class RememberedFoldersTest(SettingsInTempDir, _MainWindowTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def _folder(self) -> str:
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        return folder

    @staticmethod
    def _opened_in(open_dialog) -> str:
        """The folder the open dialog of `open_dialog` shows first."""
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')) as dialog:
            open_dialog()
        return dialog.call_args.kwargs['dir']

    def test_a_new_session_opens_the_workspaces_where_the_last_one_was_saved_or_opened(self):
        saved, opened = self._folder(), self._folder()
        win = self._main_window(ROWS)
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(os.path.join(saved, 'w'), '*.json')):
            win.on_export()

        after_save = self._opened_in(self._main_window(ROWS).on_import)
        shutil.copy(os.path.join(saved, 'w.json'), opened)
        win = self._main_window(ROWS)
        # Whether the import works is left to the tests of the import: its message box would wait for a click.
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(os.path.join(opened, 'w.json'), '')), \
                patch.object(win, '_tell_import_failed'):
            win.on_import()

        self.assertEqual((after_save, self._opened_in(self._main_window(ROWS).on_import)), (saved, opened))

    def test_a_new_session_opens_the_signal_sets_where_the_last_one_was_saved_opened_or_appended(self):
        saved, appended = self._folder(), self._folder()
        table = self._main_window(ROWS).sigCfgWidget
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(os.path.join(saved, 's'), '*.scsv')):
            table.on_export()

        after_save = self._opened_in(self._main_window(ROWS).sigCfgWidget.on_import)
        shutil.copy(os.path.join(saved, 's.scsv'), appended)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(os.path.join(appended, 's.scsv'), '')):
            self._main_window(ROWS).sigCfgWidget.on_append()

        self.assertEqual((after_save, self._opened_in(self._main_window(ROWS).sigCfgWidget.on_append)),
                         (saved, appended))

    def test_a_folder_gone_since_gives_the_one_of_mint_back(self):
        first = self._opened_in(self._main_window(ROWS).on_import)
        gone = self._folder()
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(os.path.join(gone, 'w.json'), '*.json')):
            self._main_window(ROWS).on_export()
        shutil.rmtree(gone)

        self.assertEqual(self._opened_in(self._main_window(ROWS).on_import), first)


if __name__ == '__main__':
    unittest.main()
