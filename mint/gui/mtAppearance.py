# Description: Runtime selection of the application look (widget style, style-sheet theme,
#              UI scale), persisted across sessions with QSettings.
# Author: Simon Pinches

import os
import pkgutil
import typing

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMenu, QStyleFactory

from iplotlib.core.display import (DisplayScale, MODE_AUTO, MODE_OFF,
                                   parse_scale_setting)
from iplotLogging import setupLogger as setupLog

logger = setupLog.get_logger(__name__)

STYLE_KEY = 'appearance/style'
THEME_KEY = 'appearance/theme'
SCALE_KEY = 'appearance/ui_scale'
#: The unscaled application font size, captured once. Everything else is derived
#: from it, so applying 1.5 twice in a session does not compound.
BASE_FONT_PT_KEY = 'appearance/base_font_pt'

#: Offered in the menu. 'Auto' asks iplotlib to work it out from the screen.
SCALE_CHOICES = (
    ('Auto', MODE_AUTO),
    ('100% (off)', MODE_OFF),
    ('125%', '1.25'),
    ('150%', '1.5'),
    ('175%', '1.75'),
    ('200%', '2.0'),
)

#: Callables invoked after the scale changes, so open canvases can rebuild.
#: A registry rather than a signal because the Appearance menu is parented to
#: the menu bar and has no handle on the main window.
_scale_listeners = []  # type: typing.List[typing.Callable[[float], None]]


def scale_pinned_by_env() -> bool:
    """True when IPLOT_UI_SCALE pins the scale, making the menu inoperative."""
    return bool(os.environ.get('IPLOT_UI_SCALE'))


def register_scale_listener(callback: typing.Callable[[float], None]):
    """Register a callable to run whenever the UI scale changes."""
    if callback not in _scale_listeners:
        _scale_listeners.append(callback)


def _base_font_pt() -> float:
    """The application font size before any scaling was applied."""
    settings = QSettings()
    stored = settings.value(BASE_FONT_PT_KEY)
    if stored:
        try:
            return float(stored)
        except (TypeError, ValueError):
            settings.remove(BASE_FONT_PT_KEY)
    size = QApplication.font().pointSizeF()
    if size <= 0:
        # A pixel-sized font gives pointSizeF() == -1; fall back to the Qt
        # default rather than persisting a nonsense base.
        size = 9.0
    settings.setValue(BASE_FONT_PT_KEY, size)
    return size


def apply_ui_scale(value, persist: bool = True):
    """Scale the widget font and the iplotlib canvas primitives together.

    Scaling the *application font* is what makes the widgets follow: a fair
    amount of MINT's layout is already font-derived (the time-field widths in
    mtAbsoluteTime, the reserved button width in mtMainWindow), and the style
    sheets use em units for the rest.
    """
    mode, factor_value = parse_scale_setting(value)
    factor = DisplayScale.instance().configure(mode=mode, value=factor_value)

    font = QApplication.font()
    font.setPointSizeF(_base_font_pt() * factor)
    QApplication.instance().setFont(font)

    if persist:
        QSettings().setValue(SCALE_KEY, value if isinstance(value, str) else str(value))
    logger.info(f"UI scale set to {factor:g} ({DisplayScale.instance().reason})")

    for callback in list(_scale_listeners):
        try:
            callback(factor)
        except Exception as e:
            logger.warning(f"UI scale listener failed: {e}")
    return factor

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
    # A style sheet can carry font settings, so re-assert the scaled font.
    apply_ui_scale(QSettings().value(SCALE_KEY, MODE_AUTO), persist=False)


def restore_appearance():
    """Re-apply the persisted appearance. Call once, right after the QApplication is created."""
    settings = QSettings()
    # Capture the untouched font before a theme style sheet can change it.
    _base_font_pt()
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
    apply_ui_scale(settings.value(SCALE_KEY, MODE_AUTO), persist=False)


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

        self._scale_menu = QMenu("UI &scale", self)
        self.addMenu(self._scale_menu)
        scale_group = QActionGroup(self)
        current_scale = str(QSettings().value(SCALE_KEY, MODE_AUTO))
        if current_scale not in (value for _, value in SCALE_CHOICES):
            current_scale = MODE_AUTO
        for label, value in SCALE_CHOICES:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(value == current_scale)
            action.triggered.connect(lambda checked=False, v=value: apply_ui_scale(v))
            scale_group.addAction(action)
            self._scale_menu.addAction(action)
        if scale_pinned_by_env():
            # An IPLOT_UI_SCALE override wins over the menu; say so rather than
            # offering choices that silently do nothing.
            self._scale_menu.setEnabled(False)
            self._scale_menu.setTitle("UI &scale (set by IPLOT_UI_SCALE)")
