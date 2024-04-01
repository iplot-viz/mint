from mint.tools.icon_loader import create_pxmap
from mint.tools.icon_loader import create_icon
from pytestqt.qtbot import QtBot

#
# create_pxmap(...)
#
def test_create_pxmap_existing_icon(qtbot: QtBot):
    """
    Test that the function correctly creates a QPixmap from an existing icon.
    """

    # Given
    icon_name = "append_file"
    package = "tests.mint.gui"

    # When
    qt_icon = create_pxmap(icon_name, package)

    # Then
    assert not qt_icon.isNull(), "QPixmap should not be null"
    assert qt_icon.width() == 512, "QPixmap width should be 512"
    assert qt_icon.height() == 512, "QPixmap height should be 512"


#
# create_pxmap(...)
#
def test_create_icon_existing_icon(qtbot: QtBot):
    """
    Test that the function correctly creates a QPixmap from an existing icon.
    """

    # Given
    icon_name = "append_file"
    package = "tests.mint.gui"

    # When
    qt_icon = create_icon(icon_name, package)

    # Then
    assert not qt_icon.isNull(), "QIcon should not be null"
    assert qt_icon.availableSizes() != [], "Icon should have available sizes"
    assert qt_icon.availableSizes()[0].width() == 512, "QIcon width should be 512"
    assert qt_icon.availableSizes()[0].height() == 512, "QIcon height should be 512"