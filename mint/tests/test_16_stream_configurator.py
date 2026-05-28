"""State tests for MTStreamConfigurator.

The streamer dialog owns two pieces of state: an ``_active`` flag and a
time-window spinbox value. The main window watches the ``streamStarted``
/ ``streamStopped`` signals to decide whether a draw button press should
re-render or kick off a streaming session. Breaking those signals or the
flag means the streaming feature silently stops working.

We don't exercise the underlying CanvasStreamer's live data fetch here —
that path needs a real UDA server and a timer loop, both of which make a
CI test flaky. The configurator's state machine is the high-value piece
and it's fully unit-testable.
"""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.gui.mtStreamConfigurator import MTStreamConfigurator
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access():
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())
    return AppDataAccess.get_data_access()


class StreamConfiguratorStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.da = _ensure_data_access()

    def _configurator(self) -> MTStreamConfigurator:
        # The real main window passes no kwargs here either; kwargs get
        # forwarded to QDialog.__init__ which rejects 'da' as not-a-property.
        # The streamer attribute still gets created (with da=None), which is
        # enough for the state machine we're testing.
        return MTStreamConfigurator()

    def test_starts_inactive(self):
        cfg = self._configurator()
        try:
            self.assertFalse(cfg.is_activated())
        finally:
            cfg.close()

    def test_start_sets_active_flag_and_emits_signal(self):
        cfg = self._configurator()
        try:
            fired = []
            cfg.streamStarted.connect(lambda: fired.append(True))
            cfg.start()
            self.assertTrue(cfg.is_activated())
            self.assertEqual(len(fired), 1)
        finally:
            cfg.close()

    def test_stop_clears_active_flag_and_emits_signal(self):
        cfg = self._configurator()
        try:
            cfg.start()
            fired = []
            cfg.streamStopped.connect(lambda: fired.append(True))
            cfg.stop()
            self.assertFalse(cfg.is_activated())
            self.assertEqual(len(fired), 1)
        finally:
            cfg.close()

    def test_time_window_reads_spinbox_value(self):
        cfg = self._configurator()
        try:
            cfg.ui.windowSpinBox.setValue(120)
            self.assertEqual(cfg.time_window(), 120)
        finally:
            cfg.close()


if __name__ == '__main__':
    unittest.main()
