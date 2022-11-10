# Description: A main window embedding a table of signals' description on the right
#               and a Qt iplotlib canvas on the left.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from collections import defaultdict
from dataclasses import fields
import json
from pathlib import Path
import os
import pkgutil
import typing

from PySide6.QtCore import QCoreApplication, QMargins, QModelIndex, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QPixmap, QAction
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QSplitter, QVBoxLayout, QWidget

from iplotlib.core.axis import LinearAxis
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY, Plot
from iplotlib.interface import IplotSignalAdapter
from iplotlib.data_access import CanvasStreamer
from iplotlib.interface.iplotSignalAdapter import ParserHelper
from iplotlib.qt.gui.iplotQtMainWindow import IplotQtMainWindow


from iplotDataAccess.dataAccess import DataAccess
from mint.gui.mtAbout import MTAbout

from mint.gui.mtDataRangeSelector import MTDataRangeSelector
from mint.gui.mtMemoryMonitor import MTMemoryMonitor
from mint.gui.mtStatusBar import MTStatusBar
from mint.gui.mtStreamConfigurator import MTStreamConfigurator
from mint.gui.mtSignalConfigurator import MTSignalConfigurator
from mint.models.utils import mtBlueprintParser as mtbp
from mint.tools.map_tricks import delete_keys_from_dict
from mint.tools.sanity_checks import check_data_range


from iplotLogging import setupLogger as sl
logger = sl.get_logger(__name__, "INFO")


