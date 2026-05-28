"""Behaviour tests for the calibrated flag in data-access parameter construction.

Calibrated signals on CODAC_UDA must append ``retType=doubleCalibrated`` to
the UDA query. Non-calibrated signals and non-CODAC sources must not.
"""

import types
import unittest
from unittest.mock import MagicMock

from iplotlib.interface.iplotSignalAdapter import AccessHelper


def _signal(calibrated: bool, data_source: str = 'codacuda'):
    """Minimal stub exposing only the attributes ``construct_da_params`` reads."""
    return types.SimpleNamespace(
        data_source=data_source,
        name='MAG-MCTB-F1:VAR1',
        ts_start=None,
        ts_end=None,
        ts_relative=False,
        pulse_nb=None,
        envelope=False,
        extremities=False,
        calibrated=calibrated,
    )


class TestCalibratedParams(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_da = AccessHelper.da

    def tearDown(self) -> None:
        AccessHelper.da = self._prev_da

    def _install_data_access(self, source_type: str) -> None:
        fake_ds = types.SimpleNamespace(source_type=source_type)
        fake_da = MagicMock()
        fake_da.get_data_source.return_value = fake_ds
        AccessHelper.da = fake_da

    def test_calibrated_true_adds_rettype_for_codac(self):
        self._install_data_access('CODAC_UDA')
        params = AccessHelper.construct_da_params(_signal(calibrated=True))
        self.assertEqual(params.get('retType'), 'doubleCalibrated')

    def test_calibrated_false_does_not_add_rettype(self):
        self._install_data_access('CODAC_UDA')
        params = AccessHelper.construct_da_params(_signal(calibrated=False))
        self.assertNotIn('retType', params)

    def test_calibrated_true_on_non_codac_does_not_add_rettype(self):
        self._install_data_access('IMASPY')
        params = AccessHelper.construct_da_params(_signal(
            calibrated=True, data_source='imas_source'))
        self.assertNotIn('retType', params)


if __name__ == '__main__':
    unittest.main()
