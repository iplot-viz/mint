"""Workspace round-trip for Ruler annotations placed on a plot.

Rulers are a iplotlib-side concept (Plot.rulers) but the user persists them
through MINT's MTMainWindow workspace flow (export_dict / import_dict).
A break here would silently drop rulers on workspace reload, so pin the
end-to-end contract: export → import → rulers still present, with
preserved coordinates, colors, visibility and label state.
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

# iplotlib.core.ruler lives on the rulers branch of iplotlib and is not yet
# merged to develop. mint CI installs iplotlib@develop, so this module may be
# missing at test-collection time; skip the suite cleanly when that happens.
try:
    from iplotlib.core.ruler import Ruler
    RULER_AVAILABLE = True
except ImportError:
    Ruler = None
    RULER_AVAILABLE = False


def _build_main_window(impl: str = 'matplotlib') -> MTMainWindow:
    canvas = Canvas()
    time_model = {"range": {}}
    data_sources = AccessHelper.da.get_connected_data_source_names()
    win = MTMainWindow(
        canvas, AccessHelper.da, time_model, app_version='test',
        data_sources=data_sources,
        blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl=impl)
    win.dataRangeSelector.import_dict({
        'mode': MTGenericAccessMode.PULSE_NUMBER,
        'pulse_nb': ['ITER:MCTB-TEST/111'],
        'base': 'Second(s)',
        't_start': '-5',
        't_end': '4',
    })
    df = pd.DataFrame({
        'DS': ['csv', 'csv'],
        'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
        'Stack': ['1.1', '1.2'],
        'Plot type': ['PlotXY', 'PlotXY'],
        'Alias': ['a', 'b'],
    })
    win.sigCfgWidget.model.set_dataframe(df)
    return win


@unittest.skipUnless(RULER_AVAILABLE, "iplotlib.core.ruler not present in installed iplotlib")
class RulerWorkspaceRoundtripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()

    def test_rulers_added_to_plot_survive_workspace_export(self):
        win = _build_main_window()
        try:
            win.draw_clicked()
            self.app.processEvents()
            plot = win.canvas.plots[0][0]
            self.assertIsNotNone(plot, "draw_clicked must populate the canvas with at least one plot")
            plot.add_ruler(Ruler(name='A', xy=(1.0, 2.0), color='#FF0000', visible=True))
            plot.add_ruler(Ruler(name='B', xy=(3.0, 4.0), color='#00FF00', visible=False))

            ws = win.export_dict()
            plot_dict = ws['main_canvas']['plots'][0][0]
            self.assertIn('rulers', plot_dict)
            self.assertEqual(len(plot_dict['rulers']), 2)
            self.assertEqual([r['name'] for r in plot_dict['rulers']], ['A', 'B'])
        finally:
            win.close()

    def test_workspace_dict_with_rulers_rehydrates_canvas(self):
        """The export_dict / Canvas.from_dict pair is the persistence boundary:
        verifying that exported rulers reconstruct as Ruler instances on the
        new Canvas guarantees that MINT's import path receives them intact,
        independent of the signals-rebuild side of the workspace flow."""
        win = _build_main_window()
        try:
            win.draw_clicked()
            self.app.processEvents()
            plot = win.canvas.plots[0][0]
            plot.add_ruler(Ruler(name='A', xy=(1.0, 2.0), color='#FF0000', visible=True,
                                 font_color='#000000', show_label=False, show_val_label=False))
            plot.add_ruler(Ruler(name='B', xy=(3.0, 4.0), color='#00FF00', visible=False))
            ws = win.export_dict()
        finally:
            win.close()

        restored = Canvas.from_dict(ws['main_canvas'])
        restored_plot = restored.plots[0][0]
        self.assertIsNotNone(restored_plot)
        self.assertEqual([r.name for r in restored_plot.rulers], ['A', 'B'])
        self.assertEqual(restored_plot.rulers[0].color, '#FF0000')
        self.assertEqual(restored_plot.rulers[0].font_color, '#000000')
        self.assertFalse(restored_plot.rulers[0].show_label)
        self.assertFalse(restored_plot.rulers[0].show_val_label)
        self.assertFalse(restored_plot.rulers[1].visible)


if __name__ == '__main__':
    unittest.main()
