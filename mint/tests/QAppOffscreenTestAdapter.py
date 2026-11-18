# Description: Sets up an application ready for testing.
# Author: Jaswant Sai Panchumarti

from iplotlib.qt.testing import QAppTestAdapter
from mint.tests.qAppSingleton import ensure_qapp

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
            # The application of the whole suite: with the font that sizes its widgets whichever test makes it.
            _instance = ensure_qapp()

        self.app = _instance

    def tearDown(self):
        """Deletes the reference owned by self"""
        del self.app
        super().tearDown()
