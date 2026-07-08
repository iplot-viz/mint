"""Home button: toolbar wiring and relative-time auto-refresh handling.

The view reset itself lives in iplotlib (covered by its reset-view tests). Here
we verify the mint-specific contract: Home is present on the toolbar and, in
relative time, halts the periodic refresh (which resumes only on the next Draw).
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


class HomeButtonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls.cfg_path = write_csv_datasource_config()
        AppDataAccess.initialize(cls.cfg_path)
        AccessHelper.da = AppDataAccess.get_data_access()

    def _build_main_window(self, impl: str = 'matplotlib') -> MTMainWindow:
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

    def test_home_action_present_and_enabled(self):
        win = self._build_main_window()
        self.assertTrue(hasattr(win.toolBar, 'homeAction'))
        self.assertTrue(win.toolBar.homeAction.isEnabled())
        win.close()

    def test_home_stops_active_auto_refresh(self):
        # Triggering the real toolbar action stops the periodic refresh.
        win = self._build_main_window()
        win.canvas.auto_refresh = 60
        win.start_auto_refresh()
        self.assertTrue(win.refreshTimer.isActive())

        win.toolBar.homeAction.trigger()

        self.assertFalse(win.refreshTimer.isActive())
        win.close()


if __name__ == '__main__':
    unittest.main()
