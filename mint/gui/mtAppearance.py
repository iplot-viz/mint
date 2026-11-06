# Description: Runtime selection of the application look (widget style, theme, UI scale),
#              persisted across sessions with QSettings.
# Author: Simon Pinches

import os
import pkgutil
import typing

from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QPalette
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QMenu, QStyleFactory, QWidget

from iplotlib.core.display import (DisplayScale, MODE_AUTO, MODE_FIXED, MODE_OFF,
                                   parse_scale_setting)
from iplotLogging import setupLogger as setupLog

logger = setupLog.get_logger(__name__)

STYLE_KEY = 'appearance/style'
THEME_KEY = 'appearance/theme'
SCALE_KEY = 'appearance/ui_scale'
#: Factor exported as QT_SCALE_FACTOR at the next start. Per user and machine
#: (QSettings), never in a workspace: the screen is what varies, not the plot.
QT_SCALE_KEY = 'appearance/qt_scale_factor'
#: What applies until the user picks otherwise.
DEFAULT_SCALE = MODE_AUTO
#: The application font size before any scaling, captured once per process so
#: applying 1.5 twice does not compound. Not persisted: the platform default
#: differs between machines sharing the same settings file.
_base_font_pt = None  # type: typing.Optional[float]

#: Offered in the menu. 'Auto' sizes the plot text from the screen and leaves
#: the widget font to the platform.
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


def startup_qt_scale_factor(settings=None) -> typing.Optional[str]:
    """The QT_SCALE_FACTOR to export before the QApplication is built.

    Qt reads it once, at QGuiApplication construction, and it is the only
    lever that scales everything alike: fonts, style primitives (radio
    indicators, check boxes, scroll bars), icons and spacing. Scaling the
    application font reaches the fonts only.

    None when there is nothing to set: no stored factor, a factor of 1, or a
    QT_SCALE_FACTOR already in the environment, which wins.
    """
    if os.environ.get('QT_SCALE_FACTOR'):
        return None
    settings = QSettings() if settings is None else settings
    stored = settings.value(QT_SCALE_KEY)
    if not stored:
        return None
    try:
        factor = float(stored)
    except (TypeError, ValueError):
        logger.warning(f"Ignoring invalid {QT_SCALE_KEY}={stored!r}")
        settings.remove(QT_SCALE_KEY)
        return None
    if abs(factor - 1.0) < 1e-6:
        return None
    return f"{factor:g}"


def remember_detected_qt_scale() -> typing.Optional[float]:
    """Store the factor detected for this screen, for Qt to use from the next
    start: a screen can only be queried once the QApplication exists, and by
    then Qt has read QT_SCALE_FACTOR.

    Returns the detected factor when it differs from the one in effect, None
    otherwise.
    """
    if os.environ.get('QT_SCALE_FACTOR'):
        # Set by the session or a launcher: leave it alone.
        return None
    scale = DisplayScale.instance()
    if scale.mode != MODE_AUTO:
        return None
    detected = scale.factor()
    settings = QSettings()
    previous = settings.value(QT_SCALE_KEY)
    settings.setValue(QT_SCALE_KEY, f"{detected:g}")
    try:
        in_effect = float(previous) if previous else 1.0
    except (TypeError, ValueError):
        in_effect = 1.0
    if abs(detected - in_effect) < 1e-6:
        return None
    logger.info(f"Detected a UI scale of {detected:g} ({scale.reason}); "
                f"it will be applied from the next start")
    return detected


def scale_pinned_by_env() -> bool:
    """True when IPLOT_UI_SCALE pins the scale, making the menu inoperative."""
    return bool(os.environ.get('IPLOT_UI_SCALE'))


def register_scale_listener(callback: typing.Callable[[float], None]):
    """Register a callable to run whenever the UI scale changes."""
    if callback not in _scale_listeners:
        _scale_listeners.append(callback)


def base_font_pt() -> float:
    """The application font size before any scaling was applied."""
    global _base_font_pt
    if _base_font_pt is None:
        size = QApplication.font().pointSizeF()
        # A pixel-sized font gives pointSizeF() == -1.
        _base_font_pt = size if size > 0 else 9.0
    return _base_font_pt


def _set_style_sheets_again():
    """Make the widgets with a style sheet of their own take the font and palette in effect: they keep those they
    were polished with until the sheet is set again."""
    for widget in QApplication.allWidgets():
        if widget.styleSheet():
            widget.setStyleSheet(widget.styleSheet())


def _styled(widget: QWidget) -> bool:
    """Whether a style sheet applies to a widget: its own, that of a parent or that of the application."""
    while widget is not None:
        if widget.styleSheet():
            return True
        widget = widget.parentWidget()
    return bool(QApplication.instance().styleSheet())


def _inherit_palettes_again():
    """Make the widgets that inherit their palette take the one in effect. Removing the style sheet of the
    application sometimes leaves one, as the menu bar, marked as styled by it, which keeps it with the palette
    from before: setting a style sheet of its own and none clears the mark."""
    for widget in QApplication.allWidgets():
        if widget.testAttribute(Qt.WidgetAttribute.WA_SetPalette):
            continue
        if widget.testAttribute(Qt.WidgetAttribute.WA_StyleSheet):
            if _styled(widget):
                continue
            widget.setStyleSheet(' ')
            widget.setStyleSheet('')
        widget.setPalette(QPalette())


