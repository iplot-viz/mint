"""Unit tests for the data-access mode models.

``MTAbsoluteTime``, ``MTPulseId`` and ``MTRelativeTime`` are the three
time-selection modes exposed by the MTDataRangeSelector. Each one
serialises state via ``to_dict`` / ``from_dict``, which is the path the
workspace export/import relies on — a silent regression here would lose
the user's time selection when a workspace is reloaded.

The constructors need a QApplication because they instantiate widgets,
but the serialisation behaviour is testable headlessly.
"""

import unittest

from PySide6.QtCore import QDateTime

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.models.accessModes.mtAbsoluteTime import MTAbsoluteTime
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.accessModes.mtPulseId import MTPulseId
from mint.models.accessModes.mtRelativeTime import MTRelativeTime
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class AccessModeConstantsTest(unittest.TestCase):
    def test_get_supported_modes_order(self):
        """Stack indices of the selector rely on this order: time, pulse, relative."""
        self.assertEqual(
            MTGenericAccessMode.get_supported_modes(),
            [MTGenericAccessMode.TIME_RANGE,
             MTGenericAccessMode.PULSE_NUMBER,
             MTGenericAccessMode.RELATIVE_TIME])

    def test_mode_constants_are_distinct(self):
        constants = {MTGenericAccessMode.TIME_RANGE,
                     MTGenericAccessMode.PULSE_NUMBER,
                     MTGenericAccessMode.RELATIVE_TIME,
                     MTGenericAccessMode.UNKNOWN}
        self.assertEqual(len(constants), 4)


class AbsoluteTimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_mode_is_time_range(self):
        mode = MTAbsoluteTime({})
        self.assertEqual(mode.mode, MTGenericAccessMode.TIME_RANGE)

    def test_from_dict_applies_ts_start_and_end(self):
        mode = MTAbsoluteTime({})
        mode.from_dict({
            'ts_start': '2024-01-15T12:34:56',
            'ts_end': '2024-01-15T13:34:56',
            'ts_ns_start': '123456789',
            'ts_ns_end': '987654321',
        })
        props = mode.properties()
        self.assertEqual(props['ts_start'], '2024-01-15T12:34:56')
        self.assertEqual(props['ts_end'], '2024-01-15T13:34:56')
        self.assertEqual(props['ts_ns_start'], '123456789')
        self.assertEqual(props['ts_ns_end'], '987654321')

    def test_from_dict_defaults_ns_to_zero(self):
        mode = MTAbsoluteTime({})
        mode.from_dict({
            'ts_start': '2024-01-15T12:34:56',
            'ts_end': '2024-01-15T13:34:56',
        })
        props = mode.properties()
        self.assertEqual(props['ts_ns_start'], '000000000')
        self.assertEqual(props['ts_ns_end'], '000000000')


