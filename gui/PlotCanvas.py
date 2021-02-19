import json
import os
from functools import partial

from PyQt5 import QtGui
from PyQt5.QtCore import QMargins, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction, QActionGroup, QApplication, QFileDialog, QMainWindow, QMenuBar, QMessageBox, QSizePolicy, QStatusBar, QToolBar
from iplotlib.Canvas import Canvas
from qt import QtPlotCanvas

from gui.Main import StatusBar

try:
	from qt.gnuplot.QtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas
except ModuleNotFoundError:
    print("import 'gnuplot' is not installed")

from util.JSONExporter import JSONExporter


class CanvasToolbar(QToolBar):

    toolSelected = pyqtSignal(str)
    detachPressed = pyqtSignal()
    undo = pyqtSignal()
    redo = pyqtSignal()
    export_json = pyqtSignal()
    import_json = pyqtSignal()
    redraw = pyqtSignal()
    preferences = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum))

        def selectTool(selected):
            self.toolSelected.emit(selected)

        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        for e in [Canvas.MOUSE_MODE_SELECT, Canvas.MOUSE_MODE_CROSSHAIR, Canvas.MOUSE_MODE_PAN, Canvas.MOUSE_MODE_ZOOM]:
            tool_action = QAction(e[3:], self)
            tool_action.setCheckable(True)
            tool_action.setActionGroup(tool_group)
            tool_action.triggered.connect(partial(selectTool, e))
            self.addAction(tool_action)

        self.addSeparator()

        undo_action = QAction("Undo", self)
        undo_action.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"../icons/undo.png")))
        undo_action.triggered.connect(self.undo.emit)
        self.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"../icons/redo.png")))
        redo_action.triggered.connect(self.redo.emit)
        self.addAction(redo_action)

        self.detach_action = QAction("Detach", self)
        # detach_action.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"../icons/fullscreen.png")))
        self.detach_action.triggered.connect(self.detachPressed.emit)
        self.addAction(self.detach_action)

        preferences_action = QAction("Preferences", self)
        preferences_action.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"../icons/options.png")))
        preferences_action.triggered.connect(self.preferences.emit)
        self.addAction(preferences_action)

        self.addAction(QIcon(os.path.join(os.path.dirname(__file__), "../icons/save_as.png")), "Export to JSON", self.export_json.emit)
        self.addAction(QIcon(os.path.join(os.path.dirname(__file__), "../icons/open_file.png")), "Import JSON", self.import_json.emit)
        self.addAction(QIcon(os.path.join(os.path.dirname(__file__), "../icons/rotate180.png")), "Redraw", self.redraw.emit)


class MainCanvas(QMainWindow):

    def __init__(self, detached=False, attach_parent=None, plot_canvas=None, canvas=None):
        super().__init__()
        self.original_canvas = None
        self.plot_canvas: QtPlotCanvas = plot_canvas
        # self.canvas = canvas
        self.toolbar = CanvasToolbar()
        self.toolbar.setVisible(False)

        self.addToolBar(self.toolbar)
        self.setCentralWidget(self.plot_canvas)

        self.detached = False
        self.attach_parent = attach_parent
        self.detached_window = QMainWindow()
        self.detached_window.setStatusBar(StatusBar())
        self.detached_window.layout().setContentsMargins(QMargins())
        self.detached_window.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)

        if hasattr(self.plot_canvas, "process_canvas_toolbar"):
            self.plot_canvas.process_canvas_toolbar(self.toolbar)

        def tool_selected(tool):
            self.plot_canvas.set_mouse_mode(tool)

        def detach():
            if self.detached:
                self.setParent(self.attach_parent)
                self.detached_window.hide()
                self.detached = False
                self.toolbar.detach_action.setText("Detach")
            else:
                self.attach_parent = self.parent()
                self.detached_window.setCentralWidget(self)
                self.detached_window.show()
                self.detached = True
                self.toolbar.detach_action.setText("Reattach")

        self.toolbar.toolSelected.connect(tool_selected)
        self.toolbar.detachPressed.connect(detach)
        self.toolbar.undo.connect(self.plot_canvas.back)
        self.toolbar.redo.connect(self.plot_canvas.forward)
        self.toolbar.redraw.connect(self.draw)

        def do_export():
            try:
                file = QFileDialog.getSaveFileName(self, "Save JSON")
                if file and file[0] and self.plot_canvas and self.plot_canvas.get_canvas():
                    with open(file[0], "w") as out_file:
                        out_file.write(self.export_json())
            except:
                box = QMessageBox()
                box.setIcon(QMessageBox.Critical)
                box.setText("Error exporting file")
                box.exec_()

        def do_import():
            try:
                file = QFileDialog.getOpenFileName(self, "Open CSV")
                if file and file[0]:
                    with open(file[0], "r") as in_file:
                        self.import_json(in_file.read())
            except:
                box = QMessageBox()
                box.setIcon(QMessageBox.Critical)
                box.setText("Error parsing file")
                box.exec_()

        self.toolbar.import_json.connect(do_import)
        self.toolbar.export_json.connect(do_export)

    def export_json(self):
        return JSONExporter().to_json(self.plot_canvas.get_canvas())

    def import_json(self, json):
        self.draw(JSONExporter().from_json(json))

    def draw(self, canvas):
        self.toolbar.setVisible(True)
        self.plot_canvas.set_canvas(canvas)



