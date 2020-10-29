# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import os
import sys
import time
from threading import Thread

from PyQt5.QtCore import QMargins, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QDockWidget, QHBoxLayout, QPushButton, QSizePolicy, QSplitter, QStyle, QVBoxLayout, QWidget
from dataAccess import DataAccess
from iplotlib.Signal import UDAPulse
from qt.gnuplot.QtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas
from qt.matplotlib.QtMatplotlibCanvas2 import QtMatplotlibCanvas2

from widgets.Uda import MainCanvas, MainMenu, PlotToolbar, UDARangeSelector, UDAVariablesTable


if __name__ == '__main__':

    da = DataAccess()
    da.udahost = os.environ.get('UDA_HOST') or "10.153.0.204"

    app = QApplication(sys.argv)

    header = ["Variable", "Stack", "Row span", "Col span"]

    stack_model = {
        "table": [
            ["UTIL-PHV-P400-BAY3:41PPAC_TC3000-IT01", "1.1.1"]
            ,["UTIL-PHV-P400-BAY3:41PPAC_TC3000-IT02", "1.1.2"]
        ],
        "range": {"mode": UDARangeSelector.TIME_RANGE, "value": ["2020-09-18T08:00:00", "2020-09-30T08:00:00"]}
    }

    pan_model = {
        "table": [
            ["CWS-SCSU-HR00:AISPARE-2169-XI", "1.1.1"]
        ],
        "range": {"mode": UDARangeSelector.TIME_RANGE, "value": ["2020-10-21T14:30:52.195Z", "2020-10-21T14:50:55.195Z"]}
    }

    pan_model2 = {
        "table": [
            ["UTIL-SYSM-COM-4503-UT:SRV3601-NRBPS", "1.1.1"]
        ],
        "range": {"mode": UDARangeSelector.TIME_RANGE, "value": ["2020-10-14T14:30:52.195Z", "2020-10-21T14:50:55.195Z"]}
    }

    empty_model = {}

    model = stack_model

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

    right_column = MainCanvas(plot_canvas=QtMatplotlibCanvas2())
    # right_column = MainCanvas(plot_canvas=QtGnuplotMultiwidgetCanvas())

    central_widget = QSplitter()
    central_widget.setContentsMargins(10, 0, 10, 10)
    central_widget.addWidget(left_column)
    central_widget.addWidget(right_column)

    main_widget = QWidget()
    main_widget.setLayout(QVBoxLayout())
    main_widget.layout().setContentsMargins(QMargins())
    main_widget.layout().addWidget(MainMenu())
    main_widget.layout().addWidget(central_widget)

    main_widget.show()
    app.setWindowIcon(main_widget.style().standardIcon(getattr(QStyle, "SP_BrowserReload")))
    sys.exit(app.exec_())
