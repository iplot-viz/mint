# Description: A main window embedding a table of signals' description on the right
#               and a Qt iplotlib canvas on the left.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from functools import partial
import json
from pathlib import Path
from threading import Timer
import os
import pkgutil
import typing

from PySide2.QtCore import QMargins, Qt, Slot
from PySide2.QtGui import QCloseEvent, QIcon, QKeySequence, QPixmap
from PySide2.QtWidgets import QAction, QActionGroup, QApplication, QDockWidget, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget

from iplotlib.core.axis import LinearAxis
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.data_access import DataAccessSignal
from iplotlib.data_access import CanvasStreamer
from iplotlib.qt.gui.iplotQtMainWindow import IplotQtMainWindow


from iplotDataAccess.dataAccess import DataAccess
from iplotProcessing.core import Context, SignalDescription
from iplotProcessing.core.environment import DEFAULT_BLUEPRINT_FILE

from mint.gui.mtDataRangeSelector import MTDataRangeSelector
from mint.gui.mtMenuBar import MTMenuBar
from mint.gui.mtStatusBar import MTStatusBar
from mint.gui.mtStreamConfigurator import MTStreamConfigurator
from mint.gui.mtSignalTable import MTSignalTable
from mint.tools.sanity_checks import check_data_range


from iplotLogging import setupLogger as sl
logger = sl.get_logger(__name__, "INFO")


