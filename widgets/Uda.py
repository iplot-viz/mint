import os
import threading
import time
import typing
import numpy as np
from functools import partial

import pandas
from PyQt5 import QtGui
from PyQt5.QtCore import QAbstractTableModel, QMargins, QModelIndex, QStringListModel, QVariant, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction, QActionGroup, QApplication, QComboBox, QDataWidgetMapper, QDateTimeEdit, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, \
    QMainWindow, QMenu, QMenuBar, QPushButton, QRadioButton, QSizePolicy, QStackedWidget, QStatusBar, QStyle, QTabWidget, QTableView, QTableWidget, QToolBar, QToolButton, QVBoxLayout, QWidget
from iplotlib.Axis import LinearAxis
from iplotlib.Canvas import Canvas
from iplotlib.Plot import Plot2D
from iplotlib.Signal import UDAPulse
from matplotlib.dates import date2num, epoch2num
from qt import QtPlotCanvas

from util.JSONExporter import JSONExporter


class UDAVariablesTable(QWidget):

    canvasChanged = pyqtSignal(Canvas)

    def __init__(self, parent=None, data_access=None, model=None, header=None, plot_class=Plot2D):
        super().__init__(parent)

        self.data_access = data_access
        self.plot_class = plot_class
        self.header = header
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.table_model = PlotsModel(self.header, initial_model=model)

        self.uda_table_view = QTableView()
        self.uda_table_view.setModel(self.table_model)

        def export_clicked():
            file = QFileDialog.getSaveFileName(self, "Save CSV")
            if file and file[0]:
                self.export_csv(file[0])

        def import_clicked():
            file = QFileDialog.getOpenFileName(self, "Open CSV")
            if file and file[0]:
                self.import_csv(file[0])


        uda_toolbar = UDAVairablesToolbar()
        uda_toolbar.exportCsv.connect(export_clicked)
        uda_toolbar.importCsv.connect(import_clicked)

        uda_tab = QWidget()
        uda_tab.setLayout(QVBoxLayout())
        uda_tab.layout().setContentsMargins(QMargins())
        uda_tab.layout().addWidget(uda_toolbar)
        uda_tab.layout().addWidget(self.uda_table_view)

        tabwidget = QTabWidget()
        tabwidget.addTab(uda_tab, "Data")

        self.layout().addWidget(tabwidget)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:

        def remove_row():
            selected_rows = [e.row() for e in self.uda_table_view.selectionModel().selectedIndexes()]
            for row in reversed(sorted(selected_rows)):
                self.table_model.removeRow(row)

        context_menu = QMenu(self)
        context_menu.addAction(self.style().standardIcon(getattr(QStyle, "SP_TrashIcon")), "Remove", remove_row)
        context_menu.popup(event.globalPos())

    def _create_signals(self, row, time_model=None):

        def get_value(data_row, key):
            return data_row[list(self.header).index(key)]

        if row and get_value(row, "DataSource") and get_value(row, "Variable"):
            signal_params = dict(datasource=get_value(row, "DataSource"), title=get_value(row, "Alias") or None, varname=get_value(row, "Variable"), envelope=get_value(row, "Envelope"))

            if time_model is not None:
                if 'pulsenb' in time_model:
                    signals = [UDAPulse(**signal_params, pulsenb=e, ts_relative=True) for e in time_model['pulsenb']]
                else:
                    signals = [UDAPulse(**signal_params, pulsenb=None, ts_relative=False, **time_model)]
            else:
                signals = [UDAPulse(**signal_params)]

            stack_val = str(get_value(row, "Stack")).split('.')
            col_num = int(stack_val[0]) if len(stack_val) > 0 and stack_val[0] else 1
            row_num = int(stack_val[1]) if len(stack_val) > 1 and stack_val[1] else 1
            stack_num = int(stack_val[2]) if len(stack_val) > 2 and stack_val[2] else 1

            row_span = str(get_value(row, "RowSpan")) or 1
            col_span = str(get_value(row, "ColSpan")) or 1

            return signals, int(col_num), int(row_num), int(stack_num), int(row_span), int(col_span)
        else:
            return None, 0, 0, 0, 1, 1

    def create_canvas(self, time_model=None):
        model = {}

        x_axis_date = False if time_model is not None and 'pulsenb' in time_model else True

        for row in self.table_model.model:
            signals, colnum, rownum, stacknum, row_span, col_span = self._create_signals(row, time_model)
            if signals:
                if colnum not in model:
                    model[colnum] = {}
                if rownum not in model[colnum]:
                    model[colnum][rownum] = [row_span, col_span, {}]
                else:
                    existing = model[colnum][rownum]
                    existing[0] = row_span if row_span > existing[0] else existing[0]
                    existing[1] = col_span if col_span > existing[1] else existing[1]

                if stacknum not in model[colnum][rownum][2]:
                    model[colnum][rownum][2][stacknum] = []
                for signal in signals:
                    model[colnum][rownum][2][stacknum].append(signal)

        canvas = Canvas()

        if model.keys():
            canvas.cols = max(model.keys())
            canvas.rows = max([max(e.keys()) for e in model.values()])
            canvas.plots = [[] for _ in range(canvas.cols)]

            for colnum, rows in model.items():
                for row in range(max(rows.keys())):
                    plot = None
                    if row+1 in rows.keys():
                        y_axes = [LinearAxis() for _ in range(len(rows[row + 1][2].items()))]
                        plot = self.plot_class(axes=[LinearAxis(is_date=x_axis_date), y_axes], row_span=rows[row+1][0], col_span=rows[row+1][1])
                        for stack, signals in rows[row+1][2].items():
                            for signal in signals:
                                plot.add_signal(signal, stack=stack)
                    canvas.add_plot(plot, col=colnum-1)

        return canvas




    def export_csv(self, file_path):
        df = pandas.DataFrame(self.uda_table_view.model().model[:-1])
        df.to_csv(file_path, header=self.uda_table_view.model().column_names, index=False)

    def import_csv(self, file_path):
        df = pandas.read_csv(file_path, dtype=str, keep_default_na=False)
        if not df.empty:
            self.uda_table_view.model().set_model(df.values.tolist())


