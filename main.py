import json
import os
import sys
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from threading import Timer

import argparse

from gui._version import __version__
from iplotlib.core._version import __version__ as __iplotlib_version__

import pandas
from qtpy.QtCore import QMargins
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox, QSplitter, QStyle, QVBoxLayout, QWidget
from iplotDataAccess.dataAccess import DataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.data_access.dataAccessSignal import AccessHelper
from iplotlib.qt.qtCanvasToolbar import CanvasToolbar

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)


parser = argparse.ArgumentParser(description='MINT application')
parser.add_argument('-IMPL', metavar='CANVAS_IMPL', help='Use canvas implementation (MATPLOTLIB/GNUPOLOT/...)', default="MATPLOTLIB")
parser.add_argument('-d', dest='csv_file', metavar='csv_file', help='Load variables table from file')
parser.add_argument('-w', dest='json_file', metavar='json_file', help='Load a workspace from json file')
parser.add_argument('-e', dest='image_file', metavar='image_file', help='Load canvas from JSON and save to file (PNG/SVG/PDF...)')
parser.add_argument('-ew', dest='export_width', metavar='export_width', type=int, default=1920, help='Exported image width')
parser.add_argument('-eh', dest='export_height', metavar='export_height', type=int, default=1080, help='Exported image height')
parser.add_argument('-ed', dest='export_dpi', metavar='export_dpi', type=int, default=100, help='Exported image DPI')

args = parser.parse_args()

# print(parser.print_help())

# exit(1)

try:
    from iplotlib.impl.gnuplot.qt.qtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas
except ModuleNotFoundError:
    logger.error("import qt gnuplot not installed ")

from iplotlib.data_access.streamer import CanvasStreamer

from gui.main import Multiwindow, MainMenu, StatusBar
from gui.variablesTable import VariablesTable, DataRangeSelector

def export_to_file(impl: str, canvas: Canvas, output_filename, **kwargs):
    try:
        if impl.lower() == "matplotlib":
            import matplotlib
            matplotlib.rcParams["figure.dpi"] = kwargs.get('dpi')
            from iplotlib.impl.matplotlib.matplotlibCanvas import MatplotlibCanvas
            
            mpl_canvas = MatplotlibCanvas()
            mpl_canvas.export_image(output_filename, canvas=canvas, **kwargs)
    except FileNotFoundError:
        logger.error(f"Unable to open file: {output_filename}")


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
    canvasImpl = args.IMPL

    var_table_file = args.csv_file
    workspace_file = args.json_file

    currTime = datetime.utcnow().isoformat(timespec='seconds')
    currTimeDelta = datetime.utcnow() - timedelta(days=7)

    # This is a main reference to canvas that is drawn
    if workspace_file:
        with open(workspace_file) as f:
            payload = json.loads(f.read())
            if payload.get("main_canvas"):
                json_str = json.dumps(payload.get("main_canvas"))
                canvas = Canvas.from_json(json_str)
            else:
                logger.error(f"Failed to load main_canvas from {workspace_file}")
    else:
        canvas = Canvas(grid=True)

    if args.image_file:
        export_to_file(canvasImpl, canvas, args.image_file, dpi=args.export_dpi, width=args.export_width, height=args.export_height)
        exit(0)

    app = QApplication(sys.argv)

    header = {
        "DataSource": {"label": "DS"},
        "Variable": {},
        "Stack": {},
        "RowSpan": {"label": "Row span"},
        "ColSpan": {"label": "Col span"},
        "Envelope": {},
        "Alias": {},
        "DecSamples": {"label": "Samples"},
        "PulseNumber": {},
        "StartTime": {},
        "EndTime": {}
    }

    model = {
        "range": {"mode": DataRangeSelector.TIME_RANGE, "value": [currTimeDelta.isoformat(timespec='seconds'), currTime]}
        # "range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2020-10-19T20:17:40", "2020-10-19T20:27:40"]}
        # "range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2021-02-22T12:00:00", "2021-02-22T12:00:01"]}
        # "range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2018-09-13T15:22:35.100", "2018-09-13T15:22:35.101 "]}
        #"range": {"mode": DataRangeSelector.TIME_RANGE, "value": ["2021-02-22T12:01:53.790", "2021-02-25T12:01:54.800"]}

    }

    if var_table_file:
        model["table"] = pandas.read_csv(var_table_file, dtype=str, keep_default_na=False).values.tolist()

    streamer = None
    stream_window = 3600
    refresh_timer = None

    if canvasImpl == "MATPLOTLIB":
        from iplotlib.impl.matplotlib.qt.qtMatplotlibCanvas import QtMatplotlibCanvas
        right_column = QWidget()
        right_column.setLayout(QVBoxLayout())
        qt_canvas = QtMatplotlibCanvas(tight_layout=True)
        right_column.layout().addWidget(CanvasToolbar(qt_canvas=qt_canvas))
        right_column.layout().addWidget(qt_canvas)

    variables_table = VariablesTable(data_access=da, header=header, model=model.get("table"))
    range_selector = DataRangeSelector(model=model.get("range"))

    if workspace_file:
        with open(workspace_file) as json_file:
            payload = json.loads(json_file.read())
            if payload.get("variables_table"):
                json_str = json.dumps(payload.get("variables_table"))
                variables_table.import_json(json_str)
            if payload.get("range_selector"):
                json_str = json.dumps(payload.get("range_selector"))
                range_selector.import_json(json_str)

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

        qt_canvas.unfocus_plot()
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
            qt_canvas.unfocus_plot()
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