def apply_ui_scale(value, persist: bool = True):
    """Scale the iplotlib canvas primitives and, for an explicit percentage,
    the widget font with them.

    Scaling the *application font* is what makes the widgets follow: a fair
    amount of MINT's layout is already font-derived (the time-field widths in
    mtAbsoluteTime, the reserved button width in mtMainWindow), and the style
    sheets use em units for the rest.

    ``auto`` leaves that font alone. The platform font already reflects the
    desktop's own answer to the screen (GNOME's font size, Windows text
    scaling, Xft.dpi), whereas the canvas sizes are absolute numbers tuned for
    a FullHD panel that follow no such setting.
    """
    mode, factor_value = parse_scale_setting(value)
    scale = DisplayScale.instance()
    factor = scale.configure(mode=mode, value=factor_value)
    if persist and not os.environ.get('QT_SCALE_FACTOR'):
        # An explicit choice is what Qt should use from the next start; Auto is
        # left to remember_detected_qt_scale.
        if mode == MODE_FIXED:
            QSettings().setValue(QT_SCALE_KEY, f"{factor:g}")
        elif mode == MODE_OFF:
            QSettings().setValue(QT_SCALE_KEY, '1')
    # scale.mode rather than mode: IPLOT_UI_SCALE, when set, wins over the request.
    font_factor = factor if scale.mode == MODE_FIXED else 1.0

    font = QApplication.font()
    size = base_font_pt() * font_factor
    if abs(font.pointSizeF() - size) > 1e-6:
        # Only when it changes, so a session at 100% keeps the platform font
        # untouched.
        font.setPointSizeF(size)
        QApplication.instance().setFont(font)
        # Qt documents setFont as not meant for style-sheet driven widgets:
        # one with a sheet of its own keeps the font it was polished with.
        _set_style_sheets_again()

    if persist:
        QSettings().setValue(SCALE_KEY, value if isinstance(value, str) else str(value))
    logger.info(f"UI scale set to {factor:g} for the canvas, {font_factor:g} for the widgets "
                f"({scale.reason})")

    for callback in list(_scale_listeners):
        try:
            callback(factor)
        except Exception as e:
            logger.warning(f"UI scale listener failed: {e}")
    return factor

# None is the look of the widget style in light colours, Dark the same look in dark ones and Auto either, as the
# system has it. Light is a style sheet shipped in mint/gui/themes/light.qss.
THEME_NONE = 'None'
THEME_DARK = 'Dark'
THEME_LIGHT = 'Light'
THEME_AUTO = 'Auto'
THEMES = (THEME_DARK, THEME_LIGHT, THEME_AUTO)
#: The theme in use, whether a change of the colour scheme of the system reaches _follow_system, whether the
#: application palette is one set here instead of that of the platform, and the style that a dark theme replaced.
_theme = THEME_NONE
_following_system = False
_palette_set = False
_light_only_style = None
#: Styles that draw their controls light whatever the palette.
_LIGHT_ONLY_STYLES = ('windowsvista',)

#: The dark palette that Qt gives the Fusion style on Windows, for the platforms that cannot switch to a dark
#: colour scheme: Linux desktops that do not tell one, the offscreen platform.
_DARK_PALETTE = {
    'Window': '#1e1e1e', 'WindowText': '#ffffff', 'Base': '#2d2d2d', 'AlternateBase': '#343434',
    'ToolTipBase': '#3c3c3c', 'ToolTipText': '#d4d4d4', 'PlaceholderText': '#80ffffff', 'Text': '#ffffff',
    'Button': '#3c3c3c', 'ButtonText': '#ffffff', 'BrightText': '#65bcff', 'Light': '#787878',
    'Midlight': '#5a5a5a', 'Mid': '#282828', 'Dark': '#1e1e1e', 'Shadow': '#000000', 'Highlight': '#0078d4',
    'HighlightedText': '#ffffff', 'Link': '#65bcff', 'LinkVisited': '#32a6ff', 'Accent': '#32a6ff',
}
_DARK_PALETTE_DISABLED = {'WindowText': '#9d9d9d', 'Text': '#9d9d9d', 'ButtonText': '#9d9d9d', 'Base': '#1e1e1e'}


def is_dark(palette: typing.Optional[QPalette] = None) -> bool:
    """Whether a palette, the application's by default, draws light text on a dark window."""
    palette = QGuiApplication.palette() if palette is None else palette
    return (palette.color(QPalette.ColorRole.Window).lightness()
            < palette.color(QPalette.ColorRole.WindowText).lightness())


def blend(a, b, t: float) -> QColor:
    """The colour a fraction `t` of the way from colour `a` to colour `b`."""
    a, b = QColor(a), QColor(b)
    return QColor.fromRgbF(*(x + (y - x) * t for x, y in zip(a.getRgbF()[:3], b.getRgbF()[:3])))


