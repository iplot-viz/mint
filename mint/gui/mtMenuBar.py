# Description: A menu bar with commonly used actions (workspace, help, etc)
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import json

from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QAction, QActionGroup, QApplication, QFileDialog, QMainWindow, QMenuBar, QMessageBox, QSizePolicy, QStatusBar

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)


class MTMenuBar(QMenuBar):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Maximum))
