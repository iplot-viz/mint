# Description: A status bar widget.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from PySide6.QtWidgets import QStatusBar


class MTStatusBar(QStatusBar):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.showMessage("Ready.")