def secondary_text_color(palette: QPalette) -> str:
    """The colour of secondary text, as hints are, on the window: with the contrast WCAG AA asks of text."""
    return blend(palette.color(QPalette.ColorRole.Window), palette.color(QPalette.ColorRole.WindowText), 0.6).name()


def _dark_palette() -> QPalette:
    palette = QPalette()
    for role, colour in _DARK_PALETTE.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    for role, colour in _DARK_PALETTE_DISABLED.items():
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(colour))
    return palette


def _set_colour_scheme(theme: str):
    """Ask the platform for the colour scheme of a theme, as Qt recommends, and set the palette of that scheme where
    the platform keeps the other one."""
    global _palette_set, _light_only_style
    hints = QGuiApplication.styleHints()
    if theme == THEME_AUTO:
        hints.unsetColorScheme()
        dark = hints.colorScheme() == Qt.ColorScheme.Dark
    else:
        dark = theme == THEME_DARK
        hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    app = QApplication.instance()
    if dark and app.style().name().lower() in _LIGHT_ONLY_STYLES:
        # Its controls are light whatever the palette: dark, the look is that of Fusion, which Qt gives dark palettes.
        _light_only_style = app.style().name()
        QApplication.setStyle('Fusion')
    elif not dark and _light_only_style:
        QApplication.setStyle(_light_only_style)
        _light_only_style = None
    if _palette_set:
        # The palette of the platform, which follows the scheme: one set for another theme would stay.
        app.setPalette(QPalette())
        _palette_set = False
    palette = app.palette()
    if dark and not is_dark(palette):
        palette = _dark_palette()
    elif dark:
        # The dark palettes of Qt for Windows give a window that is not active the accent and the selection in the
        # colour of the window, which hides a checked radio button: they keep those of an active one.
        palette = QPalette(palette)
        for role in (QPalette.ColorRole.Accent, QPalette.ColorRole.Highlight):
            palette.setColor(QPalette.ColorGroup.Inactive, role, palette.color(QPalette.ColorGroup.Active, role))
    elif is_dark(palette):
        # The platform stays dark: the light palette of the style.
        palette = app.style().standardPalette()
    if palette != app.palette():
        app.setPalette(palette)
        _palette_set = True


def _follow_system(_scheme=None):
    if _theme == THEME_AUTO:
        _set_colour_scheme(THEME_AUTO)


def _set_theme(name: str) -> bool:
    """Apply a theme (see THEMES); False if there is none of that name."""
    global _theme, _following_system
    if name == THEME_LIGHT:
        qss = _load_theme(name)
        if qss is None:
            return False
    elif name in (THEME_NONE, THEME_DARK, THEME_AUTO):
        qss = ''
    else:
        return False
    if not _following_system:
        QGuiApplication.styleHints().colorSchemeChanged.connect(_follow_system)
        _following_system = True
    _theme = name
    _set_colour_scheme(name)
    QApplication.instance().setStyleSheet(qss)
    _inherit_palettes_again()
    _set_style_sheets_again()
    return True


def apply_style(name: str):
    """Switch the widget style at runtime and persist the choice."""
    if QApplication.setStyle(name) is None:
        logger.warning(f"Unknown widget style: {name}")
        return
    QSettings().setValue(STYLE_KEY, name)
    # A new style sets back the palette of the platform.
    _set_colour_scheme(_theme)


def _load_theme(name: str) -> typing.Optional[str]:
    try:
        data = pkgutil.get_data('mint.gui', f'themes/{name.lower()}.qss')
    except (FileNotFoundError, OSError):
        data = None
    return data.decode('utf-8') if data is not None else None


def apply_theme(name: str):
    """Switch the theme at runtime and persist the choice."""
    if not _set_theme(name):
        logger.warning(f"Unknown theme: {name}")
        return
    QSettings().setValue(THEME_KEY, name)
    if name == THEME_LIGHT:
        # A style sheet can carry font settings, so re-assert the scaled font.
        apply_ui_scale(QSettings().value(SCALE_KEY, DEFAULT_SCALE), persist=False)


def restore_appearance():
    """Re-apply the persisted appearance. Call once, right after the QApplication is created."""
    settings = QSettings()
    # Capture the untouched font before a theme style sheet can change it.
    base_font_pt()
    style = settings.value(STYLE_KEY)
    if style and QApplication.setStyle(style) is None:
        # self-heal legacy/renamed style names so settings and menu state stay consistent
        logger.warning(f"Persisted widget style is not available, resetting it: {style}")
        settings.remove(STYLE_KEY)
    theme = settings.value(THEME_KEY) or THEME_NONE
    if not _set_theme(theme):
        # self-heal legacy/renamed theme names so settings and menu state stay consistent
        logger.warning(f"Persisted theme is not available, resetting it: {theme}")
        settings.setValue(THEME_KEY, THEME_NONE)
        _set_theme(THEME_NONE)
    apply_ui_scale(settings.value(SCALE_KEY, DEFAULT_SCALE), persist=False)


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
        current_scale = str(QSettings().value(SCALE_KEY, DEFAULT_SCALE))
        if current_scale not in (value for _, value in SCALE_CHOICES):
            current_scale = DEFAULT_SCALE
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
