"""Shared QApplication singleton for the MINT test suite.

Qt only allows one QApplication per process. When multiple test modules
run in the same pytest session, each must reuse the existing instance
instead of creating a new one. A generic font (DejaVu Sans, taken from
matplotlib's bundle) is registered so Qt offscreen has real fonts to
render with on any platform.

TODO: once iplotlib issue #34 lands on develop and a new iplotlib
release is cut, migrate to ``from iplotlib.qt.testing import ensure_qapp``
and remove this copy.
"""

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from matplotlib import font_manager


def _register_bundled_font(app: QApplication) -> None:
    try:
        ttf_path = font_manager.findfont("DejaVu Sans", fallback_to_default=True)
        if QFontDatabase.addApplicationFont(ttf_path) != -1:
            app.setFont(QFont("DejaVu Sans", 10))
    except Exception:
        pass


def ensure_qapp() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    app = QApplication(['mint_tests', '-platform', 'offscreen'])
    _register_bundled_font(app)
    return app
