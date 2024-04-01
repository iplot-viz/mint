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


def test_mt_about_prepareButtons(mt_about):
    """
    Test case for _prepareButtons method.
    """
    mt_about._prepareButtons()
    assert mt_about._copyBtn.text() == "Copy to clipboard"

def test_mt_about_prepareEnvironmentWidget(mt_about):
    """
    Test case for _prepareEnvironmentWidget method.
    """
    mt_about._prepareEnvironmentWidget()
    assert mt_about._environmentWidget.model() == mt_about._model

def test_mt_about_prepareDescription(mt_about):
    """
    Test case for _prepareDescription method.
    """
    mt_about._prepareDescription()
    assert isinstance( mt_about._descriptionWidget, QWidget)
    assert mt_about._descriptionWidget.layout().count() == 4

def test_mt_about_prepareIcon(mt_about):
    """
    Test case for _prepareIcon method.
    """
    mt_about._prepareIcon()
    assert mt_about.iconLabel.pixmap() is not None
    assert mt_about.iconLabel.pixmap().size().width() >= 64
    assert mt_about.iconLabel.pixmap().size().height() >= 64

def test_mt_about_catalogEnvironment(mt_about):
    """
    Test case for catalogEnvironment method.
    """
    mt_about.catalogEnvironment()
    assert mt_about._model.columnCount() == 3
    assert mt_about._model.rowCount() == len(packages)

def test_mt_about_getContentsAsString(mt_about):
    """
    Test case for getContentsAsString method.
    """
    mt_about.catalogEnvironment()
    contents = mt_about.getContentsAsString()
    assert isinstance(contents, str)

    # Check if the contents are in JSON format
    data = json.loads(contents)
    assert len(data) == len(packages)