class AbsoluteTimeClearPulseTest(unittest.TestCase):
    """Clear-pulse keeps user-edited timestamps; only resets when the
    fields still match the pulse that originally populated them."""

    FMT = MTAbsoluteTime.TIME_FORMAT

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _seed_pulse_snapshot(self, mode):
        pre_from = QDateTime.fromString('2024-01-15T10:00:00', self.FMT)
        pre_to = QDateTime.fromString('2024-01-15T11:00:00', self.FMT)
        pulse_from = QDateTime.fromString('2024-01-15T12:00:00', self.FMT)
        pulse_to = QDateTime.fromString('2024-01-15T13:00:00', self.FMT)
        mode.fromTime.setDateTime(pulse_from)
        mode.toTime.setDateTime(pulse_to)
        mode.fromTimeNs.setText('000000000')
        mode.toTimeNs.setText('000000000')
        mode.pulseUsed.setText('ITER:test/1')
        mode._saved_time_before_pulse = {
            'from_time': pre_from,
            'to_time': pre_to,
            'from_ns': '111111111',
            'to_ns': '222222222',
            'pulse_from_time': pulse_from,
            'pulse_to_time': pulse_to,
            'pulse_from_ns': '000000000',
            'pulse_to_ns': '000000000',
        }
        return pre_from, pre_to, pulse_from, pulse_to

    def test_clear_restores_pre_pulse_when_user_did_not_edit(self):
        mode = MTAbsoluteTime({})
        pre_from, pre_to, _, _ = self._seed_pulse_snapshot(mode)
        mode.clear_pulse()
        self.assertEqual(mode.pulseUsed.text(), '')
        self.assertEqual(mode.fromTime.dateTime(), pre_from)
        self.assertEqual(mode.toTime.dateTime(), pre_to)
        self.assertEqual(mode.fromTimeNs.text(), '111111111')
        self.assertEqual(mode.toTimeNs.text(), '222222222')
        self.assertIsNone(mode._saved_time_before_pulse)

    def test_clear_preserves_user_edit_to_from_time(self):
        mode = MTAbsoluteTime({})
        _, _, _, pulse_to = self._seed_pulse_snapshot(mode)
        edited_from = QDateTime.fromString('2024-01-15T12:30:00', self.FMT)
        mode.fromTime.setDateTime(edited_from)
        mode.clear_pulse()
        self.assertEqual(mode.pulseUsed.text(), '')
        self.assertEqual(mode.fromTime.dateTime(), edited_from)
        self.assertEqual(mode.toTime.dateTime(), pulse_to)
        self.assertIsNone(mode._saved_time_before_pulse)

    def test_clear_preserves_user_edit_to_ns_field(self):
        mode = MTAbsoluteTime({})
        self._seed_pulse_snapshot(mode)
        mode.fromTimeNs.setText('500000000')
        mode.clear_pulse()
        self.assertEqual(mode.fromTimeNs.text(), '500000000')
        self.assertIsNone(mode._saved_time_before_pulse)

    def test_clear_without_pulse_snapshot_is_noop_on_times(self):
        mode = MTAbsoluteTime({})
        free_from = QDateTime.fromString('2024-02-01T08:00:00', self.FMT)
        mode.fromTime.setDateTime(free_from)
        mode.pulseUsed.setText('stray-label')
        mode.clear_pulse()
        self.assertEqual(mode.pulseUsed.text(), '')
        self.assertEqual(mode.fromTime.dateTime(), free_from)


class PulseIdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_mode_is_pulse_number(self):
        mode = MTPulseId({})
        self.assertEqual(mode.mode, MTGenericAccessMode.PULSE_NUMBER)

    def test_from_dict_populates_pulse_and_times(self):
        mode = MTPulseId({})
        mode.from_dict({
            'pulse_nb': ['ITER:MCTB-TEST/111', 'ITER:MCTB-TEST/112'],
            'base': 'Second(s)',
            't_start': '-5.0',
            't_end': '10.0',
        })
        props = mode.properties()
        # pulse_nb comes back as a list split on commas after the join.
        self.assertIn('ITER:MCTB-TEST/111', props['pulse_nb'])
        self.assertIn('ITER:MCTB-TEST/112', props['pulse_nb'])
        self.assertEqual(props['t_start'], '-5.0')
        self.assertEqual(props['t_end'], '10.0')

    def test_mapping_with_mode_match_seeds_initial_values(self):
        mode = MTPulseId({
            'mode': MTGenericAccessMode.PULSE_NUMBER,
            'value': ['ITER:A/1', 'Second(s)', '0', '5'],
        })
        props = mode.properties()
        self.assertIn('ITER:A/1', props['pulse_nb'])
        self.assertEqual(props['t_start'], '0')
        self.assertEqual(props['t_end'], '5')


class RelativeTimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_mode_is_relative_time(self):
        mode = MTRelativeTime({})
        self.assertEqual(mode.mode, MTGenericAccessMode.RELATIVE_TIME)

    def test_properties_default_structure(self):
        mode = MTRelativeTime({})
        props = mode.properties()
        self.assertIn('relative', props)
        self.assertIn('base', props)
        self.assertIn('auto_refresh', props)

    def test_from_dict_selects_matching_base_in_combo(self):
        """``base`` in the dict is the seconds multiplier, not the label.
        from_dict maps that back to the right combobox entry."""
        mode = MTRelativeTime({})
        mode.from_dict({'relative': 5, 'base': 60, 'auto_refresh': 2})
        # "60" matches the "Minute(s)" option (index 1).
        self.assertEqual(mode.units.currentIndex(), 1)

    def test_from_dict_unknown_base_falls_back_to_first_option(self):
        mode = MTRelativeTime({})
        mode.from_dict({'relative': 5, 'base': 999, 'auto_refresh': 1})
        self.assertEqual(mode.units.currentIndex(), 0)


if __name__ == '__main__':
    unittest.main()
