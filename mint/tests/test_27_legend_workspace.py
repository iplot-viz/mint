"""The legend as the user left it survives Draw and a workspace export/import.

Where the legend was dragged, its size, whether it is folded away and the
signals hidden from it live in the iplotlib canvas; MINT carries them through
Draw (canvas merge) and through the workspace file, which reads the stack names
back as numbers.
"""

import json
import os
import tempfile
import unittest
from dataclasses import fields

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.interface.iplotSignalAdapter import AccessHelper

from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

# mint CI installs iplotlib@develop, which may not keep the legend yet.
LEGEND_KEPT = 'legend_anchor' in {f.name for f in fields(PlotXY)}


def _build_main_window(impl: str) -> MTMainWindow:
    win = MTMainWindow(
        Canvas(), AccessHelper.da, {"range": {}}, app_version='test',
        data_sources=AccessHelper.da.get_connected_data_source_names(),
        blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl=impl)
    win.dataRangeSelector.import_dict({
        'mode': MTGenericAccessMode.PULSE_NUMBER,
        'pulse_nb': ['ITER:MCTB-TEST/111'],
        'base': 'Second(s)',
        't_start': '-5',
        't_end': '4',
    })
    win.sigCfgWidget.model.set_dataframe(pd.DataFrame({
        'DS': ['csv', 'csv'],
        'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
        'Stack': ['1.1', '1.1'],
        'Plot type': ['PlotXY', 'PlotXY'],
        'Alias': ['alpha', 'beta'],
    }))
    return win


@unittest.skipUnless(LEGEND_KEPT, "the installed iplotlib does not keep the legend")
class LegendWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())
        AccessHelper.da = AppDataAccess.get_data_access()

    def _legend(self, win):
        plot = win.canvas.plots[0][0]
        signals = [signal for stack in plot.signals.values() for signal in stack]
        anchor = {str(stack): place for stack, place in (plot.legend_anchor or {}).items()}
        return (anchor, plot.legend_width, plot.legend_collapsed,
                [signal.hidden for signal in signals])

    def test_survives_draw_and_a_workspace_import(self):
        for impl in ('matplotlib', 'pyqt'):
            with self.subTest(impl=impl):
                win = _build_main_window(impl)
                path = os.path.join(tempfile.mkdtemp(), 'legend.json')
                try:
                    win.draw_clicked()
                    plot = win.canvas.plots[0][0]
                    win.canvasStack.currentWidget()._parser.set_signal_hidden(plot.signals[1][1], True)
                    plot.legend_anchor = {'1': [0.2, 0.3]}
                    plot.legend_width = 30
                    plot.legend_collapsed = ['1']
                    expected = ({'1': [0.2, 0.3]}, 30, ['1'], [False, True])

                    win.draw_clicked()
                    self.assertEqual(self._legend(win), expected)

                    with open(path, 'w') as f:
                        json.dump(win.export_dict(), f)
                    win.import_json(path)
                    self.assertEqual(self._legend(win), expected)

                    parser = win.canvasStack.currentWidget()._parser
                    hidden = win.canvas.plots[0][0].signals[1][1]
                    impl_plot = parser._signal_impl_plot_lut[parser.signal_lut_key(hidden)]
                    self.assertEqual(parser.legend_anchor(impl_plot), (0.2, 0.3))
                    self.assertTrue(parser.legend_collapsed(impl_plot))
                    line = hidden.lines[0]
                    self.assertFalse(line.get_visible() if hasattr(line, 'get_visible') else line.isVisible())
                finally:
                    win.close()
                    if os.path.exists(path):
                        os.remove(path)


if __name__ == '__main__':
    unittest.main()
