# Description: A helpful icon loader.
# Author: Jaswant Sai Panchumarti

import pkgutil

from PySide6.QtGui import QPixmap, QIcon


def create_pxmap(name, package: str = 'mint.gui', ext: str = 'png') -> QPixmap:
    pxmap = QPixmap()
    pxmap.loadFromData(pkgutil.get_data(package, f"icons/{name}.{ext}"))
    return pxmap


def create_icon(name, package: str = 'mint.gui', ext: str = 'png') -> QIcon:
    return QIcon(create_pxmap(name, package, ext))
