import os

from qtpy.QtCore import QMargins, Signal
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QHBoxLayout, QToolBar, QWidget

class MTSignalsToolBar(QWidget):
    exportCsv = Signal()
    importCsv = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        tb = QToolBar()
        tb.addAction(QIcon(os.path.join(os.path.dirname(__file__), "icons/open_file.png")), "Open CSV",
                     self.importCsv.emit)
        tb.addAction(QIcon(os.path.join(os.path.dirname(__file__), "icons/save_as.png")), "Save CSV",
                     self.exportCsv.emit)
        self.layout().addWidget(tb)
