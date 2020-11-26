import sys
from datetime import datetime, timedelta

import pandas
from PyQt5.QtCore import QMargins
from PyQt5.QtWidgets import QApplication, QPushButton, QSplitter, QStyle, QVBoxLayout, QWidget
from dataAccess import DataAccess
from iplotlib.UDAAccess import UDAAccess
from qt.gnuplot.QtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas
from qt.matplotlib.QtMatplotlibCanvas2 import QtMatplotlibCanvas2

from widgets.PreferencesWindow import PreferencesWindow
from widgets.Uda import MainCanvas, MainMenu, Multiwindow, StatusBar, UDARangeSelector, UDAVariablesTable

if __name__ == '__main__':

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

    # file_to_import = "csv/deadlock_one.csv"
    # file_to_import = "csv/deadlock_example.csv"
    # file_to_import = "csv/pulses_example_one.csv"
    file_to_import = "csv/envelope.csv"
    # file_to_import = None


    app = QApplication(sys.argv)

    header = {
        "DataSource": {"label": "DS"},
        "Variable": {},
        "Stack": {},
        "RowSpan": {"label": "Row span"},
        "ColSpan": {"label": "Col span"},
        "Envelope": {}
    }


    model = {
        # "range": {"mode": UDARangeSelector.TIME_RANGE, "value": [currTimeDelta.isoformat(timespec='seconds'), currTime]}
        "range": {"mode": UDARangeSelector.TIME_RANGE, "value": ["2020-10-19T20:17:40", "2020-10-19T20:27:40"]}

    }

    if file_to_import:
        model["table"] = pandas.read_csv(file_to_import, dtype=str, keep_default_na=False).values.tolist()

    variables_table = UDAVariablesTable(data_access=da, header=header, model=model.get("table"))
    range_selector = UDARangeSelector(model=model.get("range"))
    draw_button = QPushButton("Draw")
    draw_button.setIcon(draw_button.style().standardIcon(getattr(QStyle, "SP_BrowserReload")))

    def redraw():
        time_model = range_selector.get_model()
        canvas = variables_table.to_canvas(time_model)
        right_column.set_canvas(canvas)

    draw_button.clicked.connect(redraw)



    left_column = QWidget()
    left_column.setLayout(QVBoxLayout())
    left_column.layout().setContentsMargins(QMargins())
    left_column.layout().addWidget(range_selector)
    left_column.layout().addWidget(variables_table)
    left_column.layout().addWidget(draw_button)

    if (canvasImpl=="MATPLOTLIB"):
        right_column = MainCanvas(plot_canvas=QtMatplotlibCanvas2(tight_layout=False))
    else:
        right_column = MainCanvas(plot_canvas=QtGnuplotMultiwidgetCanvas())

    preferences_window = PreferencesWindow()

    def preferences():
        time_model = range_selector.get_model()
        canvas = variables_table.to_canvas(time_model)
        preferences_window.set_canvas(canvas)
        preferences_window.show()


    right_column.toolbar.preferences.connect(preferences)




    central_widget = QSplitter()
    central_widget.addWidget(left_column)
    central_widget.addWidget(right_column)

    main_widget = Multiwindow()
    main_widget.setMenuBar(MainMenu())
    main_widget.setCentralWidget(central_widget)
    main_widget.setStatusBar(StatusBar())

    main_widget.show()
    app.setWindowIcon(main_widget.style().standardIcon(getattr(QStyle, "SP_BrowserReload")))
    sys.exit(app.exec_())
