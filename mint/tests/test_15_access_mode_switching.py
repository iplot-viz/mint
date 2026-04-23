"""Mode-switching behaviour on MTDataRangeSelector.

The selector hosts three stacked pages (absolute time / pulse number /
relative time) driven by radio buttons. test_08 verified the individual
access-mode models; this file verifies the selector itself: clicking a
radio must update the stack index, emit ``modeChanged`` and, when
leaving relative mode, emit ``cancelRefresh`` so the auto-refresh timer
shuts down.

We trigger the behaviour via ``select_page`` (the handler the radio is
wired to) rather than a QTest mouse click — the click path is a thin
wrapper over the same handler, and driving signals through the event
loop is flakier without adding meaningful coverage.
"""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.gui.mtDataRangeSelector import MTDataRangeSelector
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class AccessModeSwitchingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _selector(self) -> MTDataRangeSelector:
        return MTDataRangeSelector({})

    def test_default_mode_is_time_range(self):
        sel = self._selector()
        try:
            # Without an explicit mode in the mappings, the selector lands
            # on page 0 (TIME_RANGE) with the radio button checked.
            self.assertEqual(sel.stack.currentIndex(), 0)
            self.assertEqual(sel.accessModes[0].mode,
                             MTGenericAccessMode.TIME_RANGE)
        finally:
            sel.close()

    def test_select_page_updates_stack_index(self):
        sel = self._selector()
        try:
            sel.select_page(1)
            self.assertEqual(sel.stack.currentIndex(), 1)
            self.assertEqual(sel.accessModes[1].mode,
                             MTGenericAccessMode.PULSE_NUMBER)

            sel.select_page(2)
            self.assertEqual(sel.stack.currentIndex(), 2)
            self.assertEqual(sel.accessModes[2].mode,
                             MTGenericAccessMode.RELATIVE_TIME)
        finally:
            sel.close()

    def test_mode_changed_signal_fires_on_switch(self):
        sel = self._selector()
        try:
            fired = []
            sel.modeChanged.connect(lambda: fired.append(True))
            sel.select_page(1)
            sel.select_page(2)
            # Two page changes → two signal emissions.
            self.assertEqual(len(fired), 2)
        finally:
            sel.close()

    def test_leaving_relative_mode_emits_cancel_refresh(self):
        """When the user switches away from relative mode, the auto-refresh
        timer must be cancelled. cancelRefresh is the signal the main
        window listens to for that."""
        sel = self._selector()
        try:
            sel.select_page(2)  # enter relative
            fired = []
            sel.cancelRefresh.connect(lambda: fired.append(True))
            sel.select_page(0)  # leave relative → time range
            self.assertEqual(len(fired), 1)
        finally:
            sel.close()

    def test_is_x_axis_date_matches_mode(self):
        """Time and relative modes use date axes; pulse mode uses numeric."""
        sel = self._selector()
        try:
            sel.select_page(0)  # TIME_RANGE
            self.assertTrue(sel.is_x_axis_date())
            sel.select_page(1)  # PULSE_NUMBER
            self.assertFalse(sel.is_x_axis_date())
            sel.select_page(2)  # RELATIVE_TIME
            self.assertTrue(sel.is_x_axis_date())
        finally:
            sel.close()


if __name__ == '__main__':
    unittest.main()
