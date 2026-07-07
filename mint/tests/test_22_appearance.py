"""Tests for the View > Appearance machinery (mint.gui.mtAppearance).

Covers runtime switching of the widget style and the bundled QSS themes,
persistence of both choices via QSettings, their restoration in a fresh
session (restore_appearance), normalization of legacy/unknown persisted
values, and the menu actions actually driving the appearance.

QSettings is redirected to a temporary directory so the tests never read
or write a real user configuration file.
"""

import tempfile
import unittest

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication, QStyleFactory

from mint.gui.mtAppearance import (MTAppearanceMenu, STYLE_KEY, THEME_KEY, THEME_NONE, THEMES,
                                   apply_style, apply_theme, restore_appearance)
from mint.tests.qAppSingleton import ensure_qapp


class AppearanceTest(unittest.TestCase):
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

    def _theme_actions(self, menu: MTAppearanceMenu):
        return menu.actions()[-1].menu().actions()

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
        for name in THEMES:
            apply_theme(name)
            self.assertIn(f'MINT {name.lower()} theme', QApplication.instance().styleSheet())
            self.assertEqual(QSettings().value(THEME_KEY), name)
        apply_theme(THEME_NONE)
        self.assertEqual(QApplication.instance().styleSheet(), '')
        self.assertEqual(QSettings().value(THEME_KEY), THEME_NONE)

    def test_restore_appearance_reapplies_persisted_choices(self):
        style = QStyleFactory.keys()[-1]
        QSettings().setValue(STYLE_KEY, style)
        restore_appearance()
        self.assertEqual(QApplication.style().objectName().lower(), style.lower())
        # with a theme active QApplication.style() becomes an anonymous QStyleSheetStyle
        # wrapper, so the style name can no longer be asserted alongside
        QSettings().setValue(THEME_KEY, 'Dark')
        restore_appearance()
        self.assertIn('MINT dark theme', QApplication.instance().styleSheet())

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
        checked = [a.text() for a in menu.actions()[0].menu().actions() if a.isChecked()]
        self.assertEqual(checked, [style])

    def test_menu_reflects_state_and_normalizes_unknown_theme(self):
        menu = MTAppearanceMenu()
        self.assertEqual([a.text() for a in menu.actions()], ['&Style', '&Theme'])
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
        checked = [a.text() for a in menu.actions()[0].menu().actions() if a.isChecked()]
        self.assertEqual(checked, [style])

    def test_menu_action_applies_theme(self):
        menu = MTAppearanceMenu()
        dark = next(a for a in self._theme_actions(menu) if a.text() == 'Dark')
        dark.trigger()
        self.assertIn('MINT dark theme', QApplication.instance().styleSheet())
        self.assertEqual(QSettings().value(THEME_KEY), 'Dark')


if __name__ == "__main__":
    unittest.main()
