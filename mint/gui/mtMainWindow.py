import os
from functools import partial
from pathlib import Path
from threading import Timer
from iplotProcessing.core.context import SignalDescription

from iplotlib.core.axis import LinearAxis
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.data_access import DataAccessSignal
from iplotlib.data_access import CanvasStreamer
from iplotlib.qt.qtCanvasToolbar import CanvasToolbar
from iplotDataAccess.dataAccess import DataAccess
from iplotLogging import setupLogger as sl
from iplotProcessing.core import Context
from iplotProcessing.core.environment import DEFAULT_BLUEPRINT_FILE

from mint.gui.mtDataRangeSelector import MTDataRangeSelector
from mint.gui.mtMenuBar import MTMenuBar
from mint.gui.mtStatusBar import MTStatusBar
from mint.gui.mtStreamConfigurator import MTStreamConfigurator
from mint.gui.mtSignalTable import MTSignalTable
from mint.tools.sanity_checks import check_data_range

from qtpy import QtCore, QtGui, QtWidgets


logger = sl.get_logger(__name__, "INFO")


class MTMainWindow(QtWidgets.QMainWindow):

    def __init__(self, 
        canvas: Canvas, 
        context: Context, 
        da: DataAccess, 
        model: dict, 
        blueprint: os.PathLike=DEFAULT_BLUEPRINT_FILE, 
        impl: str = "matplotlib", 
        parent=None, 
        **kwargs):
        super().__init__(parent, **kwargs)

        self.canvas = canvas
        self.context = context
        self.da = da
        self.plot_class = PlotXY

        self.default_dec_samples = 1000

        check_data_range(model)

        self.model = model
        self.refreshTimer = None

        self.streamerCfgWidget = MTStreamConfigurator(self)

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

        self.variables_table = MTSignalTable(blueprint=blueprint, parent=self)
        self.range_selector = MTDataRangeSelector(self.model.get("range"), parent=self)

        self.draw_button = QtWidgets.QPushButton("Draw")
        self.draw_button.setIcon(
            QtGui.QIcon(os.path.join(os.path.dirname(__file__), "gui/icons/plot.png")))
        self.streamButton = QtWidgets.QPushButton("Stream")
        self.streamButton.setIcon(
            QtGui.QIcon(os.path.join(os.path.dirname(__file__), "gui/icons/plot.png")))

        self.left_column_buttons = QtWidgets.QWidget()
        self.left_column_buttons.setLayout(QtWidgets.QHBoxLayout())
        self.left_column_buttons.layout().setContentsMargins(QtCore.QMargins())
        self.left_column_buttons.layout().addWidget(self.streamButton)
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

        self.status_bar = MTStatusBar(parent=self)

        self.menu_bar = MTMenuBar(export_widgets=dict(
            variables_table=self.variables_table,
            main_canvas=self.qt_canvas,
            time_model=self.range_selector))

        self.setCentralWidget(self.central_widget)
        self.setMenuBar(self.menu_bar)
        self.setStatusBar(self.status_bar)

        # Setup connections
        self.draw_button.clicked.connect(self.draw_clicked)
        self.streamButton.clicked.connect(self.stream_clicked)
        self.streamerCfgWidget.streamStarted.connect(self.do_stream)
        self.range_selector.cancelRefresh.connect(self.stop_auto_refresh)

    def start_auto_refresh(self):
        if self.canvas.auto_refresh:
            logger.info(
                F"Scheduling canvas refresh in {self.canvas.auto_refresh} seconds")
            self.refreshTimer = Timer(
                self.canvas.auto_refresh, self.draw_clicked)
            self.refreshTimer.daemon = True
            self.refreshTimer.start()
            self.range_selector.refreshActivate.emit()

    def stop_auto_refresh(self):
        self.range_selector.refreshDeactivate.emit()
        if self.refreshTimer is not None:
            self.refreshTimer.cancel()

    def draw_clicked(self):
        """This function creates and draws the canvas getting data from variables table and time/pulse widget"""

        self.build_layout()

        dump_dir = os.path.expanduser("~/.local/1Dtool/dumps/")
        Path(dump_dir).mkdir(parents=True, exist_ok=True)
        self.variables_table.exportCsv(os.path.join(
            dump_dir, "variables_table_" + str(os.getpid()) + ".csv"))

        self.stop_auto_refresh()

        self.qt_canvas.unfocus_plot()
        self.qt_canvas.set_canvas(self.canvas)

        self.start_auto_refresh()

    def stream_clicked(self):
        """This function shows the streaming dialog and then creates a canvas that is used when streaming"""
        if not self.streamerCfgWidget.isActivated():
            self.streamerCfgWidget.activate()
            self.streamButton.setText("Stop")
        else:
            self.streamerCfgWidget.deActivate()
            self.streamButton.setText("Stream")

    def stream_callback(self, signal):
        self.qt_canvas.matplotlib_canvas.refresh_signal(signal)

    def do_stream(self):
        self.streamerCfgWidget.hide()
        self.build_layout(stream=True)

        self.qt_canvas.unfocus_plot()
        self.qt_canvas.set_canvas(self.canvas)

        self.streamerCfgWidget.streamer = CanvasStreamer(self.da)
        self.streamerCfgWidget.streamer.start(self.canvas, self.stream_callback)
        self.streamButton.setText("Stop")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        QtWidgets.QApplication.closeAllWindows()
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

        x_axis_date = self.range_selector.isXAxisDate() and not stream
        x_axis_follow = stream
        x_axis_window = stream_window if stream else None
        refresh_interval = 0 if stream else self.range_selector.getAutoRefresh()
        pulse_number = None if stream else self.range_selector.getPulseNumber()

        if stream and stream_window > 0:
            now = self.range_selector.getTimeNow()
            ts, te = now, now - stream_window
        else:
            ts, te = self.range_selector.getTimeRange()

        params = dict(dec_samples=self.default_dec_samples, ts_start=ts, ts_end=te, pulse_nb=pulse_number)
        logger.info(f"Creating canvas {params}, stream={stream}, stream_window={stream_window}")

        self.context.reset()
        layout_plan = {}
        signal_descr_handler = partial(self.build_layout_plan, layout_plan)
        self.context.import_dataframe(self.variables_table.getModel().get_dataframe(), signal_class=DataAccessSignal, assort_signals=signal_descr_handler, **params)
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
            self.canvas.rows = max([max(e.keys()) for e in layout_plan.values()])
            self.canvas.plots = [[] for _ in range(self.canvas.cols)]

            for colnum, rows in layout_plan.items():
                for row in range(max(rows.keys())):
                    plot = None
                    if row + 1 in rows.keys():
                        y_axes = [LinearAxis()
                                  for _ in range(len(rows[row + 1][2].items()))]

                        x_axis = LinearAxis(is_date=x_axis_date, follow=x_axis_follow, window=x_axis_window)

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
