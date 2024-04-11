# Description: A helpful icon loader.
# Author: Jaswant Sai Panchumarti

import pkgutil

from PySide6.QtGui import QPixmap, QIcon


def create_pxmap(name, ext: str = 'png') -> QPixmap:
    pxmap = QPixmap()
    pxmap.loadFromData(pkgutil.get_data("mint.gui", f"icons/{name}.{ext}"))
    return pxmap


def create_icon(name, ext: str = 'png') -> QIcon:
    return QIcon(create_pxmap(name, ext))
