"""Tests for MTMainWindow stream handler wiring: Stream/Stop button text
toggle."""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.gui.mtMainWindow import MTMainWindow
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access():
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())
    return AppDataAccess.get_data_access()


def _build_main_window(impl: str = 'matplotlib') -> MTMainWindow:
    canvas = Canvas()
    time_model = {"range": {}}
    data_sources = AccessHelper.da.get_connected_data_source_names()
    return MTMainWindow(
        canvas, AccessHelper.da, time_model, app_version='test',
        data_sources=data_sources,
        blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl=impl)


class StreamHandlersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.da = _ensure_data_access()

    def test_on_stream_stopped_resets_button_text_to_stream(self):
        win = _build_main_window()
        try:
            win.streamBtn.setText("Stop")
            win.on_stream_stopped()
            self.assertEqual(win.streamBtn.text(), "Stream")
        finally:
            win.close()


if __name__ == '__main__':
    unittest.main()
