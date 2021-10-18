# Description: A toolbar to import/save signals' description
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import pkgutil

from PySide2.QtCore import QMargins, Signal
from PySide2.QtGui import QIcon, QPixmap
from PySide2.QtWidgets import QAction, QHBoxLayout, QToolBar, QWidget


class MTSignalsToolBar(QWidget):

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

        self.openAction = QAction(QIcon(open_pxmap), "&Open CSV")
        self.saveAction = QAction(QIcon(save_pxmap), "&Save CSV")
        
        tb = QToolBar()
        tb.addAction(self.openAction)
        tb.addAction(self.saveAction)

        self.layout().addWidget(tb)
