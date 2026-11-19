"""Shared fixtures and helpers for MINT integration tests."""

import atexit
import json
import os
import tempfile

ROOT = os.path.dirname(__file__)
CSV_DIR = os.path.join(ROOT, 'csv', 'ITER')
WORKSPACES_DIR = os.path.join(ROOT, 'workspaces')
BASELINE_DIR = os.path.join(ROOT, 'baseline')


def _unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def write_csv_datasource_config() -> str:
    """Write a temporary IPLOT_SOURCES_CONFIG pointing at the CSV fixture.

    Returns the absolute path to the generated cfg. The file is written to
    a system temp location so concurrent pytest workers do not collide,
    and unlinked at interpreter exit so repeated test runs do not leak.
    """
    # Forward slashes for JSON on all platforms.
    csv_path = CSV_DIR.replace('\\', '/')
    cfg = {
        "csv": {
            "path": csv_path,
            "type": "CSV",
        }
    }
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.cfg', delete=False, encoding='utf-8')
    json.dump(cfg, tmp)
    tmp.close()
    os.environ['IPLOT_SOURCES_CONFIG'] = tmp.name
    atexit.register(_unlink_quiet, tmp.name)
    return tmp.name


class SettingsInTempDir:
    """QSettings in a temporary directory while the tests of a class run, so they never read or write a real user
    configuration file; each test starts with none."""

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtCore import QSettings
        from mint.tests.qAppSingleton import ensure_qapp
        super().setUpClass()
        cls.app = ensure_qapp()
        cls._settings_dir = tempfile.TemporaryDirectory()
        cls._format = QSettings.defaultFormat()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls._settings_dir.name)
        cls._org, cls._name = cls.app.organizationName(), cls.app.applicationName()
        cls.app.setOrganizationName("ITER-tests")
        cls.app.setApplicationName("MINT-tests")

    @classmethod
    def tearDownClass(cls) -> None:
        from PySide6.QtCore import QSettings, QStandardPaths
        cls.app.setOrganizationName(cls._org)
        cls.app.setApplicationName(cls._name)
        QSettings.setDefaultFormat(cls._format)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                          QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation))
        cls._settings_dir.cleanup()
        super().tearDownClass()

    def setUp(self):
        from PySide6.QtCore import QSettings
        super().setUp()
        QSettings().clear()
