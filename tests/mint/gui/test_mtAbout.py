import pytest
from PySide6.QtWidgets import QDialog, QWidget
from mint.gui.mtAbout import MTAbout, packages
from pytestqt.qtbot import QtBot
import json


@pytest.fixture
def mt_about(qtbot: QtBot):
    mt_about = MTAbout()
    qtbot.addWidget(mt_about)
    return mt_about


def test_mt_about_initialization(mt_about):
    """
    Test case for MTAbout initialization.
    """
    assert isinstance(mt_about, QDialog)
    assert mt_about.windowTitle() == "About MINT"
    assert mt_about._layout.count() == 4


def test_mt_about_prepare_buttons(mt_about):
    """
    Test case for _prepareButtons method.
    """
    mt_about._prepare_buttons()
    assert mt_about._copyBtn.text() == "Copy to clipboard"


def test_mt_about_prepare_environment_widget(mt_about):
    """
    Test case for _prepareEnvironmentWidget method.
    """
    mt_about._prepare_environment_widget()
    assert mt_about._environmentWidget.model() == mt_about._model


def test_mt_about_prepare_description(mt_about):
    """
    Test case for _prepareDescription method.
    """
    mt_about._prepare_description()
    assert isinstance(mt_about._descriptionWidget, QWidget)
    assert mt_about._descriptionWidget.layout().count() == 4


def test_mt_about_prepare_icon(mt_about):
    """
    Test case for _prepareIcon method.
    """
    mt_about._prepare_icon()
    assert mt_about.iconLabel.pixmap() is not None
    assert mt_about.iconLabel.pixmap().size().width() >= 64
    assert mt_about.iconLabel.pixmap().size().height() >= 64


def test_mt_about_catalog_environment(mt_about):
    """
    Test case for catalogEnvironment method.
    """
    mt_about.catalog_environment()
    assert mt_about._model.columnCount() == 3
    assert mt_about._model.rowCount() == len(packages)


def test_mt_about_get_contents_as_string(mt_about):
    """
    Test case for getContentsAsString method.
    """
    mt_about.catalog_environment()
    contents = mt_about.get_contents_as_string()
    assert isinstance(contents, str)

    # Check if the contents are in JSON format
    data = json.loads(contents)
    assert len(data) == len(packages)