class MTMainWindow(IplotQtMainWindow):

    def __init__(self,
                 canvas: Canvas,
                 context: Context,
                 da: DataAccess,
                 model: dict,
                 blueprint: os.PathLike = DEFAULT_BLUEPRINT_FILE,
                 impl: str = "matplotlib",
                 parent: typing.Optional[QWidget] = None,
                 flags: Qt.WindowFlags = Qt.WindowFlags()):

        self.canvas = canvas
        self.context = context
        self.da = da
        self.plot_class = PlotXY

        self.refreshTimer = None
        self.default_dec_samples = 1000

        check_data_range(model)
        self.model = model

        super().__init__(parent=parent, flags=flags)

        self.graphicsArea = QWidget(self)
        self.graphicsArea.setLayout(QVBoxLayout())
        self.graphicsArea.layout().addWidget(self.toolBar)
        self.graphicsArea.layout().addWidget(self.canvasStack)
        self.streamerCfgWidget = MTStreamConfigurator(self)

        if impl.lower() == "matplotlib":
            from iplotlib.impl.matplotlib.qt.qtMatplotlibCanvas import QtMatplotlibCanvas
            self.canvasStack.addWidget(QtMatplotlibCanvas(
                tight_layout=True, canvas=self.canvas, parent=self.canvasStack))
        elif impl.lower() == "vtk":
            from iplotlib.impl.vtk.qt import QtVTKCanvas
            self.canvasStack.addWidget(QtVTKCanvas(
                canvas=self.canvas, parent=self.canvasStack))

        self.sigTable = MTSignalTable(blueprint=blueprint, parent=self)
        self.dataRangeSelector = MTDataRangeSelector(
            self.model.get("range"), parent=self)

        self.draw_button = QPushButton("Draw")
        pxmap = QPixmap()
        pxmap.loadFromData(pkgutil.get_data('mint.gui', 'icons/plot.png'))
        self.draw_button.setIcon(QIcon(pxmap))
        self.stream_button = QPushButton("Stream")
        self.stream_button.setIcon(QIcon(pxmap))

        self.daWidgetButtons = QWidget(self)
        self.daWidgetButtons.setLayout(QHBoxLayout())
        self.daWidgetButtons.layout().setContentsMargins(QMargins())
        self.daWidgetButtons.layout().addWidget(self.stream_button)
        self.daWidgetButtons.layout().addWidget(self.draw_button)

        self.dataAccessWidget = QWidget(self)
        self.dataAccessWidget.setLayout(QVBoxLayout())
        self.dataAccessWidget.layout().setContentsMargins(QMargins())
        self.dataAccessWidget.layout().addWidget(self.dataRangeSelector)
        self.dataAccessWidget.layout().addWidget(self.sigTable)
        self.dataAccessWidget.layout().addWidget(self.daWidgetButtons)

        self._statusBar = MTStatusBar(parent=self)

        file_menu = self.menuBar().addMenu("&File")
        help_menu = self.menuBar().addMenu("&Help")

        exit_action = QAction("Exit", self.menuBar())
        exit_action.setShortcuts(QKeySequence.Quit)
        exit_action.triggered.connect(QApplication.closeAllWindows)

        about_action = QAction("About Qt", self.menuBar())
        about_action.setShortcuts(QKeySequence.New)
        about_action.setStatusTip("About Qt")
        about_action.triggered.connect(QApplication.aboutQt)

        lr_group = QActionGroup(self.menuBar())
        lr_group.setExclusive(True)

        left_action = QAction("Left", self.menuBar())
        left_action.setChecked(False)
        left_action.setCheckable(True)
        left_action.setActionGroup(lr_group)

        right_action = QAction("Right", self.menuBar())
        right_action.setCheckable(True)
        right_action.setChecked(True)
        right_action.setActionGroup(lr_group)

        help_menu.addAction(left_action)
        help_menu.addAction(right_action)
        help_menu.addSection("Testsection")
        help_menu.addAction(about_action)

        file_menu.addAction(self.toolBar.exportAction)
        file_menu.addAction(self.toolBar.importAction)

        file_menu.addAction(exit_action)

        self._centralWidget = QSplitter(self)
        self._centralWidget.setOrientation(Qt.Horizontal)
        self._centralWidget.addWidget(self.dataAccessWidget)
        self._centralWidget.addWidget(self.graphicsArea)
        self.setCentralWidget(self._centralWidget)
        self.setStatusBar(self._statusBar)

        # Setup connections
        self.draw_button.clicked.connect(self.draw_clicked)
        self.stream_button.clicked.connect(self.stream_clicked)
        self.streamerCfgWidget.streamStarted.connect(self.do_stream)
        self.dataRangeSelector.cancelRefresh.connect(self.stop_auto_refresh)
        self.resize(1280, 720)

    def wireConnections(self):
        super().wireConnections()
        self.toolBar.exportAction.triggered.connect(self.onExport)
        self.toolBar.importAction.triggered.connect(self.onImport)

    def undo(self):
        return super().undo()

    def redo(self):
        return super().redo()

    def reDraw(self):
        self.draw_clicked()
        return super().reDraw()
    
    def detach(self):
        if self.toolBar.detachAction.text() == 'Detach':
            # we detach now.
            self._floatingWindow.setCentralWidget(self.graphicsArea)
            self._floatingWindow.setWindowTitle(self.windowTitle())
            self._floatingWindow.show()
            self.toolBar.detachAction.setText('Reattach')
        elif self.toolBar.detachAction.text() == 'Reattach':
            # we attach now.
            self.toolBar.detachAction.setText('Detach')
            self._centralWidget.addWidget(self.graphicsArea)
            self.setCentralWidget(self._centralWidget)
            self._floatingWindow.hide()

    def onExport(self):
        file = QFileDialog.getSaveFileName(self, "Save workspaces as ..")
        if file and file[0]:
            self.exportWorkspace(file[0])

    def onImport(self):
        file = QFileDialog.getOpenFileName(self, "Open a workspace ..")
        if file and file[0]:
            self.importWorkspace(file[0])

    # TODO: Implement this.
    def importWorkspace(self, file_path: os.PathLike):
        workspace = {}
        try:
            raise NotImplementedError("Not implemented")
            with open(file_path) as f:
                workspace.update(json.loads(f.read()))
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(f"Error {str(e)}: saving workspace to file: {file_path}")
            logger.exception(e)
            box.exec_()
            return

        # 1. import signals table.
        # 2. import canvas -> plots -> (axes, signals)
        # 3. import data range selector.
        # 3. finalize context
        pass

    # TODO: Implement this.
    def exportWorkspace(self, file_path: os.PathLike):
        workspace = {}
        try:
            raise NotImplementedError("Not implemented")
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(f"Error {str(e)}: loading workspace from file: {file_path}")
            logger.exception(e)
            box.exec_()
            return

        # 1. export signals table.
        # 2. export canvas -> plots -> (axes, signals)
        # 3. export data range selector.
        pass

    def start_auto_refresh(self):
        if self.canvas.auto_refresh:
            logger.info(
                F"Scheduling canvas refresh in {self.canvas.auto_refresh} seconds")
            self.refreshTimer = Timer(
                self.canvas.auto_refresh, self.draw_clicked)
            self.refreshTimer.daemon = True
            self.refreshTimer.start()
            self.dataRangeSelector.refreshActivate.emit()

    def stop_auto_refresh(self):
        self.dataRangeSelector.refreshDeactivate.emit()
        if self.refreshTimer is not None:
            self.refreshTimer.cancel()

    def draw_clicked(self):
        """This function creates and draws the canvas getting data from variables table and time/pulse widget"""

        self.build_layout()

        dump_dir = os.path.expanduser("~/.local/1Dtool/dumps/")
        Path(dump_dir).mkdir(parents=True, exist_ok=True)
        self.sigTable.exportCsv(os.path.join(
            dump_dir, "sigTable_" + str(os.getpid()) + ".csv"))

        self.stop_auto_refresh()

        self.canvasStack.currentWidget().unfocus_plot()
        self.canvasStack.currentWidget().set_canvas(self.canvas)
        self.canvasStack.refreshLinks()

        self.start_auto_refresh()

    def stream_clicked(self):
        """This function shows the streaming dialog and then creates a canvas that is used when streaming"""
        if not self.streamerCfgWidget.isActivated():
            self.streamerCfgWidget.activate()
            self.stream_button.setText("Stop")
        else:
            self.streamerCfgWidget.deActivate()
            self.stream_button.setText("Stream")

    def stream_callback(self, signal):
        self.canvasStack.currentWidget().matplotlib_canvas.refresh_signal(signal)

    def do_stream(self):
        self.streamerCfgWidget.hide()
        self.build_layout(stream=True)

        self.canvasStack.currentWidget().unfocus_plot()
        self.canvasStack.currentWidget().set_canvas(self.canvas)

        self.streamerCfgWidget.streamer = CanvasStreamer(self.da)
        self.streamerCfgWidget.streamer.start(
            self.canvas, self.stream_callback)
        self.stream_button.setText("Stop")

    def closeEvent(self, event: QCloseEvent) -> None:
        QApplication.closeAllWindows()
        super().closeEvent(event)

    def build_layout_plan(self, plan: dict, descrp: SignalDescription) -> None:
        if not (descrp.signals and descrp.stack_num and descrp.col_num and descrp.row_num):
            return
        if descrp.col_num not in plan:
            plan[descrp.col_num] = {}
        if descrp.row_num not in plan[descrp.col_num]:
            plan[descrp.col_num][descrp.row_num] = [descrp.row_span,
                                                    descrp.col_span, {}, [descrp.start_ts, descrp.end_ts]]
        else:
            existing = plan[descrp.col_num][descrp.row_num]
            existing[0] = descrp.row_span if descrp.row_span > existing[0] else existing[0]
            existing[1] = descrp.col_span if descrp.col_span > existing[1] else existing[1]

            if descrp.start_ts is not None or descrp.start_ts is not None:
                if existing[3][0] is None or descrp.start_ts < existing[3][0]:
                    existing[3][0] = descrp.start_ts
                if existing[3][1] is None or descrp.end_ts > existing[3][1]:
                    existing[3][1] = descrp.end_ts

        if descrp.stack_num not in plan[descrp.col_num][descrp.row_num][2]:
            plan[descrp.col_num][descrp.row_num][2][descrp.stack_num] = []
        for signal in descrp.signals:
            plan[descrp.col_num][descrp.row_num][2][descrp.stack_num].append(
                signal)

    def build_layout(self, stream=False):

        self.canvas.streaming = stream
        stream_window = self.streamerCfgWidget.timeWindow()

        x_axis_date = self.dataRangeSelector.isXAxisDate() and not stream
        x_axis_follow = stream
        x_axis_window = stream_window if stream else None
        refresh_interval = 0 if stream else self.dataRangeSelector.getAutoRefresh()
        pulse_number = None if stream else self.dataRangeSelector.getPulseNumber()

        if stream and stream_window > 0:
            now = self.dataRangeSelector.getTimeNow()
            ts, te = now, now - stream_window
        else:
            ts, te = self.dataRangeSelector.getTimeRange()

        params = dict(dec_samples=self.default_dec_samples,
                      ts_start=ts, ts_end=te, pulse_nb=pulse_number)
        logger.info(
            f"Creating canvas {params}, stream={stream}, stream_window={stream_window}")

        self.context.reset()
        layout_plan = {}
        signal_descr_handler = partial(self.build_layout_plan, layout_plan)
        self.context.import_dataframe(self.sigTable.getModel().get_dataframe(
        ), signal_class=DataAccessSignal, assort_signals=signal_descr_handler, **params)
        self.context.build()

        logger.info("Built context")
        logger.debug(f"{self.context.env}")

        if stream:
            self.canvas.auto_refresh = refresh_interval
            self.canvas.autoscale = Canvas.autoscale
        else:
            self.canvas.auto_refresh = Canvas.auto_refresh
            self.canvas.autoscale = x_axis_date

        logger.debug(f"Layout plan: {layout_plan}")

        if layout_plan.keys():
            self.canvas.cols = max(layout_plan.keys())
            self.canvas.rows = max([max(e.keys())
                                   for e in layout_plan.values()])
            self.canvas.plots = [[] for _ in range(self.canvas.cols)]

            for colnum, rows in layout_plan.items():
                for row in range(max(rows.keys())):
                    plot = None
                    if row + 1 in rows.keys():
                        y_axes = [LinearAxis()
                                  for _ in range(len(rows[row + 1][2].items()))]

                        x_axis = LinearAxis(
                            is_date=x_axis_date, follow=x_axis_follow, window=x_axis_window)

                        if x_axis_date and rows[row+1][3][0] is not None and rows[row+1][3][1] is not None:
                            x_axis.begin = rows[row+1][3][0]
                            x_axis.end = rows[row+1][3][1]
                            x_axis.original_begin = x_axis.begin
                            x_axis.original_end = x_axis.end

                        plot = self.plot_class(axes=[x_axis, y_axes], row_span=rows[row + 1][0],
                                               col_span=rows[row + 1][1])
                        for stack, signals in rows[row + 1][2].items():
                            for signal in signals:
                                plot.add_signal(signal, stack=stack)
                    self.canvas.add_plot(plot, col=colnum - 1)

        logger.info("Built canvas")
        logger.debug(f"{self.canvas}")
