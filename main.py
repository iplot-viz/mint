import os
import sys
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from threading import Timer

from gui._version import __version__
from iplotlib.core._version import __version__ as __iplotlib_version__

import pandas
from PyQt5.QtCore import QMargins
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox, QSplitter, QStyle, QVBoxLayout, QWidget
from dataAccess.dataAccess import DataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.data_access.dataAccessSignal import AccessHelper
from iplotlib.qt.qtCanvasToolbar import CanvasToolbar

import logging2.setupLogger as ls

logger = ls.get_logger(__name__)

try:
    from iplotlib.impl.gnuplot.qt.qtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas
except ModuleNotFoundError:
    logger.error("import qt gnuplot not installed ")

from iplotlib.impl.matplotlib.qt.qtMatplotlibCanvas import QtMatplotlibCanvas
from iplotlib.data_access.streamer import CanvasStreamer

from gui.main import Multiwindow, MainMenu, StatusBar
from gui.variablesTable import VariablesTable, DataRangeSelector



if __name__ == '__main__':

    logger.info("Running version {} iplotlib version {}".format(__version__, __iplotlib_version__))
    da = DataAccess()

    AccessHelper.da = da

    # we load the data source conf files
    listDS = da.loadConfig()
    defDS = da.getDefaultDSName()
    if len(listDS) < 1:
        logger.error("no data sources found, exiting")
        sys.exit(-1)

    # da.udahost = os.environ.get('UDA_HOST') or "io-ls-udafe01.iter.org"
    canvasImpl = "MATPLOTLIB"
    if len(sys.argv) > 1:
        if sys.argv[1] == 'MATPLOTLIB' or sys.argv[1] == 'GNUPLOT':
            canvasImpl = sys.argv[1]

    file_to_import = None
    if len(sys.argv) > 2:
        file_to_import = sys.argv[2]

    currTime = datetime.utcnow().isoformat(timespec='seconds')
    currTimeDelta = datetime.utcnow() - timedelta(days=7)

    app = QApplication(sys.argv)

    header = {
        "DataSource": {"label": "DS"},
        "Variable": {},
        "Stack": {},
        "RowSpan": {"label": "Row span"},
        "ColSpan": {"label": "Col span"},
        "Envelope": {},
        "Alias": {},
        "DecSamples": {"label": "Samples"}
    }

    model = {
        # "range": {"mode": DataRangeSelector.TIME_RANGE, "value": [currTimeDelta.isoformat(timespec='seconds'), currTime]}
        "range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2020-10-19T20:17:40", "2020-10-19T20:27:40"]}
        # "range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2021-02-22T12:00:00", "2021-02-22T12:00:01"]}
        # "range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2018-09-13T15:22:35.100", "2018-09-13T15:22:35.101 "]}
        #"range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2021-02-22T12:01:53.790", "2021-02-25T12:01:54.800"]}

    }

    if file_to_import:
        model["table"] = pandas.read_csv(file_to_import, dtype=str, keep_default_na=False).values.tolist()

    # This is a main reference to canvas that is drawn
    canvas = Canvas(grid=True)
    streamer = None
    stream_window = 3600
    refresh_timer = None

    if canvasImpl == "MATPLOTLIB":
        right_column = QWidget()
        right_column.setLayout(QVBoxLayout())
        qt_canvas = QtMatplotlibCanvas(tight_layout=True)
        right_column.layout().addWidget(CanvasToolbar(qt_canvas=qt_canvas))
        right_column.layout().addWidget(qt_canvas)

    variables_table = VariablesTable(data_access=da, header=header, model=model.get("table"))
    range_selector = DataRangeSelector(model=model.get("range"))


    draw_button = QPushButton("Draw")
    draw_button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "gui/icons/plot.png")))
    stream_button = QPushButton("Stream")
    stream_button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "gui/icons/plot.png")))

    def start_auto_refresh(canvas):
        global refresh_timer
        global range_selector

        if canvas.auto_refresh:
            logger.info(F"Scheduling canvas refresh in {canvas.auto_refresh} seconds")
            refresh_timer = Timer(canvas.auto_refresh, draw_clicked)
            refresh_timer.daemon = True
            refresh_timer.start()
            range_selector.refresh_activate.emit()

    def stop_auto_refresh():
        global refresh_timer
        global range_selector

        range_selector.refresh_deactivate.emit()
        if refresh_timer is not None:
            refresh_timer.cancel()


    range_selector.cancel_refresh.connect(stop_auto_refresh)


    def draw_clicked():
        global refresh_timer
        """This function creates and draws the canvas getting data from variables table and time/pulse widget"""
        time_model = range_selector.get_model()
        new_canvas = variables_table.create_canvas(time_model)
        canvas.rows = new_canvas.rows
        canvas.cols = new_canvas.cols
        canvas.plots = new_canvas.plots
        canvas.auto_refresh = new_canvas.auto_refresh
        canvas.autoscale = new_canvas.autoscale
        canvas.streaming = False

        dump_dir = os.path.expanduser("~/.local/1Dtool/dumps/")
        Path(dump_dir).mkdir(parents=True, exist_ok=True)
        variables_table.export_csv(os.path.join(dump_dir, "variables_table_" + str(os.getpid()) + ".csv"))

        stop_auto_refresh()

        qt_canvas.set_canvas(canvas)

        start_auto_refresh(canvas)



    def stream_clicked():
        """This function shows the streaming dialog and then creates a canvas that is used when streaming"""
        global streamer

        window_field = QSpinBox()

        def stream_callback(signal):
            qt_canvas.matplotlib_canvas.refresh_signal(signal)

        def do_stream():
            global streamer
            stream_dialog.hide()
            stream_canvas = variables_table.create_canvas(stream_window=window_field.value())
            canvas.rows = stream_canvas.rows
            canvas.cols = stream_canvas.cols
            canvas.auto_refresh = stream_canvas.auto_refresh
            canvas.streaming = True
            canvas.plots = stream_canvas.plots
            qt_canvas.set_canvas(canvas)

            streamer = CanvasStreamer(da)
            streamer.start(canvas, stream_callback)
            stream_button.setText("Stop")

        def create_stream_dialog():
            dialog = QDialog(main_widget)

            window_field.setMinimum(1)
            window_field.setMaximum(100000)
            window_field.setValue(stream_window)

            startButton = QPushButton("Start")
            startButton.clicked.connect(do_stream)

            cancelButton = QPushButton("Cancel")
            cancelButton.clicked.connect(dialog.hide)

            windowOptions = dict(seconds="Seconds")
            windowCombo = QComboBox()
            for k, v in windowOptions.items():
                windowCombo.addItem(v, k)

            windowWidget = QWidget()
            windowWidget.setLayout(QHBoxLayout())
            windowWidget.layout().setContentsMargins(QMargins())
            windowWidget.layout().addWidget(window_field)
            windowWidget.layout().addWidget(windowCombo)

            form = QWidget()
            form.setLayout(QFormLayout())
            form.layout().addRow("Window", windowWidget)
            dialog.setLayout(QVBoxLayout())
            dialog.layout().addWidget(QLabel("Stream settings"))
            dialog.layout().addWidget(form)
            buttons = QWidget()
            buttons.setLayout(QHBoxLayout())
            buttons.layout().setContentsMargins(QMargins())
            buttons.layout().addWidget(startButton)
            buttons.layout().addWidget(cancelButton)
            dialog.layout().addWidget(buttons)

            return dialog

        stream_dialog = create_stream_dialog()

        if streamer is None:
            stream_dialog.show()
        else:
            streamer.stop()
            streamer = None
            stream_button.setText("Stream")

    draw_button.clicked.connect(draw_clicked)
    stream_button.clicked.connect(stream_clicked)

    left_column_buttons = QWidget()
    left_column_buttons.setLayout(QHBoxLayout())
    left_column_buttons.layout().setContentsMargins(QMargins())
    left_column_buttons.layout().addWidget(stream_button)
    left_column_buttons.layout().addWidget(draw_button)

    left_column = QWidget()
    left_column.setLayout(QVBoxLayout())
    left_column.layout().setContentsMargins(QMargins())
    left_column.layout().addWidget(range_selector)
    left_column.layout().addWidget(variables_table)
    left_column.layout().addWidget(left_column_buttons)

    central_widget = QSplitter()
    central_widget.addWidget(left_column)
    central_widget.addWidget(right_column)

    status_bar = StatusBar()
    status_bar.addPermanentWidget(QLabel("Tool version {} iplotlib {}".format(__version__, __iplotlib_version__)))

    main_menu = MainMenu(export_widgets=dict(variables_table=variables_table, main_canvas=qt_canvas, time_model=range_selector))

    main_widget = Multiwindow()
    main_widget.setMenuBar(main_menu)
    main_widget.setCentralWidget(central_widget)
    main_widget.setStatusBar(status_bar)
    main_widget.setWindowTitle("MINT: {}".format(os.getpid()))
    main_widget.show()

    app.setWindowIcon(main_widget.style().standardIcon(getattr(QStyle, "SP_BrowserReload")))
    sys.exit(app.exec_())
