# Description: A toolbar to import/save signals' description
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]


from PySide6.QtCore import QEvent, QMargins
from PySide6.QtGui import QAction

from iplotlib.qt.utils.icon_loader import create_icon as canvas_icon
from iplotlib.qt.utils.palette import theme_colors
from mint.tools.icon_loader import create_icon
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QToolBar, QWidget


class MTSignalsToolBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        self.openAction = QAction("&Open Signal Sets")
        self.appendAction = QAction("&Append Signal Sets")
        self.saveAction = QAction("&Save Signal Sets")
        self._icons_theme = theme_colors()
        self._set_icons()
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

    def _set_icons(self):
        # The canvas tool bar's own open and save, so the File menu and both tool bars look alike.
        self.openAction.setIcon(canvas_icon('open_file', 'svg'))
        self.appendAction.setIcon(create_icon('append_file', 'svg'))
        self.saveAction.setIcon(canvas_icon('save_as', 'svg'))

    def changeEvent(self, event):
        super().changeEvent(event)
        # A theme chosen in View > Appearance changes the palette: the icons are drawn again in its grey.
        if event.type() == QEvent.Type.PaletteChange and theme_colors() != self._icons_theme:
            self._icons_theme = theme_colors()
            self._set_icons()
