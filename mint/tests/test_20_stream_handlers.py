"""Tests for MTMainWindow stream handler wiring: Stream/Stop button text
toggle and mini-map availability."""

import unittest
from unittest import mock

import numpy as np
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.core.signal import SignalXY
from iplotlib.data_access.streamer import CanvasStreamer
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

    def test_on_stream_started_turns_the_minimap_off(self):
        win = _build_main_window()
        try:
            plot = PlotXY()
            signal = SignalXY(label='s')
            signal.set_data([np.linspace(0, 1, 10), np.zeros(10)])
            plot.add_signal(signal)
            win.canvas.add_plot(plot, 0)
            w = win.canvasStack.currentWidget()
            w.set_canvas(win.canvas)
            win.refresh_minimap_availability()
            win.toolBar.minimapAction.setChecked(True)
            self.app.processEvents()
            self.assertTrue(win.canvas.show_minimap)

            # Stand in for build(stream=True): the rebuild needs a populated
            # signals table, and the only part of it that matters here is the
            # streaming flag it raises on the canvas.
            def fake_build(stream=False):
                win.canvas.streaming = stream

            with mock.patch.object(win, 'build', fake_build), \
                    mock.patch.object(CanvasStreamer, 'start'):
                win.on_stream_started()
            self.app.processEvents()

            self.assertFalse(win.toolBar.minimapAction.isEnabled())
            self.assertFalse(win.toolBar.minimapAction.isChecked())
            self.assertFalse(win.canvas.show_minimap)
        finally:
            win.close()


if __name__ == '__main__':
    unittest.main()
