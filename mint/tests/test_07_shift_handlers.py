"""Unit tests for the ShiftHandlerMixin helpers.

ShiftHandlerMixin is the host-side piece of the signal-shift feature: when
the user drags a signal in the canvas (or activates shift from the table),
the mixin rewrites the x/y expressions of the affected row, keeps per-row
shift bookkeeping so undo can restore the originals, and branches on pulse
isolation mode.

The handlers themselves need a full ``MTMainWindow`` to run, but several
helpers are pure methods on the mixin (expression formatting, dataframe
lookups, alias generation, Canvas traversal). These tests pin those
helpers against their specifications so the shift feature cannot regress
silently — it's happened before.
"""

import types
import unittest

import pandas as pd

from mint.gui.shift_handlers import ShiftHandlerMixin


class _Host(ShiftHandlerMixin):
    """Minimal host class to exercise the mixin in isolation."""

    def __init__(self, canvas=None):
        self.canvas = canvas


class FormatOffsetExprTest(unittest.TestCase):
    """_format_offset_expr builds a signed offset string on top of the base."""

    def setUp(self) -> None:
        self.host = _Host()

    def test_zero_offset_returns_base_unchanged(self):
        self.assertEqual(
            self.host._format_offset_expr('${self}.time', 0.0),
            '${self}.time')

    def test_near_zero_offset_returns_base_unchanged(self):
        """Offsets smaller than 1e-10 are treated as zero."""
        self.assertEqual(
            self.host._format_offset_expr('${self}.time', 1e-12),
            '${self}.time')

    def test_positive_offset_uses_plus(self):
        self.assertEqual(
            self.host._format_offset_expr('${self}.time', 2.5),
            '(${self}.time) + 2.5')

    def test_negative_offset_uses_minus_with_absolute_value(self):
        self.assertEqual(
            self.host._format_offset_expr('${self}.data', -1.5),
            '(${self}.data) - 1.5')


class InitShiftStorageTest(unittest.TestCase):
    def test_initial_storage_is_empty(self):
        host = _Host()
        host._init_shift_storage()

        self.assertEqual(host._shift_original_exprs, {})
        self.assertEqual(host._shift_accumulated, {})
        self.assertEqual(host._shift_mother_original_pulse_id, {})
        self.assertFalse(host._shift_undo_in_progress)

    def test_init_can_be_called_twice_to_reset(self):
        """_init_shift_storage is called on rebuild and must wipe state."""
        host = _Host()
        host._init_shift_storage()
        host._shift_accumulated['uid-1'] = (1.0, 2.0)
        host._init_shift_storage()
        self.assertEqual(host._shift_accumulated, {})


class FindRowByUidTest(unittest.TestCase):
    """_find_row_by_uid returns the first matching row index or None."""

    def setUp(self) -> None:
        self.host = _Host()

    def test_uid_found_returns_row_index(self):
        df = pd.DataFrame({'uid': ['a', 'b', 'c'], 'val': [1, 2, 3]})
        self.assertEqual(self.host._find_row_by_uid(df, 'b'), 1)

    def test_uid_missing_returns_none(self):
        df = pd.DataFrame({'uid': ['a', 'b'], 'val': [1, 2]})
        self.assertIsNone(self.host._find_row_by_uid(df, 'zzz'))

    def test_dataframe_without_uid_column_returns_none(self):
        df = pd.DataFrame({'val': [1, 2]})
        self.assertIsNone(self.host._find_row_by_uid(df, 'anything'))

    def test_duplicate_uid_returns_first_occurrence(self):
        df = pd.DataFrame({'uid': ['a', 'b', 'b'], 'val': [1, 2, 3]})
        self.assertEqual(self.host._find_row_by_uid(df, 'b'), 1)