class PlotsModel(QAbstractTableModel):

    def __init__(self, column_definitions, initial_model=None):
        super().__init__()
        self.column_names = []
        if column_definitions is not None:
            self.column_names = [e[1].get("label") or e[0] for e in column_definitions.items()]
        self.columns = len(self.column_names)
        self.model = self._expand_model(initial_model or [])
        self._add_empty_row()

    def columnCount(self, parent):
        return self.columns

    def rowCount(self, parent):
        return len(self.model)

    def data(self, index, role):
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return self.model[index.row()][index.column()]
        return QVariant()

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if role == Qt.EditRole:
            self.model[index.row()][index.column()] = value

            if index.row() == len(self.model) - 1:
                self._add_empty_row()

            self.dataChanged.emit(self.createIndex(0, 0), self.createIndex(len(self.model), self.columns))
            return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.column_names[section] if section < len(self.column_names) else "N/A"

    def _add_empty_row(self):
        self.model.append(["" for e in range(self.columns)])
        self.layoutChanged.emit()

    def removeRow(self, row: int, parent=QModelIndex()) -> bool:
        if row < len(self.model):
            self.model.remove(self.model[row])
            self.layoutChanged.emit()
            return True
        else:
            return False

    """Pad each array row with empty strings to self.columns length """
    def _expand_model(self, source):
        if source is not None:
            for row in source:
                if len(row) < self.columns:
                    row += [''] * (self.columns - len(row))
        return source

    def set_model(self, model):
        self.removeRows(0, self.rowCount(QModelIndex()))
        self.model = self._expand_model(model)
        self._add_empty_row()






class UDAVairablesToolbar(QWidget):

    exportCsv = pyqtSignal()
    importCsv = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        tb = QToolBar()
        tb.addAction(QIcon(os.path.join(os.path.dirname(__file__), "../icons/open_file.png")), "Open CSV", self.importCsv.emit)
        tb.addAction(QIcon(os.path.join(os.path.dirname(__file__), "../icons/save_as.png")), "Save CSV", self.exportCsv.emit)
        self.layout().addWidget(tb)


