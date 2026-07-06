# Description: Runtime selection of the application look (widget style, color scheme),
#              persisted across sessions with QSettings.
# Author: Simon Pinches

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QStyleFactory

from iplotLogging import setupLogger as setupLog

logger = setupLog.get_logger(__name__)

STYLE_KEY = 'appearance/style'
COLOR_SCHEME_KEY = 'appearance/colorScheme'

COLOR_SCHEMES = {
    'system': Qt.ColorScheme.Unknown,
    'light': Qt.ColorScheme.Light,
    'dark': Qt.ColorScheme.Dark,
}


def color_schemes_supported() -> bool:
    # QStyleHints.setColorScheme() needs Qt >= 6.8; on older Qt the menu entry is omitted
    return hasattr(QApplication.styleHints(), 'setColorScheme')


def apply_style(name: str):
    """Switch the widget style at runtime and persist the choice."""
    if QApplication.setStyle(name) is None:
        logger.warning(f"Unknown widget style: {name}")
        return
    QSettings().setValue(STYLE_KEY, name)


def apply_color_scheme(name: str):
    """Switch the color scheme (system/light/dark) at runtime and persist the choice."""
    if name not in COLOR_SCHEMES or not color_schemes_supported():
        logger.warning(f"Unsupported color scheme: {name}")
        return
    QApplication.styleHints().setColorScheme(COLOR_SCHEMES[name])
    QSettings().setValue(COLOR_SCHEME_KEY, name)


def restore_appearance():
    """Re-apply the persisted appearance. Call once, right after the QApplication is created."""
    settings = QSettings()
    style = settings.value(STYLE_KEY)
    if style and QApplication.setStyle(style) is None:
        logger.warning(f"Persisted widget style is not available: {style}")
    scheme = settings.value(COLOR_SCHEME_KEY)
    if scheme in COLOR_SCHEMES and color_schemes_supported():
        QApplication.styleHints().setColorScheme(COLOR_SCHEMES[scheme])


class MTAppearanceMenu(QMenu):
    """An 'Appearance' menu offering the built-in widget styles and color schemes."""

    def __init__(self, parent=None):
        super().__init__("&Appearance", parent)

        # submenus are created with an explicit parent and kept as attributes: the menus returned
        # by QMenu.addMenu(str) are owned by the Python wrapper and get garbage-collected
        self._style_menu = QMenu("&Style", self)
        self.addMenu(self._style_menu)
        style_group = QActionGroup(self)
        current_style = QApplication.style().objectName().lower()
        for name in QStyleFactory.keys():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name.lower() == current_style)
            action.triggered.connect(lambda checked=False, n=name: apply_style(n))
            style_group.addAction(action)
            self._style_menu.addAction(action)

        if color_schemes_supported():
            self._scheme_menu = QMenu("&Color scheme", self)
            self.addMenu(self._scheme_menu)
            scheme_group = QActionGroup(self)
            current_scheme = QSettings().value(COLOR_SCHEME_KEY, 'system')
            for name in COLOR_SCHEMES:
                action = QAction(name.capitalize(), self)
                action.setCheckable(True)
                action.setChecked(name == current_scheme)
                action.triggered.connect(lambda checked=False, n=name: apply_color_scheme(n))
                scheme_group.addAction(action)
                self._scheme_menu.addAction(action)
