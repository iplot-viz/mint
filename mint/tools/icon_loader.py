# Description: A helpful icon loader.
# Author: Jaswant Sai Panchumarti
# Changelog:
#   HiDPI: create_icon tags the device pixel ratio so tool bars stay sharp on a
#          scaled display. create_pxmap stays untagged for callers that need the
#          raw bitmap (the multi-size application icon, the About logo).

import pkgutil

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap


def _device_pixel_ratio() -> float:
    if QGuiApplication.instance() is None:
        return 1.0
    screen = QGuiApplication.primaryScreen()
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def create_pxmap(name, ext: str = 'png') -> QPixmap:
    """Load a packaged pixmap at its native size, untagged."""
    pxmap = QPixmap()
    pxmap.loadFromData(QByteArray(pkgutil.get_data("mint.gui", f"icons/{name}.{ext}")))
    return pxmap


def create_icon(name, ext: str = 'png') -> QIcon:
    """Load a packaged icon, tagged with the current device pixel ratio.

    Without the ratio, Qt reads an 18x18 PNG as 18 *logical* pixels and upscales
    it to 36 device pixels at 200%, which is what makes the tool bar look soft
    on a scaled 4K display. Tagging it makes Qt draw the bitmap at its native
    resolution instead.
    """
    pxmap = create_pxmap(name, ext)
    ratio = _device_pixel_ratio()
    if ratio > 1.0:
        pxmap.setDevicePixelRatio(ratio)
    return QIcon(pxmap)
