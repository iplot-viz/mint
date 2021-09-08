from gui.dataRanges.dataRange import DataRange
import os
from pathlib import Path
from threading import Timer

from iplotlib.core.canvas import Canvas
from iplotlib.data_access.streamer import CanvasStreamer
from iplotlib.qt.qtCanvasToolbar import CanvasToolbar
from iplotDataAccess.dataAccess import DataAccess
from iplotLogging import setupLogger as sl
from iplotProcessing.core import Context

from gui.dataRangeSelector import DataRangeSelector
from gui.menuBar import MainMenuBar
from gui.statusBar import StatusBar
from gui.streamerDialog import StreamerDialog
from gui.variablesTable import VariablesTable

from common.verifyModel import verifyDataRangeModel, verifyTableModel

from qtpy import QtCore, QtGui, QtWidgets


logger = sl.get_logger(__name__, "INFO")


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, canvas: Canvas, context: Context, da: DataAccess, header: dict, model: dict, impl: str = "matplotlib", parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.canvas = canvas
        self.context = context
        self.da = da
        self.header = header

        verifyDataRangeModel(model)

        self.model = model
        self.refresh_timer = None

        self.streamer_dialog = StreamerDialog(self)

        self.right_column = QtWidgets.QWidget()
        self.right_column.setLayout(QtWidgets.QVBoxLayout())

        if impl.lower() == "matplotlib":
            from iplotlib.impl.matplotlib.qt.qtMatplotlibCanvas import QtMatplotlibCanvas
            self.qt_canvas = QtMatplotlibCanvas(tight_layout=True)
        elif impl.lower() == "vtk":
            from iplotlib.impl.vtk.qt import QtVTKCanvas
            self.qt_canvas = QtVTKCanvas()

        self.toolbar = CanvasToolbar(qt_canvas=self.qt_canvas)
        self.right_column.layout().addWidget(self.toolbar)
        self.right_column.layout().addWidget(self.qt_canvas)

        self.variables_table = VariablesTable(
            context=self.context, data_access=da, header=header, model=self.model.get("table"), parent=self)
        self.range_selector = DataRangeSelector(self.model.get("range"), parent=self)

        self.draw_button = QtWidgets.QPushButton("Draw")
        self.draw_button.setIcon(
            QtGui.QIcon(os.path.join(os.path.dirname(__file__), "gui/icons/plot.png")))
        self.stream_button = QtWidgets.QPushButton("Stream")
        self.stream_button.setIcon(
            QtGui.QIcon(os.path.join(os.path.dirname(__file__), "gui/icons/plot.png")))

        self.left_column_buttons = QtWidgets.QWidget()
        self.left_column_buttons.setLayout(QtWidgets.QHBoxLayout())
        self.left_column_buttons.layout().setContentsMargins(QtCore.QMargins())
        self.left_column_buttons.layout().addWidget(self.stream_button)
        self.left_column_buttons.layout().addWidget(self.draw_button)

        self.left_column = QtWidgets.QWidget()
        self.left_column.setLayout(QtWidgets.QVBoxLayout())
        self.left_column.layout().setContentsMargins(QtCore.QMargins())
        self.left_column.layout().addWidget(self.range_selector)
        self.left_column.layout().addWidget(self.variables_table)
        self.left_column.layout().addWidget(self.left_column_buttons)

        self.central_widget = QtWidgets.QSplitter()
        self.central_widget.addWidget(self.left_column)
        self.central_widget.addWidget(self.right_column)

        self.status_bar = StatusBar(parent=self)

        self.menu_bar = MainMenuBar(export_widgets=dict(
            variables_table=self.variables_table,
            main_canvas=self.qt_canvas,
            time_model=self.range_selector))

        self.setCentralWidget(self.central_widget)
        self.setMenuBar(self.menu_bar)
        self.setStatusBar(self.status_bar)

        # Setup connections
        self.draw_button.clicked.connect(self.draw_clicked)
        self.stream_button.clicked.connect(self.stream_clicked)
        self.streamer_dialog.stream_started.connect(self.do_stream)
        self.range_selector.cancel_refresh.connect(self.stop_auto_refresh)

    def start_auto_refresh(self):
        if self.canvas.auto_refresh:
            logger.info(
                F"Scheduling canvas refresh in {self.canvas.auto_refresh} seconds")
            self.refresh_timer = Timer(
                self.canvas.auto_refresh, self.draw_clicked)
            self.refresh_timer.daemon = True
            self.refresh_timer.start()
            self.range_selector.refresh_activate.emit()

    def stop_auto_refresh(self):
        self.range_selector.refresh_deactivate.emit()
        if self.refresh_timer is not None:
            self.refresh_timer.cancel()

    def draw_clicked(self):
        """This function creates and draws the canvas getting data from variables table and time/pulse widget"""
        time_model = self.range_selector.get_model()
        new_canvas = self.variables_table.create_canvas(time_model)
        self.canvas.rows = new_canvas.rows
        self.canvas.cols = new_canvas.cols
        self.canvas.plots = new_canvas.plots
        self.canvas.auto_refresh = new_canvas.auto_refresh
        self.canvas.autoscale = new_canvas.autoscale
        self.canvas.streaming = False

        dump_dir = os.path.expanduser("~/.local/1Dtool/dumps/")
        Path(dump_dir).mkdir(parents=True, exist_ok=True)
        self.variables_table.export_csv(os.path.join(
            dump_dir, "variables_table_" + str(os.getpid()) + ".csv"))

        self.context.refresh()

        self.stop_auto_refresh()

        self.qt_canvas.unfocus_plot()
        self.qt_canvas.set_canvas(self.canvas)

        self.start_auto_refresh()

    def stream_clicked(self):
        """This function shows the streaming dialog and then creates a canvas that is used when streaming"""
        if self.streamer_dialog.streamer is None:
            self.streamer_dialog.show()
            self.stream_button.setText("Stop")
        else:
            self.streamer_dialog.streamer.stop()
            self.streamer_dialog.streamer = None
            self.stream_button.setText("Stream")

    def stream_callback(self, signal):
        self.qt_canvas.matplotlib_canvas.refresh_signal(signal)

    def do_stream(self):
        self.streamer_dialog.hide()
        stream_canvas = self.variables_table.create_canvas(
            stream_window=self.streamer_dialog.stream_window_spinbox.value())
        self.canvas.rows = stream_canvas.rows
        self.canvas.cols = stream_canvas.cols
        self.canvas.auto_refresh = stream_canvas.auto_refresh
        self.canvas.streaming = True
        self.canvas.plots = stream_canvas.plots
        self.qt_canvas.unfocus_plot()
        self.qt_canvas.set_canvas(self.canvas)

        self.streamer_dialog.streamer = CanvasStreamer(self.da)
        self.streamer_dialog.streamer.start(self.canvas, self.stream_callback)
        self.stream_button.setText("Stop")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        QtWidgets.QApplication.closeAllWindows()
        super().closeEvent(event)
