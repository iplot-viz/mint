"""Tests for the View > Appearance machinery (mint.gui.mtAppearance).

Covers runtime switching of the widget style, the bundled QSS themes and the
UI scale, persistence of the choices via QSettings, their restoration in a
fresh session (restore_appearance), normalization of legacy/unknown persisted
values, and the menu actions actually driving the appearance.

QSettings is redirected to a temporary directory so the tests never read
or write a real user configuration file.
"""

import os
import re
import tempfile
import unittest

from PySide6.QtCore import QSettings, QStandardPaths, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QStyleFactory

from iplotlib.core.display import DisplayScale
from mint.gui.mtAppearance import (MTAppearanceMenu, QT_SCALE_KEY, SCALE_KEY, STYLE_KEY, THEME_KEY,
                                   THEME_NONE, THEMES, apply_style, apply_theme, apply_ui_scale,
                                   base_font_pt, is_dark, register_scale_listener,
                                   remember_detected_qt_scale, restore_appearance,
                                   startup_qt_scale_factor)
from mint.gui.views.mtSignalItemView import MTSignalItemView
from mint.tests.qAppSingleton import ensure_qapp


class SettingsSandbox(unittest.TestCase):
    """QSettings redirected to a temporary directory, plus menu helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        cls._tmp = tempfile.TemporaryDirectory()
        cls._prev_format = QSettings.defaultFormat()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls._tmp.name)
        cls._org, cls._name = cls.app.organizationName(), cls.app.applicationName()
        cls.app.setOrganizationName("ITER-tests")
        cls.app.setApplicationName("MINT-tests")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.setOrganizationName(cls._org)
        cls.app.setApplicationName(cls._name)
        # restore the process-wide QSettings defaults changed in setUpClass (QSettings has
        # no getter for the search path, so fall back to the platform config location)
        QSettings.setDefaultFormat(cls._prev_format)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                          QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation))
        cls._tmp.cleanup()

    def setUp(self):
        QSettings().clear()
        QApplication.instance().setStyleSheet('')
        self._base_font = QApplication.font()
        DisplayScale.reset()

    def tearDown(self):
        # Back to the light palette the other tests draw in.
        apply_theme(THEME_NONE)
        QApplication.instance().setFont(self._base_font)
        DisplayScale.reset()

    def _submenu_actions(self, menu: MTAppearanceMenu, title: str):
        # Look the submenu up by title rather than by index: the menu grew a
        # third entry and index-based lookups silently pick the wrong one.
        return next(a.menu().actions() for a in menu.actions() if a.text() == title)

    def _theme_actions(self, menu: MTAppearanceMenu):
        return self._submenu_actions(menu, '&Theme')

    def _style_actions(self, menu: MTAppearanceMenu):
        return self._submenu_actions(menu, '&Style')

    def _scale_actions(self, menu: MTAppearanceMenu):
        return self._submenu_actions(menu, 'UI &scale')


class AppearanceTest(SettingsSandbox):

    def test_apply_style_switches_and_persists(self):
        for name in QStyleFactory.keys():
            apply_style(name)
            self.assertEqual(QApplication.style().objectName().lower(), name.lower())
            self.assertEqual(QSettings().value(STYLE_KEY), name)

    def test_apply_unknown_style_is_rejected(self):
        before = QApplication.style().objectName()
        apply_style('no-such-style')
        self.assertEqual(QApplication.style().objectName(), before)
        self.assertIsNone(QSettings().value(STYLE_KEY))

    def test_apply_theme_switches_and_persists(self):
        apply_theme('Light')
        self.assertIn('MINT light theme', QApplication.instance().styleSheet())
        self.assertEqual(QSettings().value(THEME_KEY), 'Light')
        # Without a system that tells a dark scheme, Auto is light, as None is.
        for name, dark in (('Dark', True), ('Auto', False), (THEME_NONE, False)):
            apply_theme(name)
            self.assertEqual(QApplication.instance().styleSheet(), '')
            self.assertEqual(is_dark(), dark)
            self.assertEqual(QSettings().value(THEME_KEY), name)

    def test_dark_is_the_default_look_in_dark_colours(self):
        style = QApplication.style().name()
        apply_theme('Dark')
        self.assertEqual(QApplication.style().name(), style)
        self.assertEqual(QApplication.instance().styleSheet(), '')
        self.assertTrue(is_dark())
        apply_theme(THEME_NONE)
        self.assertFalse(is_dark())

    def test_a_widget_left_marked_as_styled_takes_the_dark_palette(self):
        # Removing the style sheet of the Light theme sometimes leaves a widget, as the menu bar of MINT, marked as
        # styled, which kept it light in Dark.
        window = QMainWindow()
        bar = window.menuBar()
        bar.addMenu('File')
        apply_theme('Light')
        apply_theme('Auto')
        bar.setAttribute(Qt.WidgetAttribute.WA_StyleSheet, True)
        apply_theme('Dark')
        self.assertTrue(is_dark(bar.palette()))
        window.deleteLater()

    def test_a_new_style_keeps_the_dark_palette(self):
        apply_theme('Dark')
        apply_style(QStyleFactory.keys()[0])
        self.assertTrue(is_dark())

    @unittest.skipUnless('windowsvista' in QStyleFactory.keys(), 'only on Windows')
    def test_a_style_that_draws_light_controls_is_fusion_while_dark(self):
        apply_style('windowsvista')
        apply_theme('Dark')
        self.assertEqual(QApplication.style().name().lower(), 'fusion')
        apply_theme(THEME_NONE)
        self.assertEqual(QApplication.style().name().lower(), 'windowsvista')

    def test_restore_appearance_reapplies_persisted_choices(self):
        style = QStyleFactory.keys()[-1]
        QSettings().setValue(STYLE_KEY, style)
        restore_appearance()
        self.assertEqual(QApplication.style().objectName().lower(), style.lower())
        # with a theme active QApplication.style() becomes an anonymous QStyleSheetStyle
        # wrapper, so the style name can no longer be asserted alongside
        QSettings().setValue(THEME_KEY, 'Dark')
        restore_appearance()
        self.assertEqual(QApplication.instance().styleSheet(), '')
        self.assertTrue(is_dark())

    def test_restore_appearance_resets_unknown_theme(self):
        QSettings().setValue(THEME_KEY, 'no-such-theme')
        restore_appearance()
        self.assertEqual(QApplication.instance().styleSheet(), '')
        self.assertEqual(QSettings().value(THEME_KEY), THEME_NONE)

    def test_restore_appearance_resets_unknown_style(self):
        before = QApplication.style().objectName()
        QSettings().setValue(STYLE_KEY, 'no-such-style')
        restore_appearance()
        self.assertEqual(QApplication.style().objectName(), before)
        self.assertIsNone(QSettings().value(STYLE_KEY))

    def test_menu_normalizes_unknown_style(self):
        style = QStyleFactory.keys()[0]
        apply_style(style)
        QSettings().setValue(STYLE_KEY, 'no-such-style')
        menu = MTAppearanceMenu()
        checked = [a.text() for a in self._style_actions(menu) if a.isChecked()]
        self.assertEqual(checked, [style])

    def test_menu_reflects_state_and_normalizes_unknown_theme(self):
        menu = MTAppearanceMenu()
        self.assertEqual([a.text() for a in menu.actions()], ['&Style', '&Theme', 'UI &scale'])
        self.assertEqual([a.text() for a in self._theme_actions(menu)], [THEME_NONE, 'Dark', 'Light', 'Auto'])
        checked = [a.text() for a in self._theme_actions(menu) if a.isChecked()]
        self.assertEqual(checked, [THEME_NONE])

        QSettings().setValue(THEME_KEY, 'no-such-theme')
        menu = MTAppearanceMenu()
        checked = [a.text() for a in self._theme_actions(menu) if a.isChecked()]
        self.assertEqual(checked, [THEME_NONE])

    def test_menu_style_checkmark_survives_active_theme(self):
        style = QStyleFactory.keys()[0]
        apply_style(style)
        apply_theme('Dark')
        menu = MTAppearanceMenu()
        checked = [a.text() for a in self._style_actions(menu) if a.isChecked()]
        self.assertEqual(checked, [style])

    def test_menu_action_applies_theme(self):
        menu = MTAppearanceMenu()
        dark = next(a for a in self._theme_actions(menu) if a.text() == 'Dark')
        dark.trigger()
        self.assertTrue(is_dark())
        self.assertEqual(QSettings().value(THEME_KEY), 'Dark')


class SignalTableGridTest(SettingsSandbox):

    def test_the_grid_shows_where_mid_is_as_light_as_base(self):
        # As the palette of SDCC, where the cells of the variables table did not show.
        palette = QApplication.palette()
        base = palette.color(QPalette.ColorRole.Base)
        palette.setColor(QPalette.ColorRole.Mid, base)
        QApplication.setPalette(palette)
        self.addCleanup(QApplication.setPalette, QPalette())
        view = MTSignalItemView()
        grid = QColor(re.search(r'gridline-color: (#[0-9a-f]{6})', view.view().styleSheet()).group(1))
        self.assertLess(grid.lightness(), base.lightness() - 60)
        view.deleteLater()


class UiScaleTest(SettingsSandbox):
    """The UI scale lever: it must move the widget font and the canvas together."""

    def test_apply_ui_scale_scales_the_application_font(self):
        base = base_font_pt()
        apply_ui_scale('2.0')
        self.assertAlmostEqual(QApplication.font().pointSizeF(), base * 2.0, places=3)
        self.assertEqual(QSettings().value(SCALE_KEY), '2.0')

    def test_applying_twice_does_not_compound(self):
        # The scaled font must be derived from the persisted base every time,
        # otherwise picking 150% twice in a session gives 225%.
        apply_ui_scale('1.5')
        once = QApplication.font().pointSizeF()
        apply_ui_scale('1.5')
        self.assertAlmostEqual(QApplication.font().pointSizeF(), once, places=3)

    def test_scale_reaches_the_canvas_property_scale(self):
        apply_ui_scale('2.0')
        self.assertEqual(DisplayScale.instance().apply('font_size', 8), 16)
        apply_ui_scale('off')
        self.assertEqual(DisplayScale.instance().apply('font_size', 8), 8)

    def test_off_restores_the_base_font(self):
        base = QApplication.font().pointSizeF()
        apply_ui_scale('2.0')
        apply_ui_scale('off')
        self.assertAlmostEqual(QApplication.font().pointSizeF(), base, places=3)

    def test_unknown_persisted_scale_falls_back_to_auto(self):
        # A stale or hand-edited settings value must not stop MINT starting.
        QSettings().setValue(SCALE_KEY, 'mostly')
        restore_appearance()
        self.assertEqual(DisplayScale.instance().mode, 'auto')

    def test_nothing_persisted_means_auto_and_an_untouched_font_on_a_plain_screen(self):
        # The test screen reports no high DPI, so the automatic mode must
        # resolve to 1.0 and leave the application font exactly as it was.
        base = QApplication.font().pointSizeF()
        restore_appearance()
        self.assertEqual(DisplayScale.instance().mode, 'auto')
        self.assertEqual(DisplayScale.instance().factor(), 1.0)
        self.assertAlmostEqual(QApplication.font().pointSizeF(), base, places=3)
        menu = MTAppearanceMenu()
        checked = [a.text() for a in self._scale_actions(menu) if a.isChecked()]
        self.assertEqual(checked, ['Auto'])

    def test_auto_scales_the_canvas_but_not_the_widget_font(self):
        # The platform font already reflects the desktop's settings for the
        # screen; only an explicit percentage enlarges it.
        from unittest.mock import patch
        unscaled_4k = dict(available=True, device_pixel_ratio=1.0, logical_dpi=96.0,
                           physical_dpi=163.0, width_px=3840, height_px=2160, remote_markers=[])
        base = QApplication.font().pointSizeF()
        with patch('iplotlib.core.display.collect_metrics', return_value=unscaled_4k):
            apply_ui_scale('auto')
            self.assertEqual(DisplayScale.instance().factor(), 1.75)
        self.assertAlmostEqual(QApplication.font().pointSizeF(), base, places=3)

    def test_listeners_are_notified(self):
        seen = []
        register_scale_listener(seen.append)
        apply_ui_scale('1.5')
        self.assertTrue(seen)
        self.assertAlmostEqual(seen[-1], 1.5, places=3)

    def test_listener_exception_does_not_break_the_scale_change(self):
        def boom(_factor):
            raise RuntimeError('listener failure')
        register_scale_listener(boom)
        apply_ui_scale('1.25')
        self.assertAlmostEqual(DisplayScale.instance().factor(), 1.25, places=3)

    def test_widgets_with_their_own_style_sheet_follow_the_scale(self):
        # Such a widget keeps the font it was polished with unless its sheet
        # is re-applied; the signals table and the console are styled this way.
        from PySide6.QtWidgets import QLabel
        label = QLabel('styled')
        label.setStyleSheet('QLabel { color: red; }')
        label.ensurePolished()
        apply_ui_scale('2.0')
        self.assertAlmostEqual(label.font().pointSizeF(), base_font_pt() * 2.0, places=3)
        apply_ui_scale('off')
        self.assertAlmostEqual(label.font().pointSizeF(), base_font_pt(), places=3)

    def test_theme_change_keeps_the_scaled_font(self):
        # Installing a style sheet can reset the application font.
        apply_ui_scale('2.0')
        scaled = QApplication.font().pointSizeF()
        apply_theme('Dark')
        self.assertAlmostEqual(QApplication.font().pointSizeF(), scaled, places=3)

    def test_menu_reflects_the_persisted_scale(self):
        apply_ui_scale('1.5')
        menu = MTAppearanceMenu()
        checked = [a.text() for a in self._scale_actions(menu) if a.isChecked()]
        self.assertEqual(checked, ['150%'])

    def test_menu_action_applies_the_scale(self):
        menu = MTAppearanceMenu()
        action = next(a for a in self._scale_actions(menu) if a.text() == '200%')
        action.trigger()
        self.assertAlmostEqual(DisplayScale.instance().factor(), 2.0, places=3)


class QtScaleFactorTest(SettingsSandbox):
    """QT_SCALE_FACTOR is per machine and never travels with a workspace."""

    def setUp(self):
        super().setUp()
        self._env = os.environ.pop('QT_SCALE_FACTOR', None)

    def tearDown(self):
        os.environ.pop('QT_SCALE_FACTOR', None)
        if self._env is not None:
            os.environ['QT_SCALE_FACTOR'] = self._env
        super().tearDown()

    def test_nothing_to_export_without_a_stored_factor(self):
        self.assertIsNone(startup_qt_scale_factor(QSettings()))

    def test_stored_factor_is_exported(self):
        QSettings().setValue(QT_SCALE_KEY, '1.75')
        self.assertEqual(startup_qt_scale_factor(QSettings()), '1.75')

    def test_a_factor_of_one_exports_nothing(self):
        QSettings().setValue(QT_SCALE_KEY, '1')
        self.assertIsNone(startup_qt_scale_factor(QSettings()))

    def test_an_invalid_stored_factor_is_discarded(self):
        # A hand-edited or stale settings file must not stop MINT starting.
        QSettings().setValue(QT_SCALE_KEY, 'big')
        self.assertIsNone(startup_qt_scale_factor(QSettings()))
        self.assertIsNone(QSettings().value(QT_SCALE_KEY))

    def test_the_environment_wins(self):
        # A launcher script or a site profile stays in control.
        QSettings().setValue(QT_SCALE_KEY, '1.75')
        os.environ['QT_SCALE_FACTOR'] = '2'
        self.assertIsNone(startup_qt_scale_factor(QSettings()))
        self.assertIsNone(remember_detected_qt_scale())

    def test_an_explicit_percentage_is_stored_for_the_next_start(self):
        apply_ui_scale('1.5')
        self.assertEqual(QSettings().value(QT_SCALE_KEY), '1.5')

    def test_choosing_off_stores_one(self):
        apply_ui_scale('1.5')
        apply_ui_scale('off')
        self.assertEqual(QSettings().value(QT_SCALE_KEY), '1')


if __name__ == "__main__":
    unittest.main()
