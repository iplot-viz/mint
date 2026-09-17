# Description: A toolbar to import/save signals' description
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]


from PySide6.QtCore import QMargins
from PySide6.QtGui import QAction

from mint.tools.icon_loader import create_icon
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QToolBar, QWidget


class MTSignalsToolBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        self.openAction = QAction(create_icon('open_file'), "&Open Signal Sets")
        self.appendAction = QAction(create_icon('append_file'), "&Append Signal Sets")
        self.saveAction = QAction(create_icon('save_as'), "&Save Signal Sets")
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
