"""Unit tests for mtBlueprintParser helpers.

The blueprint describes every column MINT tracks — name, type, default,
whether it's exported to workspace, whether it overrides global state,
whether a signal parameter is constructed from it. The helpers below
turn the blueprint JSON into usable metadata and into constructor
arguments for signals. A regression in these paths silently breaks
column naming, workspace roundtrip or signal construction, so we pin
the invariants.
"""

import unittest

import pandas as pd

from mint.models.utils import mtBlueprintParser as mtBp


class ColumnNameTest(unittest.TestCase):
    def test_returns_label_when_present(self):
        bp = {'PulseNumber': {'label': 'PulseId', 'code_name': 'pulse_nb'}}
        self.assertEqual(mtBp.get_column_name(bp, 'PulseNumber'), 'PulseId')

    def test_falls_back_to_key_when_no_label(self):
        bp = {'Variable': {'code_name': 'name'}}
        self.assertEqual(mtBp.get_column_name(bp, 'Variable'), 'Variable')

    def test_schema_keys_are_returned_verbatim(self):
        bp = {'$schema': 'https://...'}
        self.assertEqual(mtBp.get_column_name(bp, '$schema'), '$schema')


class ColumnNamesIteratorTest(unittest.TestCase):
    def test_yields_labels_for_every_non_schema_key(self):
        bp = {
            '$schema': 'x',
            'DataSource': {'label': 'DS', 'code_name': 'data_source'},
            'Variable': {'code_name': 'name'},
        }
        self.assertEqual(list(mtBp.get_column_names(bp)), ['DS', 'Variable'])

    def test_skips_no_export_keys(self):
        bp = {
            'Variable': {'code_name': 'name'},
            'Internal': {'code_name': 'internal', 'no_export': True},
        }
        self.assertEqual(list(mtBp.get_column_names(bp)), ['Variable'])


class OverrideKeysTest(unittest.TestCase):
    def test_returns_keys_marked_override(self):
        bp = {
            'PulseNumber': {'code_name': 'pulse_nb', 'override': True},
            'Variable': {'code_name': 'name'},
            'StartTime': {'code_name': 'ts_start', 'override': True},
        }
        self.assertEqual(sorted(mtBp.get_keys_with_override(bp)),
                         ['PulseNumber', 'StartTime'])


class RemoveTypeInfoTest(unittest.TestCase):
    def test_type_key_is_stripped(self):
        bp = {
            'Variable': {'code_name': 'name', 'type': str, 'type_name': 'str'},
        }
        cleaned = mtBp.remove_type_info(bp)
        self.assertNotIn('type', cleaned['Variable'])
        self.assertIn('type_name', cleaned['Variable'])

    def test_original_blueprint_is_not_mutated(self):
        bp = {'Variable': {'code_name': 'name', 'type': str}}
        mtBp.remove_type_info(bp)
        self.assertIn('type', bp['Variable'])


class ParseRawBlueprintTest(unittest.TestCase):
    def test_type_callable_is_attached(self):
        bp = {'Variable': {'code_name': 'name', 'type_name': 'str'}}
        parsed = mtBp.parse_raw_blueprint(bp)
        self.assertTrue(callable(parsed['Variable']['type']))
        self.assertIs(parsed['Variable']['type'], str)

    def test_default_blueprint_parses_cleanly(self):
        """The shipped DEFAULT_BLUEPRINT must not fail parsing."""
        parsed = mtBp.parse_raw_blueprint(dict(mtBp.DEFAULT_BLUEPRINT))
        # DataSource is a required column; its type must be str after parse.
        self.assertIs(parsed['DataSource']['type'], str)


class AdjustDataframeTest(unittest.TestCase):
    def test_missing_columns_are_added_with_empty_default(self):
        bp = {
            'DataSource': {'label': 'DS', 'code_name': 'data_source'},
            'Variable': {'code_name': 'name'},
        }
        df = pd.DataFrame({'DS': ['csv']})
        mtBp.adjust_dataframe(bp, df)
        self.assertIn('Variable', df.columns)
        self.assertEqual(df.iloc[0]['Variable'], '')

    def test_existing_columns_are_preserved(self):
        bp = {'Variable': {'code_name': 'name'}}
        df = pd.DataFrame({'Variable': ['MAG-MCTB-F1:VAR1']})
        mtBp.adjust_dataframe(bp, df)
        self.assertEqual(df.iloc[0]['Variable'], 'MAG-MCTB-F1:VAR1')


class ConstructParamsFromSeriesTest(unittest.TestCase):
    def test_columns_map_to_code_names(self):
        bp = {
            'Variable': {'code_name': 'name'},
            'DataSource': {'label': 'DS', 'code_name': 'data_source'},
        }
        row = pd.Series({'Variable': 'X', 'DS': 'csv'})
        params = mtBp.construct_params_from_series(bp, row)
        self.assertEqual(params, {'name': 'X', 'data_source': 'csv'})

    def test_missing_columns_are_skipped(self):
        bp = {
            'Variable': {'code_name': 'name'},
            'Missing': {'code_name': 'missing_col'},
        }
        row = pd.Series({'Variable': 'X'})
        params = mtBp.construct_params_from_series(bp, row)
        self.assertEqual(params, {'name': 'X'})


if __name__ == '__main__':
    unittest.main()
