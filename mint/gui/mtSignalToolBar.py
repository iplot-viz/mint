# Description: A toolbar to import/save signals' description
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import pkgutil

from qtpy.QtCore import QMargins, Signal
from qtpy.QtGui import QIcon, QPixmap
from qtpy.QtWidgets import QHBoxLayout, QToolBar, QWidget


class MTSignalsToolBar(QWidget):
    exportCsv = Signal()
    importCsv = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        open_pxmap = QPixmap()
        open_pxmap.loadFromData(pkgutil.get_data(
            'mint.gui', 'icons/open_file.png'))
        save_pxmap = QPixmap()
        save_pxmap.loadFromData(pkgutil.get_data(
            'mint.gui', 'icons/save_as.png'))

        tb = QToolBar()
        tb.addAction(QIcon(open_pxmap), "Open CSV",
                     self.importCsv.emit)
        tb.addAction(QIcon(save_pxmap), "Save CSV",
                     self.exportCsv.emit)
        self.layout().addWidget(tb)
