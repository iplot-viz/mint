"""Workspace roundtrip tests.

MINT persists and restores the signals table through
``MTSignalsModel.export_dict`` / ``import_dict``. A silent break here would
lose the user's table on reload, so these tests pin the core invariants of
the roundtrip.
"""

import unittest

import pandas as pd

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.models.mtSignalsModel import MTSignalsModel
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


def _populated_model() -> MTSignalsModel:
    model = MTSignalsModel()
    df = pd.DataFrame({
        'DS': ['codacuda', 'codacuda'],
        'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
        'Stack': ['1.1', '1.2'],
        'Plot type': ['PlotXY', 'PlotXY'],
        'Alias': ['a', 'b'],
    })
    model.set_dataframe(df)
    return model


class TestSignalsModelRoundtrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_roundtrip_preserves_row_count_and_values(self):
        original = _populated_model()
        exported = original.export_dict()

        restored = MTSignalsModel()
        restored.import_dict(exported)

        original_df = original.get_dataframe()
        restored_df = restored.get_dataframe()
        self.assertEqual(len(restored_df), len(original_df))

        # The user-facing columns must survive identically.
        for col in ('DS', 'Variable', 'Stack', 'Plot type', 'Alias'):
            self.assertListEqual(
                list(restored_df[col]), list(original_df[col]),
                f"Column {col} drifted across roundtrip")

    def test_export_dict_shape(self):
        model = _populated_model()
        exported = model.export_dict()
        # Contract: export_dict returns a dict containing at least a
        # blueprint section and a table section.
        self.assertIn('blueprint', exported)
        self.assertIn('table', exported)

    def test_import_accepts_legacy_variables_table_key(self):
        # Older workspaces used the 'variables_table' key instead of 'table'.
        legacy = _populated_model().export_dict()
        legacy['variables_table'] = legacy.pop('table')

        restored = MTSignalsModel()
        restored.import_dict(legacy)
        self.assertEqual(len(restored.get_dataframe()), 2)


if __name__ == '__main__':
    unittest.main()
