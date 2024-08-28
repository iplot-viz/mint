# Description: A toolbar to import/save signals' description
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import pkgutil

from PySide6.QtCore import QMargins
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QToolBar, QWidget


class MTSignalsToolBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        open_pxmap = QPixmap()
        open_pxmap.loadFromData(pkgutil.get_data('mint.gui', 'icons/open_file.png'))
        append_pxmap = QPixmap()
        append_pxmap.loadFromData(pkgutil.get_data('mint.gui', 'icons/append_file.png'))
        save_pxmap = QPixmap()
        save_pxmap.loadFromData(pkgutil.get_data('mint.gui', 'icons/save_as.png'))

        self.openAction = QAction(QIcon(open_pxmap), "&Open Signal Sets")
        self.appendAction = QAction(QIcon(append_pxmap), "&Append Signal Sets")
        self.saveAction = QAction(QIcon(save_pxmap), "&Save Signal Sets")
        self.configureColsBtn = QPushButton("Hide/Show &Columns")
        self.searchVarsBtn = QPushButton("&Search Vars")
        self.loadModules = QPushButton("&Load new module")

        tb = QToolBar()
        tb.addAction(self.openAction)
        tb.addAction(self.appendAction)
        tb.addAction(self.saveAction)
        tb.addSeparator()
        tb.addWidget(self.configureColsBtn)
        tb.addSeparator()
        tb.addWidget(self.searchVarsBtn)
        tb.addSeparator()
        tb.addWidget(self.loadModules)

        self.layout().addWidget(tb)
