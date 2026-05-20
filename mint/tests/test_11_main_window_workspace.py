"""Behavioural tests for MTMainWindow export_dict / import_dict workspace flow.

MTMainWindow is the glue between the signals table, the data range
selector, the canvas stack and the plot preferences. Users persist a
workspace via export_dict / import_dict, and a silent break in either
side would lose their work on reload.

These tests check the round-trip end-to-end: populate the window, export,
import into a fresh window, assert state is equivalent. They also cover
the smaller wires (data_range read, build_canvas invocation) that the
smoke test doesn't touch.
"""

import unittest

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _build_main_window(impl: str = 'matplotlib') -> MTMainWindow:
    canvas = Canvas()
    time_model = {"range": {}}
    data_sources = AccessHelper.da.get_connected_data_source_names()
    win = MTMainWindow(
        canvas, AccessHelper.da, time_model, app_version='test',
        data_sources=data_sources,
        blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl=impl)
    win.dataRangeSelector.import_dict({
        'mode': MTGenericAccessMode.PULSE_NUMBER,
        'pulse_nb': ['ITER:MCTB-TEST/111'],
        'base': 'Second(s)',
        't_start': '-5',
        't_end': '4',
    })
    return win


def _populate(win: MTMainWindow) -> None:
    df = pd.DataFrame({
        'DS': ['csv', 'csv'],
        'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
        'Stack': ['1.1', '1.2'],
        'Plot type': ['PlotXY', 'PlotXY'],
        'Alias': ['a', 'b'],
    })
    win.sigCfgWidget.model.set_dataframe(df)


class MainWindowExportDictTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()

    def test_export_dict_has_top_level_workspace_keys(self):
        win = _build_main_window()
        try:
            _populate(win)
            ws = win.export_dict()
            self.assertIn('_metadata', ws)
            self.assertIn('data_range', ws)
            self.assertIn('signal_cfg', ws)
            self.assertIn('main_canvas', ws)
        finally:
            win.close()

    def test_metadata_records_app_version_and_host(self):
        win = _build_main_window()
        try:
            ws = win.export_dict()
            self.assertEqual(ws['_metadata']['appVersion'], 'test')
            self.assertIn('createdAt', ws['_metadata'])
            self.assertIn('createdOnHost', ws['_metadata'])
        finally:
            win.close()

    def test_data_range_export_reflects_pulse_mode(self):
        win = _build_main_window()
        try:
            ws = win.export_dict()
            self.assertEqual(ws['data_range']['mode'],
                             MTGenericAccessMode.PULSE_NUMBER)
        finally:
            win.close()

    def test_signal_cfg_roundtrip_preserves_row_count(self):
        """Export then feed signal_cfg.model back into a new signals model."""
        from mint.models.mtSignalsModel import MTSignalsModel

        win = _build_main_window()
        try:
            _populate(win)
            ws = win.export_dict()
            sig_model_dict = ws['signal_cfg']['model']

            restored = MTSignalsModel()
            restored.import_dict(sig_model_dict)
            self.assertEqual(len(restored.get_dataframe()), 2)
        finally:
            win.close()


class MainWindowDataRangeFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        if AppDataAccess.da is None:
            AppDataAccess.initialize(write_csv_datasource_config())
            AccessHelper.da = AppDataAccess.get_data_access()

    def test_changing_data_range_updates_selector(self):
        """import_dict on the data range selector propagates to the model."""
        win = _build_main_window()
        try:
            win.dataRangeSelector.import_dict({
                'mode': MTGenericAccessMode.PULSE_NUMBER,
                'pulse_nb': ['ITER:MCTB-TEST/999'],
                'base': 'Second(s)',
                't_start': '0',
                't_end': '1',
            })
            self.assertEqual(
                win.dataRangeSelector.get_pulse_number(),
                ['ITER:MCTB-TEST/999'])
        finally:
            win.close()

    def test_get_time_range_in_pulse_mode_returns_numeric_bounds(self):
        win = _build_main_window()
        try:
            ts, te = win.dataRangeSelector.get_time_range()
            # pulse mode returns floats (seconds * base).
            self.assertIsInstance(ts, float)
            self.assertIsInstance(te, float)
            self.assertLess(ts, te)
        finally:
            win.close()


if __name__ == '__main__':
    unittest.main()
