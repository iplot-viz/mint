"""Smoke test: MINT main window boots offscreen with a CSV data source.

Does not draw anything; just verifies that the full MINT stack (main window,
signal configurator, data range selector, toolbar, preferences wiring, status
bar) initialises without raising. Catches broken imports, wiring regressions
and initialisation-time errors long before a user sees them.
"""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.utils import mtBlueprintParser
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


class MainWindowSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()

    def _build_main_window(self, impl: str) -> MTMainWindow:
        canvas = Canvas()
        time_model = {
            "range": {
                "mode": MTGenericAccessMode.TIME_RANGE,
                "value": ["", ""],
            }
        }
        data_sources = AccessHelper.da.get_connected_data_source_names()
        return MTMainWindow(
            canvas,
            AccessHelper.da,
            time_model,
            app_version='test',
            data_sources=data_sources,
            blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT,
            impl=impl,
        )

    def test_main_window_builds_with_matplotlib(self):
        win = self._build_main_window('matplotlib')
        self.assertIsNotNone(win.sigCfgWidget)
        self.assertIsNotNone(win.dataRangeSelector)
        self.assertIsNotNone(win.canvasStack)
        win.close()

    def test_main_window_builds_with_pyqtgraph(self):
        win = self._build_main_window('pyqt')
        self.assertIsNotNone(win.sigCfgWidget)
        self.assertIsNotNone(win.dataRangeSelector)
        self.assertIsNotNone(win.canvasStack)
        win.close()


if __name__ == '__main__':
    unittest.main()
