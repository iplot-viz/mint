# Description: Sets up an application ready for testing.
# Author: Jaswant Sai Panchumarti

from PySide6.QtWidgets import QApplication
from iplotlib.qt.testing import QAppTestAdapter

_instance = None
_qvtk_canvas = None


class QAppOffscreenTestAdapter(QAppTestAdapter):
    """Helper class to provide QApplication instances"""

    qapplication = True

    def setUp(self):
        """Creates the QApplication instance"""

        # Simple way of making instance a singleton
        super().setUp()
        global _instance, _qvtk_canvas
        if _instance is None:
            _instance = QApplication(['QAppOffscreenTestAdapter', '-platform', 'offscreen'])

        self.app = _instance

    def tearDown(self):
        """Deletes the reference owned by self"""
        del self.app
        super().tearDown()
