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
