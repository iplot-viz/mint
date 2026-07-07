# Description: Runtime selection of the application look (widget style, style-sheet theme),
#              persisted across sessions with QSettings.
# Author: Simon Pinches

import pkgutil
import typing

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMenu, QStyleFactory

from iplotLogging import setupLogger as setupLog

logger = setupLog.get_logger(__name__)

STYLE_KEY = 'appearance/style'
THEME_KEY = 'appearance/theme'

# style-sheet themes shipped in mint/gui/themes/<name>.qss
THEME_NONE = 'None'
THEMES = ('Dark', 'Light')


def apply_style(name: str):
    """Switch the widget style at runtime and persist the choice."""
    if QApplication.setStyle(name) is None:
        logger.warning(f"Unknown widget style: {name}")
        return
    QSettings().setValue(STYLE_KEY, name)


def _load_theme(name: str) -> typing.Optional[str]:
    try:
        data = pkgutil.get_data('mint.gui', f'themes/{name.lower()}.qss')
    except (FileNotFoundError, OSError):
        data = None
    return data.decode('utf-8') if data is not None else None


def apply_theme(name: str):
    """Switch the application style-sheet theme at runtime and persist the choice."""
    if name == THEME_NONE:
        QApplication.instance().setStyleSheet('')
        QSettings().setValue(THEME_KEY, name)
        return
    qss = _load_theme(name)
    if qss is None:
        logger.warning(f"Unknown style-sheet theme: {name}")
        return
    QApplication.instance().setStyleSheet(qss)
    QSettings().setValue(THEME_KEY, name)


def restore_appearance():
    """Re-apply the persisted appearance. Call once, right after the QApplication is created."""
    settings = QSettings()
    style = settings.value(STYLE_KEY)
    if style and QApplication.setStyle(style) is None:
        # self-heal legacy/renamed style names so settings and menu state stay consistent
        logger.warning(f"Persisted widget style is not available, resetting it: {style}")
        settings.remove(STYLE_KEY)
    theme = settings.value(THEME_KEY)
    if theme and theme != THEME_NONE:
        qss = _load_theme(theme)
        if qss is None:
            # self-heal legacy/renamed theme names so settings and menu state stay consistent
            logger.warning(f"Persisted style-sheet theme is not available, resetting it: {theme}")
            settings.setValue(THEME_KEY, THEME_NONE)
        else:
            QApplication.instance().setStyleSheet(qss)


class MTAppearanceMenu(QMenu):
    """An 'Appearance' menu offering the built-in widget styles and style-sheet themes."""

    def __init__(self, parent=None):
        super().__init__("&Appearance", parent)

        # submenus are created with an explicit parent and kept as attributes: the menus returned
        # by QMenu.addMenu(str) are owned by the Python wrapper and get garbage-collected
        self._style_menu = QMenu("&Style", self)
        self.addMenu(self._style_menu)
        style_group = QActionGroup(self)
        # when a style-sheet theme is active QApplication.style() is an anonymous
        # QStyleSheetStyle wrapper, so prefer the persisted choice over its objectName;
        # a legacy/unknown persisted name falls back to the live style
        current_style = QSettings().value(STYLE_KEY, '') or QApplication.style().objectName()
        if current_style.lower() not in (k.lower() for k in QStyleFactory.keys()):
            current_style = QApplication.style().objectName()
        for name in QStyleFactory.keys():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name.lower() == current_style.lower())
            action.triggered.connect(lambda checked=False, n=name: apply_style(n))
            style_group.addAction(action)
            self._style_menu.addAction(action)

        self._theme_menu = QMenu("&Theme", self)
        self.addMenu(self._theme_menu)
        theme_group = QActionGroup(self)
        current_theme = QSettings().value(THEME_KEY, THEME_NONE)
        if current_theme not in (THEME_NONE,) + THEMES:
            # legacy/unknown persisted value: nothing would be applied, so show 'None' as checked
            current_theme = THEME_NONE
        for name in (THEME_NONE,) + THEMES:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name == current_theme)
            action.triggered.connect(lambda checked=False, n=name: apply_theme(n))
            theme_group.addAction(action)
            self._theme_menu.addAction(action)