class FindRowByUidOrVariableTest(unittest.TestCase):
    """Fallback path: match by Variable/DS if uid is absent."""

    def setUp(self) -> None:
        self.host = _Host()

    def test_uid_match_takes_priority(self):
        df = pd.DataFrame({
            'uid': ['a', 'b', 'c'],
            'Variable': ['X', 'X', 'X'],
            'DS': ['csv', 'csv', 'csv'],
        })
        signal = types.SimpleNamespace(name='X', data_source='csv', pulse_nb='')
        self.assertEqual(
            self.host._find_row_by_uid_or_variable(df, 'b', signal), 1)

    def test_fallback_on_variable_and_ds(self):
        df = pd.DataFrame({
            'uid': ['a', 'b', 'c'],
            'Variable': ['X', 'Y', 'Z'],
            'DS': ['csv', 'csv', 'csv'],
        })
        signal = types.SimpleNamespace(name='Y', data_source='csv', pulse_nb='')
        self.assertEqual(
            self.host._find_row_by_uid_or_variable(df, 'not-a-uid', signal), 1)

    def test_pulse_id_disambiguates_multiple_matches(self):
        df = pd.DataFrame({
            'uid': ['a', 'b'],
            'Variable': ['X', 'X'],
            'DS': ['csv', 'csv'],
            'PulseId': ['111', '222'],
        })
        signal = types.SimpleNamespace(name='X', data_source='csv', pulse_nb='222')
        self.assertEqual(
            self.host._find_row_by_uid_or_variable(df, 'not-a-uid', signal), 1)

    def test_no_match_returns_none(self):
        df = pd.DataFrame({
            'uid': ['a', 'b'],
            'Variable': ['X', 'Y'],
            'DS': ['csv', 'csv'],
        })
        signal = types.SimpleNamespace(name='Z', data_source='csv', pulse_nb='')
        self.assertIsNone(
            self.host._find_row_by_uid_or_variable(df, 'not-a-uid', signal))


class FindSignalInCanvasTest(unittest.TestCase):
    def test_returns_signal_and_plot_when_uid_matches(self):
        sig = types.SimpleNamespace(uid='target')
        plot = types.SimpleNamespace(signals={1: [sig]})
        canvas = types.SimpleNamespace(plots=[[plot]])
        host = _Host(canvas=canvas)

        found_sig, found_plot = host._find_signal_in_canvas('target')
        self.assertIs(found_sig, sig)
        self.assertIs(found_plot, plot)

    def test_returns_none_when_uid_not_found(self):
        canvas = types.SimpleNamespace(plots=[[]])
        host = _Host(canvas=canvas)
        self.assertEqual(host._find_signal_in_canvas('missing'), (None, None))

    def test_skips_empty_plot_slots(self):
        sig = types.SimpleNamespace(uid='found')
        plot = types.SimpleNamespace(signals={1: [sig]})
        canvas = types.SimpleNamespace(plots=[[None, plot]])
        host = _Host(canvas=canvas)

        found_sig, _ = host._find_signal_in_canvas('found')
        self.assertIs(found_sig, sig)


class BuildOffsetExpressionsFromTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = _Host()
        # Blueprint-agnostic model stub; _build_offset_expressions_from only
        # reads model.blueprint.get('x'/'y').get('default').
        self.model = types.SimpleNamespace(blueprint={
            'x': {'default': '${self}.time'},
            'y': {'default': '${self}.data'},
        })

    def test_offset_on_empty_originals_uses_blueprint_defaults(self):
        new_x, new_y = self.host._build_offset_expressions_from(
            self.model, original_x='', original_y='', total_dx=2.0, total_dy=3.0)
        self.assertEqual(new_x, '(${self}.time) + 2.0')
        self.assertEqual(new_y, '(${self}.data) + 3.0')

    def test_zero_offset_preserves_original_expressions(self):
        new_x, new_y = self.host._build_offset_expressions_from(
            self.model, original_x='foo', original_y='bar',
            total_dx=0.0, total_dy=0.0)
        self.assertEqual(new_x, 'foo')
        self.assertEqual(new_y, 'bar')

    def test_negative_offset_produces_subtraction(self):
        new_x, _ = self.host._build_offset_expressions_from(
            self.model, original_x='${self}.time', original_y='',
            total_dx=-1.5, total_dy=0.0)
        self.assertEqual(new_x, '(${self}.time) - 1.5')


if __name__ == '__main__':
    unittest.main()
