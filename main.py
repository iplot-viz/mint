import os
import sys
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

import pandas
from PyQt5.QtCore import QMargins
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QSplitter, QStyle, QVBoxLayout, QWidget
from access.dataAccess import DataAccess
from iplotlib.Canvas import Canvas
from iplotlib.UDAAccess import UDAAccess

try:
    from qt.gnuplot.QtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas
except ModuleNotFoundError:
    print("import qt gnuplot not installed ")

from qt.matplotlib.QtMatplotlibCanvas2 import QtMatplotlibCanvas2
from utils.streamer import CanvasStreamer

from gui.Main import Multiwindow, MainMenu, StatusBar
from gui.PlotCanvas import MainCanvas
from gui.VariablesTable import VariablesTable, DataRangeSelector
from gui.PreferencesWindow import PreferencesWindow


if __name__ == '__main__':


    print("Running version 0.5.0")
    da = DataAccess()

    UDAAccess.da = da

    ###we load the data source conf files
    listDS=da.loadConfig()
    defDS = da.getDefaultDSName()
    if len(listDS)<1:
        print ("no data sources found, exiting")
        sys.exit(-1)

    #da.udahost = os.environ.get('UDA_HOST') or "io-ls-udafe01.iter.org"
    canvasImpl = "MATPLOTLIB"
    if len(sys.argv) > 1:
        if sys.argv[1] == 'MATPLOTLIB' or sys.argv[1] == 'GNUPLOT':
            canvasImpl = sys.argv[1]

    currTime = datetime.now().isoformat(timespec='seconds')
    currTimeDelta = datetime.now() - timedelta(days=7)

    file_to_import = None

    # file_to_import = "csv/deadlock_stack.csv"
    # file_to_import = "csv/stream_example.csv"
    # file_to_import = "csv/deadlock_example.csv"
    # file_to_import = "csv/pulses_example_one.csv"
    # file_to_import = "csv/envelope.csv"
    #file_to_import = "csv/nanosecond.csv"

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
        "range": {"mode": DataRangeSelector.TIME_RANGE, "value": [currTimeDelta.isoformat(timespec='seconds'), currTime]}
        # "range": {"mode": UDARangeSelector.TIME_RANGE, "value": ["2020-10-19T20:17:40", "2020-10-19T20:27:40"]}
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

    if canvasImpl == "MATPLOTLIB":
        right_column = MainCanvas(plot_canvas=QtMatplotlibCanvas2(tight_layout=True), canvas=canvas)
    else:
        right_column = MainCanvas(plot_canvas=QtGnuplotMultiwidgetCanvas(), canvas=canvas)

    variables_table = VariablesTable(data_access=da, header=header, model=model.get("table"))
    range_selector = DataRangeSelector(model=model.get("range"))

    draw_button = QPushButton("Draw")
    draw_button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons/plot.png")))
    stream_button = QPushButton("Stream")
    stream_button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons/plot.png")))

    preferences_window = PreferencesWindow()
    preferences_window.apply.connect(partial(right_column.draw, canvas))

    right_column.toolbar.preferences.connect(preferences_window.show)

    def draw_clicked():
        """This function creates and draws the canvas getting data from variables table and time/pulse widget"""
        time_model = range_selector.get_model()
        new_canvas = variables_table.create_canvas(time_model)
        canvas.rows = new_canvas.rows
        canvas.cols = new_canvas.cols
        canvas.plots = new_canvas.plots
        canvas.autoscale = new_canvas.autoscale
        canvas.streaming = False
        preferences_window.set_canvas(canvas)

        right_column.toolbar.setVisible(True)
        dump_dir = os.path.expanduser("~/.local/1Dtool/dumps/")
        Path(dump_dir).mkdir(parents=True, exist_ok=True)
        variables_table.export_csv(os.path.join(dump_dir, "variables_table_" + str(os.getpid()) + ".csv"))
        right_column.draw(canvas)

    def stream_clicked():
        """This function shows the streaming dialog and then creates a canvas that is used when streaming"""
        global streamer

        windowField = QSpinBox()

        def stream_callback(signal):
            right_column.plot_canvas.matplotlib_canvas.refresh_signal(signal)

        def do_stream():
            global streamer
            stream_dialog.hide()

            stream_canvas = variables_table.create_canvas(stream_window=windowField.value())
            canvas.rows = stream_canvas.rows
            canvas.cols = stream_canvas.cols
            canvas.streaming = True
            canvas.plots = stream_canvas.plots
            right_column.draw(canvas)

            right_column.toolbar.setVisible(False)

            streamer = CanvasStreamer(da)
            streamer.start(canvas, stream_callback)
            stream_button.setText("Stop")

        def create_stream_dialog():
            dialog = QDialog(main_widget)

            loginField = QLineEdit()
            passwordField = QLineEdit()
            passwordField.setEchoMode(QLineEdit.Password)
            # windowField = QSpinBox()
            windowField.setMinimum(1)
            windowField.setMaximum(100000)
            windowField.setValue(stream_window)

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
            windowWidget.layout().addWidget(windowField)
            windowWidget.layout().addWidget(windowCombo)

            form = QWidget()
            form.setLayout(QFormLayout())
            # form.layout().addRow("Login", loginField)
            # form.layout().addRow("Password", passwordField)
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
    status_bar.showMessage("Tool version 0.5.0")

    main_menu = MainMenu(export_widgets=dict(variables_table=variables_table, main_canvas=right_column, time_model=range_selector))

    main_widget = Multiwindow()
    main_widget.setMenuBar(main_menu)
    main_widget.setCentralWidget(central_widget)
    main_widget.setStatusBar(status_bar)
    main_widget.show()

    app.setWindowIcon(main_widget.style().standardIcon(getattr(QStyle, "SP_BrowserReload")))
    sys.exit(app.exec_())
