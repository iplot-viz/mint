"""Rebuilding the canvas must not blank the plots before the new draw.

In relative time the canvas is rebuilt on every refresh tick: build() fetches
the data (synchronously, in the GUI thread) and only then set_canvas() draws.
The previous plots have to stay on screen for the whole fetch; otherwise the
user sees an empty canvas for as long as the archive takes to answer. Only the
pyqtgraph widget paints the emptied scene straight away (matplotlib defers the
draw), so that backend is the one checked here.
"""

import unittest

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

PULSE_ID = 'ITER:MCTB-TEST/111'
GRAB_SIZE = (800, 600)


def _ink_pixels(widget) -> int:
    """Number of sampled non-white pixels in the widget's current rendering."""
    image = widget.grab().toImage()
    count = 0
    for y in range(0, image.height(), 4):
        for x in range(0, image.width(), 4):
            color = image.pixelColor(x, y)
            if min(color.red(), color.green(), color.blue()) < 200:
                count += 1
    return count


class RebuildKeepsCanvasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()

    def _build_main_window(self) -> MTMainWindow:
        data_sources = AccessHelper.da.get_connected_data_source_names()
        win = MTMainWindow(
            Canvas(),
            AccessHelper.da,
            {"range": {}},
            app_version='test',
            data_sources=data_sources,
            blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT,
            impl='pyqt',
        )
        win.dataRangeSelector.import_dict({
            'mode': MTGenericAccessMode.PULSE_NUMBER,
            'pulse_nb': [PULSE_ID],
            'base': 'Second(s)',
            't_start': '-5',
            't_end': '4',
        })
        win.sigCfgWidget.model.set_dataframe(pd.DataFrame({
            'DS': ['csv', 'csv'],
            'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
            'Stack': ['1.1', '1.2'],
            'Plot type': ['PlotXY', 'PlotXY'],
        }))
        return win

    def test_build_leaves_previous_plots_on_screen(self):
        win = self._build_main_window()
        try:
            figure = win.qtcanvas._parser.figure
            figure.resize(*GRAB_SIZE)
            win.draw_clicked()
            self.app.processEvents()
            drawn = _ink_pixels(figure)
            self.assertGreater(drawn, 0, "the first draw must render something")

            # Same as a refresh tick: build (fetch) without drawing yet.
            win.build()
            self.app.processEvents()
            self.assertGreater(_ink_pixels(figure), 0,
                               "the previous plots must stay visible while the data is fetched")

            win.qtcanvas.set_canvas(win.canvas)
            self.app.processEvents()
            self.assertGreater(_ink_pixels(figure), 0)
        finally:
            win.close()


if __name__ == '__main__':
    unittest.main()