class MTMainWindow(IplotQtMainWindow):

    def __init__(self,
                 canvas: Canvas,
                 da: DataAccess,
                 model: dict,
                 data_dir: os.PathLike = '.',
                 data_sources: list = [],
                 blueprint: dict = mtbp.DEFAULT_BLUEPRINT,
                 impl: str = "matplotlib",
                 signal_class: type = IplotSignalAdapter,
                 parent: typing.Optional[QWidget] = None,
                 flags: Qt.WindowFlags = Qt.WindowFlags()):

        self.canvas = canvas
        self.da = da
        self.plot_class = PlotXY
        self.signal_class = signal_class
        try:
            blueprint['DataSource']['default'] = data_sources[0]
        except IndexError:
            pass
        except KeyError:
            logger.error('Blueprint does not have a DataSource key!')
            QCoreApplication.exit(-1)

        check_data_range(model)
        self.model = model
        self.sigCfgWidget = MTSignalConfigurator(
            blueprint=blueprint, csv_dir=os.path.join(data_dir, 'csv'), data_sources=data_sources)
        self.dataRangeSelector = MTDataRangeSelector(self.model.get("range"),)

        self._data_dir = os.path.join(data_dir, 'workspaces')
        self._progressBar = QProgressBar()
        self._statusBar = MTStatusBar()

        super().__init__(parent=parent, flags=flags)

        self.refreshTimer = QTimer(self)
        self.refreshTimer.setTimerType(Qt.CoarseTimer)
        self.refreshTimer.setSingleShot(False)
        self.refreshTimer.timeout.connect(lambda: self.canvasStack.currentWidget().refresh())
        self._memoryMonitor = MTMemoryMonitor(
            parent=self, pid=QCoreApplication.instance().applicationPid())
        self.sigCfgWidget.setParent(self)
        self.dataRangeSelector.setParent(self)
        self._statusBar.setParent(self)
        self._progressBar.setParent(self)
        self._progressBar.setMinimum(0)
        self._progressBar.setMaximum(100)
        self._progressBar.hide()
        self._statusBar.addPermanentWidget(self._progressBar)
        self._statusBar.addPermanentWidget(QLabel('|'))
        self._statusBar.addPermanentWidget(self._memoryMonitor)
        self._statusBar.addPermanentWidget(QLabel('|'))

        self.graphicsArea = QWidget(self)
        self.graphicsArea.setLayout(QVBoxLayout())
        self.graphicsArea.layout().addWidget(self.toolBar)
        self.graphicsArea.layout().addWidget(self.canvasStack)
        self.streamerCfgWidget = MTStreamConfigurator(self)
        self.aboutMINT = MTAbout(self)

        if impl.lower() == "matplotlib":
            from iplotlib.impl.matplotlib.qt.qtMatplotlibCanvas import QtMatplotlibCanvas
            self.canvasStack.addWidget(QtMatplotlibCanvas(
                tight_layout=True, canvas=self.canvas, parent=self.canvasStack))
        elif impl.lower() == "vtk":
            from iplotlib.impl.vtk.qt import QtVTKCanvas
            self.canvasStack.addWidget(QtVTKCanvas(
                canvas=self.canvas, parent=self.canvasStack))

        file_menu = self.menuBar().addMenu("&File")
        help_menu = self.menuBar().addMenu("&Help")

        exit_action = QAction("Exit", self.menuBar())
        exit_action.setShortcuts(QKeySequence.Quit)
        exit_action.triggered.connect(QApplication.closeAllWindows)

        about_qt_action = QAction("About Qt", self.menuBar())
        about_qt_action.setStatusTip("About Qt")
        about_qt_action.triggered.connect(QApplication.aboutQt)

        about_action = QAction("About MINT", self.menuBar())
        about_action.setStatusTip("About MINT")
        about_action.triggered.connect(self.aboutMINT.exec_)

        help_menu.addAction(about_action)
        help_menu.addAction(about_qt_action)

        file_menu.addAction(self.sigCfgWidget.toolBar().openAction)
        file_menu.addAction(self.sigCfgWidget.toolBar().saveAction)
        file_menu.addAction(self.toolBar.importAction)
        file_menu.addAction(self.toolBar.exportAction)
        file_menu.addAction(exit_action)

        self.drawBtn = QPushButton("Draw")
        pxmap = QPixmap()
        pxmap.loadFromData(pkgutil.get_data('mint.gui', 'icons/plot.png'))
        self.drawBtn.setIcon(QIcon(pxmap))
        self.streamBtn = QPushButton("Stream")
        self.streamBtn.setIcon(QIcon(pxmap))

        self.daWidgetButtons = QWidget(self)
        self.daWidgetButtons.setLayout(QHBoxLayout())
        self.daWidgetButtons.layout().setContentsMargins(QMargins())
        self.daWidgetButtons.layout().addWidget(self.streamBtn)
        self.daWidgetButtons.layout().addWidget(self.drawBtn)

        self.dataAccessWidget = QWidget(self)
        self.dataAccessWidget.setLayout(QVBoxLayout())
        self.dataAccessWidget.layout().setContentsMargins(QMargins())
        self.dataAccessWidget.layout().addWidget(self.dataRangeSelector)
        self.dataAccessWidget.layout().addWidget(self.sigCfgWidget)
        self.dataAccessWidget.layout().addWidget(self.daWidgetButtons)

        self._centralWidget = QSplitter(self)
        self._centralWidget.setOrientation(Qt.Horizontal)
        self._centralWidget.addWidget(self.dataAccessWidget)
        self._centralWidget.addWidget(self.graphicsArea)
        self.setCentralWidget(self._centralWidget)
        self.setStatusBar(self._statusBar)

        # Setup connections
        self.drawBtn.clicked.connect(self.drawClicked)
        self.streamBtn.clicked.connect(self.streamClicked)
        self.streamerCfgWidget.streamStarted.connect(self.onStreamStarted)
        self.streamerCfgWidget.streamStopped.connect(self.onStreamStopped)
        self.dataRangeSelector.cancelRefresh.connect(self.stopAutoRefresh)
        self.resize(1920, 1080)

    def wireConnections(self):
        super().wireConnections()
        self.sigCfgWidget.statusChanged.connect(self._statusBar.showMessage)
        self.sigCfgWidget.buildAborted.connect(self.onTableAbort)
        self.sigCfgWidget.showProgress.connect(self._progressBar.show)
        self.sigCfgWidget.hideProgress.connect(self._progressBar.hide)
        self.sigCfgWidget.busy.connect(self.indicateBusy)
        self.sigCfgWidget.ready.connect(self.indicateReady)
        self.sigCfgWidget.progressChanged.connect(self._progressBar.setValue)
        self.toolBar.exportAction.triggered.connect(self.onExport)
        self.toolBar.importAction.triggered.connect(self.onImport)

    def onTableAbort(self, message):
        logger.error(message)

        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Table Build Failed")
        box.setText(message)
        box.exec_()

    def detach(self):
        if self.toolBar.detachAction.text() == 'Detach':
            # we detach now.
            self._floatingWindow.addToolBar(Qt.TopToolBarArea, self.toolBar)
            self.graphicsArea.setLayout(QVBoxLayout())
            self.graphicsArea.layout().addWidget(self.canvasStack)
            self._floatingWindow.setCentralWidget(self.graphicsArea)
            self._floatingWindow.setWindowTitle(self.windowTitle())
            self._floatingWindow.show()
            self.toolBar.detachAction.setText('Reattach')
            self.sigCfgWidget.resizeViewsToContents()
        elif self.toolBar.detachAction.text() == 'Reattach':
            # we attach now.
            self.toolBar.detachAction.setText('Detach')
            self.graphicsArea.setLayout(QVBoxLayout())
            self.graphicsArea.layout().addWidget(self.toolBar)
            self.graphicsArea.layout().addWidget(self.canvasStack)
            self._centralWidget.addWidget(self.graphicsArea)
            self.setCentralWidget(self._centralWidget)
            self._floatingWindow.hide()

    def updateCanvasPreferences(self):
        self.indicateBusy()
        super().updateCanvasPreferences()
        self.indicateReady()

    def reDraw(self):
        self.indicateBusy()
        super().reDraw()
        self.indicateReady()

    def onExport(self):
        file = QFileDialog.getSaveFileName(
            self, "Save workspaces as ..", dir=self._data_dir, filter='*.json')
        if file and file[0]:
            if not file[0].endswith('.json'):
                file_name = file[0] + '.json'
            else:
                file_name = file[0]
            self.export_json(file_name)
            self._data_dir = os.path.dirname(file_name)

    def onImport(self):
        file = QFileDialog.getOpenFileName(
            self, "Open a workspace ..", dir=os.path.join(self._data_dir, 'workspaces'))
        if file and file[0]:
            self._data_dir = os.path.dirname(file[0])
            self.import_json(file[0])

    def indicateBusy(self):
        self._progressBar.setMinimum(0)
        self._progressBar.setMaximum(0)
        self._progressBar.show()
        self.statusBar().showMessage('Hang on ..')
        QCoreApplication.processEvents()

    def indicateReady(self):
        self._progressBar.hide()
        self._progressBar.setMinimum(0)
        self._progressBar.setMaximum(100)
        self.statusBar().showMessage('Ready.')
        QCoreApplication.processEvents()

    def export_dict(self) -> dict:
        self.indicateBusy()
        workspace = {}
        workspace.update({'data_range': self.dataRangeSelector.export_dict()})
        workspace.update({'signal_cfg': self.sigCfgWidget.export_dict()})
        workspace.update(
            {'main_canvas': self.canvasStack.currentWidget().export_dict()})
        self.indicateReady()
        return workspace

    def import_dict(self, input_dict: dict):
        self.indicateBusy()
        data_range = input_dict.get('data_range')
        self.dataRangeSelector.import_dict(data_range)

        delete_keys_from_dict(input_dict, ['dec_samples'])
        main_canvas = input_dict.get('main_canvas')
        self.canvas = Canvas.from_dict(main_canvas)

        ts, te = self.dataRangeSelector.getTimeRange()
        pulse_number = self.dataRangeSelector.getPulseNumber()
        da_params = dict(ts_start=ts, ts_end=te, pulse_nb=pulse_number)

        signal_cfg = input_dict.get('signal_cfg') or input_dict
        if signal_cfg:
            self.sigCfgWidget.import_dict(signal_cfg)

        path = list(self.sigCfgWidget.build(**da_params))
        path_len = len(path)
        ParserHelper.env.clear()  # Removes any previously aliased signals.
        self.indicateReady()
        self.sigCfgWidget.setStatusMessage("Update signals ..")
        self.sigCfgWidget.beginBuild()
        self.sigCfgWidget.setProgress(0)
        
        # Travel the path and update each signal parameters from workspace and trigger a data access request.
        for i, waypt in enumerate(path):
            self.sigCfgWidget.setStatusMessage(f"Updating {waypt} ..")
            self.sigCfgWidget.setProgress(i * 100 / path_len)

            if (not waypt.stack_num) or (not waypt.col_num and not waypt.row_num):
                signal = waypt.func(*waypt.args, **waypt.kwargs)
                self.sigCfgWidget.model.update_signal_data(
                    waypt.idx, signal, True)
                continue

            plot = self.canvas.plots[waypt.col_num -
                                    1][waypt.row_num - 1]  # type: Plot
            old_signal = plot.signals[str(
                waypt.stack_num)][waypt.signal_stack_id]

            params = dict()
            for f in fields(old_signal):
                if f.name == 'children':  # Don't copy children.
                    continue
                else:
                    params.update({f.name: getattr(old_signal, f.name)})
            new_signal = waypt.func(
                *waypt.args, signal_class=waypt.kwargs.get('signal_class'), **params)

            self.sigCfgWidget.model.update_signal_data(
                waypt.idx, new_signal, True)

            # Replace signal.
            plot.signals[str(waypt.stack_num)
                        ][waypt.signal_stack_id] = new_signal

        self.sigCfgWidget.setProgress(100)

        self.indicateBusy()
        self.canvasStack.currentWidget().set_canvas(self.canvas)
        self.canvasStack.refreshLinks()
        self.sigCfgWidget.model.dataChanged.emit(self.sigCfgWidget.model.index(0, 0), 
            self.sigCfgWidget.model.index(self.sigCfgWidget.model.rowCount(QModelIndex()) - 1, self.sigCfgWidget.model.columnCount(QModelIndex()) - 1))
        self.indicateReady()
        self.sigCfgWidget.resizeViewsToContents()

    def import_json(self, file_path: os.PathLike):
        self.statusBar().showMessage(f"Importing {file_path} ..")
        try:
            with open(file_path, mode='r') as f:
                payload = f.read()
                payload = payload.replace("data_access.dataAccessSignal.DataAccessSignal",
                                          "interface.iplotSignalAdapter.IplotSignalAdapter")
                replacements = {'varname': 'name',
                                'datasource': 'data_source',
                                'pulsenb': 'pulse_nb',
                                'time_model': 'data_range'
                                }
                for f, r in replacements.items():
                    payload = payload.replace(f, r)
                self.import_dict(json.loads(payload))
                logger.info(f"Finished loading workspace {file_path}")
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(
                f"Error {str(e)}: cannot import workspace from file: {file_path}")
            logger.exception(e)
            box.exec_()
            self.indicateReady()
            return

    def export_json(self, file_path: os.PathLike):
        self.statusBar().showMessage(f"Exporting {file_path} ..")
        try:
            with open(file_path, mode='w') as f:
                f.write(json.dumps(self.export_dict()))
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(
                f"Error {str(e)}: cannot export workspace to file: {file_path}")
            logger.exception(e)
            box.exec_()
            self.indicateReady()
            return

    def startAutoRefresh(self):
        if self.canvas.auto_refresh:
            logger.info(
                F"Scheduling canvas refresh in {self.canvas.auto_refresh} seconds")
            self.refreshTimer.start(self.canvas.auto_refresh * 1000)
            self.dataRangeSelector.refreshActivate.emit()

    def stopAutoRefresh(self):
        self.dataRangeSelector.refreshDeactivate.emit()
        if self.refreshTimer is not None:
            self.refreshTimer.stop()

    def drawClicked(self, no_build: bool = False):
        """This function creates and draws the canvas getting data from variables table and time/pulse widget"""

        if not no_build:
            self.build()
            dump_dir = os.path.expanduser("~/.local/1Dtool/dumps/")
            Path(dump_dir).mkdir(parents=True, exist_ok=True)
            self.sigCfgWidget.export_csv(os.path.join(
                dump_dir, "signals_table" + str(os.getpid()) + ".csv"))

        self.indicateBusy()
        self.stopAutoRefresh()

        self.canvasStack.currentWidget().unfocus_plot()
        self.canvasStack.currentWidget().set_canvas(self.canvas)
        self.canvasStack.refreshLinks()
        self.prefWindow.formsStack.currentWidget().widgetMapper.revert()
        self.prefWindow.update()

        self.drop_history()      # clean zoom history; is this best place?
        self.startAutoRefresh()
        self.indicateReady()

    def streamClicked(self, no_build: bool = False):
        """This function shows the streaming dialog and then creates a canvas that is used when streaming"""
        if self.streamerCfgWidget.isActivated():
            self.streamBtn.setText("Stopping")
            self.streamerCfgWidget.stop()
        else:
            self.streamerCfgWidget.show()

    def streamCallback(self, signal):
        self.canvasStack.currentWidget()._parser.process_ipl_signal(signal)

    def onStreamStarted(self):
        self.streamerCfgWidget.hide()
        self.streamBtn.setText("Stop")
        self.build(stream=True)

        self.indicateBusy()
        self.canvasStack.currentWidget().unfocus_plot()
        self.canvasStack.currentWidget().set_canvas(self.canvas)
        self.canvasStack.refreshLinks()

        self.streamerCfgWidget.streamer = CanvasStreamer(self.da)
        self.streamerCfgWidget.streamer.start(
            self.canvas, self.streamCallback)
        self.indicateReady()
    
    def onStreamStopped(self):
        self.streamBtn.setText("Stream")

    def closeEvent(self, event: QCloseEvent) -> None:
        QApplication.closeAllWindows()
        super().closeEvent(event)

    def build(self, stream=False):

        self.canvas.streaming = stream
        stream_window = self.streamerCfgWidget.timeWindow() * 1000000000

        x_axis_date = (self.dataRangeSelector.isXAxisDate() and not stream) or stream
        x_axis_follow = stream
        x_axis_window = stream_window if stream else None
        refresh_interval = 0 if stream else self.dataRangeSelector.getAutoRefresh()
        pulse_number = None if stream else self.dataRangeSelector.getPulseNumber()

        if stream and stream_window > 0:
            now = self.dataRangeSelector.getTimeNow()
            ts, te = now - stream_window, now
        else:
            ts, te = self.dataRangeSelector.getTimeRange()

        self.canvas.auto_refresh = refresh_interval
        if stream:
            self.canvas.autoscale = Canvas.autoscale
        else:
            self.canvas.autoscale = x_axis_date

        da_params = dict(ts_start=ts, ts_end=te, pulse_nb=pulse_number)
        plan = dict()

        for waypt in self.sigCfgWidget.build(**da_params):

            if not waypt.func and not waypt.args:
                continue
            if (not waypt.stack_num) or (not waypt.col_num and not waypt.row_num):
                signal = waypt.func(*waypt.args, **waypt.kwargs)
                if not stream:
                    self.sigCfgWidget.model.update_signal_data(
                        waypt.idx, signal, True)
                continue

            if waypt.col_num not in plan:
                plan[waypt.col_num] = {}

            if waypt.row_num not in plan[waypt.col_num]:
                plan[waypt.col_num][waypt.row_num] = [waypt.row_span,
                                                    waypt.col_span,
                                                    defaultdict(list),
                                                    [waypt.ts_start, waypt.ts_end]]

            else:
                existing = plan[waypt.col_num][waypt.row_num]
                existing[0] = waypt.row_span if waypt.row_span > existing[0] else existing[0]
                existing[1] = waypt.col_span if waypt.col_span > existing[1] else existing[1]

                if waypt.ts_start is not None or waypt.ts_start is not None:
                    if existing[3][0] is None or waypt.ts_start < existing[3][0]:
                        existing[3][0] = waypt.ts_start
                    if existing[3][1] is None or waypt.ts_end > existing[3][1]:
                        existing[3][1] = waypt.ts_end

            signal = waypt.func(*waypt.args, **waypt.kwargs)
            signal.data_access_enabled = False if self.canvas.streaming else True
            signal.hi_precision_data = True if self.canvas.streaming else False
            if not stream:
                self.sigCfgWidget.model.update_signal_data(waypt.idx, signal, True)
            plan[waypt.col_num][waypt.row_num][2][waypt.stack_num].append(
                signal)

        self.indicateBusy()
        self.build_canvas(self.canvas, plan, x_axis_date,
                          x_axis_follow, x_axis_window)
        logger.info("Built canvas")
        logger.debug(f"{self.canvas}")
        self.sigCfgWidget.model.dataChanged.emit(self.sigCfgWidget.model.index(0, 0), 
            self.sigCfgWidget.model.index(self.sigCfgWidget.model.rowCount(QModelIndex()) - 1, self.sigCfgWidget.model.columnCount(QModelIndex()) - 1))
        self.indicateReady()

    def build_canvas(self, canvas: Canvas, plan: dict, x_axis_date=False, x_axis_follow=False, x_axis_window=False):
        if not plan.keys():
            return

        canvas.cols = max(plan.keys())
        canvas.rows = max([max(e.keys())
                           for e in plan.values()])
        canvas.plots = [[] for _ in range(canvas.cols)]

        for colnum, rows in plan.items():
            for row in range(max(rows.keys())):
                plot = None
                if row + 1 in rows.keys():
                    if not canvas.streaming:
                        signal_x_is_date = False
                        for stack, signals in rows[row + 1][2].items():
                            for signal in signals:
                                try:
                                    x_data = signal.get_data()[0]
                                    signal_x_is_date |= bool(max(x_data) > (1 << 53))
                                except (IndexError, ValueError) as _:
                                    signal_x_is_date = True
                    else:
                        signal_x_is_date = True

                    y_axes = [LinearAxis()
                              for _ in range(len(rows[row + 1][2].items()))]

                    x_axis = LinearAxis(
                        is_date=x_axis_date and signal_x_is_date, follow=x_axis_follow, window=x_axis_window)

                    if x_axis_date and signal_x_is_date and rows[row+1][3][0] is not None and rows[row+1][3][1] is not None:
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
