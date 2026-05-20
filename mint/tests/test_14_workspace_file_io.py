"""On-disk round-trip of a MINT workspace.

test_11 covers ``export_dict`` / ``import_dict`` in memory. This file
goes one step further: writes the workspace to a JSON file with
``export_json``, then reads it back with ``import_json`` into a fresh
window and asserts the signals table matches. That's the path that
gets exercised every time a user hits File → Save Workspace / Open
Workspace — a silent regression in the on-disk serialisation would
lose their work on reload.

Bypasses QFileDialog by calling export_json / import_json directly
with a tempfile path.
"""

import json
import os
import tempfile
import unittest

import pandas as pd
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


def _populate_two_signals(win: MTMainWindow) -> None:
    df = pd.DataFrame({
        'DS': ['csv', 'csv'],
        'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
        'Stack': ['1.1', '1.2'],
        'Plot type': ['PlotXY', 'PlotXY'],
        'Alias': ['alpha', 'beta'],
    })
    win.sigCfgWidget.model.set_dataframe(df)


class WorkspaceFileIOTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()
        # import_json surfaces errors via QMessageBox.exec_(), which is a
        # modal dialog — even offscreen it blocks the event loop. Short
        # it out for the duration of the suite so the missing-file path
        # can be exercised without hanging the test process.
        cls._orig_exec = QMessageBox.exec_
        QMessageBox.exec_ = lambda self, *a, **k: QMessageBox.StandardButton.Ok

    @classmethod
    def tearDownClass(cls) -> None:
        QMessageBox.exec_ = cls._orig_exec

    def test_export_json_writes_valid_json_file(self):
        win = _build_main_window()
        try:
            _populate_two_signals(win)

            fd, path = tempfile.mkstemp(suffix='.json')
            os.close(fd)
            try:
                win.export_json(path)

                self.assertTrue(os.path.getsize(path) > 0,
                                "export_json produced an empty file")
                with open(path) as fh:
                    data = json.load(fh)
                # A valid workspace carries the four top-level sections —
                # same contract as export_dict.
                self.assertIn('_metadata', data)
                self.assertIn('data_range', data)
                self.assertIn('signal_cfg', data)
                self.assertIn('main_canvas', data)
            finally:
                os.remove(path)
        finally:
            win.close()

    def test_json_roundtrip_preserves_signals_table(self):
        """Save workspace, load it into a fresh window, assert same rows."""
        exporter = _build_main_window()
        importer = None
        path = None
        try:
            _populate_two_signals(exporter)

            fd, path = tempfile.mkstemp(suffix='.json')
            os.close(fd)
            exporter.export_json(path)

            importer = _build_main_window()
            importer.import_json(path)

            df = importer.sigCfgWidget.model.get_dataframe()
            # Every row the user saved must come back on reload.
            self.assertEqual(len(df), 2)
            self.assertListEqual(sorted(df['Variable'].tolist()),
                                 ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'])
        finally:
            exporter.close()
            if importer is not None:
                importer.close()
            if path is not None and os.path.exists(path):
                os.remove(path)

    def test_import_json_missing_file_does_not_crash(self):
        """File-not-found should surface as a user-visible error box, not
        as an unhandled traceback that aborts the whole app."""
        win = _build_main_window()
        try:
            missing_path = os.path.join(
                tempfile.gettempdir(), 'mint_nonexistent_workspace.json')
            if os.path.exists(missing_path):
                os.remove(missing_path)
            # The public import_json catches all exceptions and surfaces
            # a QMessageBox. We assert it returns without raising.
            win.import_json(missing_path)
        finally:
            win.close()


if __name__ == '__main__':
    unittest.main()
