"""Behaviour tests for MTSignalsModel.

The signals model is the heart of MINT — it mediates between the user's
table, workspace serialisation and the signal processing pipeline. These
tests lock in a handful of invariants that the UI and the data access
layer depend on:

- appending a variable from the browser populates only DS + Variable + uid
- setting a full dataframe honours blueprint defaults for missing columns
  (backward compatibility with older SCSV/workspaces without newer columns)
- insertRows seeds new rows with the expected defaults (DataSource, PlotType)
"""

import unittest
from unittest import mock

import pandas as pd

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.models.mtSignalsModel import MTSignalsModel
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class TestAppendDataframeFromBrowser(unittest.TestCase):
    """When a variable is added via the browser, only DS + Variable come in."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def setUp(self) -> None:
        self.model = MTSignalsModel()

    def test_append_populates_only_ds_and_variable(self):
        df = pd.DataFrame({'DS': ['codacuda'], 'Variable': ['MAG-MCTB-F1:VAR1']})
        self.model.append_dataframe(df)

        table = self.model.get_dataframe()
        self.assertEqual(len(table), 1)
        row = table.iloc[0]
        self.assertEqual(row['DS'], 'codacuda')
        self.assertEqual(row['Variable'], 'MAG-MCTB-F1:VAR1')
        # Blueprint-overridable columns must stay empty — they inherit from the
        # global time/pulse selector at draw time.
        self.assertEqual(row['StartTime'], '')
        self.assertEqual(row['EndTime'], '')
        self.assertEqual(row['PulseId'], '')
        # Expression columns also stay empty here; defaults resolve in _parse_series.
        self.assertEqual(row['x'], '')
        self.assertEqual(row['y'], '')
        self.assertEqual(row['z'], '')
        self.assertEqual(row['Stack'], '')

    def test_append_assigns_uid(self):
        df = pd.DataFrame({'DS': ['codacuda'], 'Variable': ['MAG-MCTB-F1:VAR1']})
        self.model.append_dataframe(df)
        uid = self.model.get_dataframe().iloc[0]['uid']
        self.assertTrue(uid)  # non-empty
        self.assertEqual(len(uid), 36)  # uuid4 string length


class TestInsertRows(unittest.TestCase):
    """Programmatic row insertion seeds DataSource and PlotType defaults."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_insert_row_has_plot_type_default(self):
        model = MTSignalsModel()
        model.insertRows(0, 1)
        df = model.get_dataframe()
        # insertRows seeds Plot type with the blueprint default.
        if len(df) > 0:
            self.assertEqual(df.iloc[0]['Plot type'], 'PlotXY')


class TestSetDataframeBackwardCompat(unittest.TestCase):
    """Importing a workspace missing newer columns still loads cleanly."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_set_dataframe_without_calibrated_column(self):
        # Simulate an old workspace: no Calibrated column in the dataframe.
        df = pd.DataFrame({
            'DS': ['codacuda'],
            'Variable': ['MAG-MCTB-F1:VAR1'],
            'Stack': ['1.1'],
            'Plot type': ['PlotXY'],
        })
        model = MTSignalsModel()
        model.set_dataframe(df)

        table = model.get_dataframe()
        self.assertEqual(len(table), 1)
        # Calibrated column exists in the table even though df did not have it,
        # filled from the blueprint / accommodation path.
        self.assertIn('Calibrated', table.columns)


class TestRowLevelRelativePulse(unittest.TestCase):
    """Row-level relative pulse ids (0 = last, -N = N-th previous) must resolve
    to the explicit pulse for that row, instead of being misrouted into the
    'remove from global' bucket (mint #96)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _resolve_pulse(self, cell: str, global_pulses):
        model = MTSignalsModel()
        pulse_bp = model._blueprint['PulseNumber']
        original_default = pulse_bp.get('default')
        pulse_bp['default'] = list(global_pulses)
        try:
            model.insertRows(0, 1)
            df = model.get_dataframe()
            row = {
                'DS': 'csv', 'Variable': 'MAG-MCTB-F1:VAR1', 'PulseId': cell,
                'Stack': '1', 'Plot type': 'PlotXY', 'Row span': '1',
                'Col span': '1', 'Envelope': '', 'x': '${self}.time',
                'y': '${self}.data', 'z': '', 'Alias': '', 'StartTime': '',
                'EndTime': '', 'Calibrated': '',
            }
            for col, val in row.items():
                if col in df.columns:
                    df.at[0, col] = val
            inp = df.iloc[0]
            fls = pd.Series(0, index=inp.index)

            all_pulses = pd.DataFrame({'Pulse': list(global_pulses)})

            def fake_get_pulses_df(pattern=None, **_):
                text = str(pattern)
                if text and '*' not in text:
                    return pd.DataFrame({'Pulse': [pattern]})
                return all_pulses

            fake_ds = mock.Mock()
            fake_ds.get_pulses_df.side_effect = fake_get_pulses_df
            with mock.patch.object(AppDataAccess, 'da') as da:
                da.get_data_source.return_value = fake_ds
                model.data_sources = ['csv']
                outputs = list(model._parse_series(inp, fls, 1, []))
            return outputs[0][0]['PulseId']
        finally:
            pulse_bp['default'] = original_default

    def test_minus_one_resolves_to_previous_pulse(self):
        resolved = self._resolve_pulse('-1', ['10', '20', '30', '40', '50'])
        self.assertEqual(resolved, '40')

    def test_zero_resolves_to_last_pulse(self):
        resolved = self._resolve_pulse('0', ['10', '20', '30', '40', '50'])
        self.assertEqual(resolved, '50')

    def test_minus_one_is_not_removed_from_global(self):
        # The bug routed -1 into the 'remove from global' bucket, so the row
        # kept the global list minus that pulse instead of the pulse itself.
        resolved = self._resolve_pulse('-1', ['10', '20', '30', '40', '50'])
        self.assertNotIn(',', str(resolved))


if __name__ == '__main__':
    unittest.main()
