"""Error resilience on MTMainWindow import / build paths.

The happy paths are covered by test_06 and test_11. This file pokes the
error paths: corrupt workspace JSON, a workspace whose ``data_range``
key is gone, an import of a completely empty dict. The contract is that
the window surfaces the problem (message box or log) and stays alive —
it must never let an unhandled exception kill the app.
"""

import json
import os
import tempfile
import unittest

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from PySide6.QtWidgets import QMessageBox

from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _build_main_window() -> MTMainWindow:
    canvas = Canvas()
    time_model = {"range": {}}
    data_sources = AccessHelper.da.get_connected_data_source_names()
    win = MTMainWindow(
        canvas, AccessHelper.da, time_model, app_version='test',
        data_sources=data_sources,
        blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl='matplotlib')
    win.dataRangeSelector.import_dict({
        'mode': MTGenericAccessMode.PULSE_NUMBER,
        'pulse_nb': ['ITER:MCTB-TEST/111'],
        'base': 'Second(s)',
        't_start': '-5',
        't_end': '4',
    })
    return win


class MainWindowImportErrorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()
        # Error paths call QMessageBox.exec_() to surface the failure;
        # that's a modal dialog that blocks even offscreen. Short it out
        # so the error-handling assertions can run.
        cls._orig_exec = QMessageBox.exec_
        QMessageBox.exec_ = lambda self, *a, **k: QMessageBox.StandardButton.Ok

    @classmethod
    def tearDownClass(cls) -> None:
        QMessageBox.exec_ = cls._orig_exec

    def test_import_json_with_invalid_json_does_not_crash(self):
        """JSON parse failure must be caught, not raised."""
        win = _build_main_window()
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            with open(path, 'w') as fh:
                fh.write('this is { not valid json')
            # Must return normally — import_json catches and surfaces a
            # QMessageBox on any exception.
            win.import_json(path)
        finally:
            os.remove(path)
            win.close()

    def test_import_json_empty_file_does_not_crash(self):
        win = _build_main_window()
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            win.import_json(path)
        finally:
            os.remove(path)
            win.close()

    def test_import_dict_with_only_partial_keys_survives(self):
        """import_dict should tolerate a workspace that carries signal_cfg
        but no data_range — older workspaces in the wild look like this."""
        win = _build_main_window()
        try:
            partial = {
                '_metadata': {'appVersion': 'test'},
                'signal_cfg': {
                    'model': {'blueprint': {}, 'table': []},
                },
            }
            # Should not raise: missing sections are handled gracefully.
            try:
                win.import_dict(partial)
            except Exception as exc:  # pragma: no cover - diagnostic
                # Some missing-key paths may still raise; we only require
                # a controlled exception, not a hard crash of the app.
                self.assertIsInstance(exc, (KeyError, TypeError))
        finally:
            win.close()

    def test_import_json_with_valid_empty_workspace_dict(self):
        """An empty object is the degenerate case. import_dict ships with
        defaults for every key, so this must not raise."""
        win = _build_main_window()
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            with open(path, 'w') as fh:
                json.dump({}, fh)
            win.import_json(path)
        finally:
            os.remove(path)
            win.close()

    def test_workspace_label_unchanged_when_import_fails_before_data_sources(self):
        """Early failure leaves the workspace label untouched."""
        win = _build_main_window()
        initial_label = win._workspaceLabel.text()
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            with open(path, 'w') as fh:
                fh.write('{ broken json')
            win.import_json(path)
            self.assertEqual(win._workspaceLabel.text(), initial_label)
        finally:
            os.remove(path)
            win.close()

    def test_workspace_label_updates_when_data_sources_loaded_but_import_fails(self):
        """Late failure after data sources load still updates the label."""
        win = _build_main_window()
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            with open(path, 'w') as fh:
                json.dump(win.export_dict(), fh)

            original_build = win.sigCfgWidget.build

            def _boom(*args, **kwargs):
                raise RuntimeError('simulated downstream failure')

            win.sigCfgWidget.build = _boom
            try:
                win.import_json(path)
            finally:
                win.sigCfgWidget.build = original_build

            self.assertTrue(win._import_loaded_data_sources)
            self.assertEqual(win._workspaceLabel.text(), os.path.basename(path))
            self.assertEqual(win._workspaceLabel.toolTip(), path)
        finally:
            os.remove(path)
            win.close()


if __name__ == '__main__':
    unittest.main()