class UDARangeSelector(QWidget):

    PULSE_NUMBER = 1
    TIME_RANGE = 2
    RELATIVE_TIME = 3

    TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"

    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        if model is None:
            model = {}
        self.model = model or {}
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum))
        self._createStackedForm()

    def get_model(self):
        model = self.items[self.stack.currentIndex()][3]
        # return {"type": self.items[self.stack.currentIndex()][0], "model": model.stringList()}
        return model()

    def _createStackedForm(self):
        self.items = [self._createTimeRangeForm(), self._createPusleNumberForm(), self._createRelativeTimeForm()]

        radiogroup = QGroupBox()
        radiogroup.setSizePolicy(QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum))
        radiogroup.setLayout(QHBoxLayout())

        self.stack = QStackedWidget()

        def switchForm(selected):
            self.stack.setCurrentIndex(selected)

        for idx, item in enumerate(self.items):
            self.stack.addWidget(item[2])
            button = QRadioButton(item[1])
            button.clicked.connect(partial(switchForm, idx))
            radiogroup.layout().addWidget(button)

            if self.model.get('mode') == item[0]:
                button.setChecked(True)
                self.stack.setCurrentIndex(idx)

        if not self.model.get('mode'):
            self.stack.setCurrentIndex(0)
            radiogroup.layout().itemAt(0).widget().setChecked(True)

        self.layout().addWidget(radiogroup)
        self.layout().addWidget(self.stack)

    def _createPusleNumberForm(self):
        form = QWidget()
        form.setLayout(QFormLayout())

        pulse_number = QLineEdit()

        model = QStringListModel(form)
        model.setStringList(self.model.get('value') if self.model.get('mode') == UDARangeSelector.PULSE_NUMBER and self.model.get('value') else [''])

        mapper = QDataWidgetMapper(form)
        mapper.setOrientation(Qt.Vertical)
        mapper.setModel(model)
        mapper.addMapping(pulse_number, 0)
        mapper.toFirst()

        form.layout().addRow(QLabel("Pulse number"), pulse_number)

        def ret():
            return {"pulsenb": [e for e in model.stringList()[0].split(',')]}

        return UDARangeSelector.PULSE_NUMBER, "Pulse number", form, ret,

    def _createTimeRangeForm(self):
        form = QWidget()
        form.setLayout(QFormLayout())

        from_time = QDateTimeEdit()
        from_time.setDisplayFormat(self.TIME_FORMAT)
        to_time = QDateTimeEdit()
        to_time.setDisplayFormat(self.TIME_FORMAT)

        model = QStringListModel(form)
        model.setStringList(self.model.get('value') if self.model.get('mode') == UDARangeSelector.TIME_RANGE and self.model.get('value') else ['', ''])

        mapper = QDataWidgetMapper(form)
        mapper.setOrientation(Qt.Vertical)
        mapper.setModel(model)
        mapper.addMapping(from_time, 0)
        mapper.addMapping(to_time, 1)
        mapper.toFirst()

        form.layout().addRow(QLabel("From time"), from_time)
        form.layout().addRow(QLabel("To time"), to_time)

        def ret():
            return {"ts_start": model.stringList()[0], "ts_end": model.stringList()[1]}

        return UDARangeSelector.TIME_RANGE, "Time range", form, ret


    def _createRelativeTimeForm(self):
        form = QWidget()
        form.setLayout(QFormLayout())

        options = [(60, "Last minute"), (3600, "Last hour")]

        values = QStringListModel()
        values.setStringList([e[1] for e in options])

        relative_time = QComboBox()
        relative_time.setModel(values)

        form.layout().addRow(QLabel("From"), relative_time)

        def ret():
            return {"relative": options[relative_time.currentIndex()][0]}

        return UDARangeSelector.RELATIVE_TIME, "Relative", form, ret,


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
        self.canvas = canvas
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
            file = QFileDialog.getSaveFileName(self, "Save JSON")
            if file and file[0]:
                with open(file[0], "w") as out_file:
                    out_file.write(JSONExporter().to_json(self.canvas))

        def do_import():
            file = QFileDialog.getOpenFileName(self, "Open CSV")
            if file and file[0]:
                with open(file[0], "r") as in_file:
                    self.canvas = JSONExporter().from_json(in_file.read())
                    print("CANVAS: ",self.canvas)

        self.toolbar.import_json.connect(do_import)
        self.toolbar.export_json.connect(do_export)

    def draw(self):
        self.toolbar.setVisible(True)
        self.plot_canvas.set_canvas(self.canvas)


class MainMenu(QMenuBar):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum))

        file_menu = self.addMenu("File")
        help_menu = self.addMenu("Help")

        exit_action = QAction("Exit", self)
        exit_action.setShortcuts(QKeySequence.Quit)
        exit_action.triggered.connect(QApplication.closeAllWindows)

        about_action = QAction("About Qt", self)
        about_action.setShortcuts(QKeySequence.New)
        about_action.setStatusTip("About Qt")
        about_action.triggered.connect(QApplication.aboutQt)

        lr_group = QActionGroup(self)
        lr_group.setExclusive(True)

        left_action = QAction("Left", self)
        left_action.setChecked(False)
        left_action.setCheckable(True)
        left_action.setActionGroup(lr_group)

        right_action = QAction("Right", self)
        right_action.setCheckable(True)
        right_action.setChecked(True)
        right_action.setActionGroup(lr_group)

        help_menu.addAction(left_action)
        help_menu.addAction(right_action)
        help_menu.addSection("Testsection")
        help_menu.addAction(about_action)

        file_menu.addAction(exit_action)


class StatusBar(QStatusBar):

    def __init__(self):
        super().__init__()
        self.showMessage("Ready.")

"""This window closes all other open windows when itself gets closed"""
class Multiwindow(QMainWindow):

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        QApplication.closeAllWindows()
        super().closeEvent(event)