import collections
import typing
from functools import partial

import pandas
from PyQt5 import QtGui
from PyQt5.QtCore import QAbstractTableModel, QMargins, QModelIndex, QStringListModel, QVariant, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction, QActionGroup, QApplication, QComboBox, QDataWidgetMapper, QDateTimeEdit, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, \
    QMainWindow, QMenu, QMenuBar, QPushButton, QRadioButton, QSizePolicy, QStackedWidget, QStatusBar, QStyle, QTabWidget, QTableView, QTableWidget, QToolBar, QToolButton, QVBoxLayout, QWidget
from iplotlib.Axis import LinearAxis
from iplotlib.Canvas import Canvas
from iplotlib.Plot import Plot2D
from iplotlib.Signal import UDAPulse
from qt.gnuplot.QtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas
from twisted.names.test.test_dns import RECORD_TYPES


class UDAVariablesTable(QWidget):

    canvasChanged = pyqtSignal(Canvas)

    def __init__(self, parent=None, data_access=None, model=None, header=None, plot_class=Plot2D):
        super().__init__(parent)
        self.data_access = data_access
        self.plot_class = plot_class

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.table_model = PlotsModel(header, initial_model=model)

        self.uda_table_view = QTableView()
        self.uda_table_view.setModel(self.table_model)

        uda_toolbar = UDAVairablesToolbar(table_view=self.uda_table_view)

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

    def _create_signals(self, row, time_model):
        if row and row[0]:
            if 'pulsenb' in time_model:
                signals = [UDAPulse(self.data_access, row[0], e, ts_relative=True) for e in time_model['pulsenb']]
            else:
                signals = [UDAPulse(self.data_access, row[0], pulsenb=None, ts_relative=False, **time_model)]

            stack_val = str(row[1]).split('.')
            col_num = int(stack_val[0]) if len(stack_val) > 0 and stack_val[0] else 1
            row_num = int(stack_val[1]) if len(stack_val) > 1 and stack_val[1] else 1
            stack_num = int(stack_val[2]) if len(stack_val) > 2 and stack_val[2] else 1

            row_span = str(row[2]) if row[2] else 1
            col_span = str(row[3]) if row[3] else 1

            return signals, int(col_num), int(row_num), int(stack_num), int(row_span), int(col_span)
        else:
            return None, 0, 0, 0, 1, 1

    def to_canvas(self, time_model):
        model = {}

        x_axis_date = False
        if time_model.get("ts_start") and time_model.get("ts_end"):
            x_axis_date = True



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


        if model.keys():
            total_cols = max(model.keys())
            total_rows = max([max(e.keys()) for e in model.values()])
            canvas = Canvas(total_rows, total_cols)

            for colnum, rows in model.items():
                for row in range(max(rows.keys())):
                    plot = None
                    if row+1 in rows.keys():
                        plot = self.plot_class(axes=[LinearAxis(is_date=x_axis_date), LinearAxis()], row_span=rows[row+1][0], col_span=rows[row+1][1])
                        print("PLOT:",plot,x_axis_date,time_model)
                        for stack, signals in rows[row+1][2].items():
                            for signal in signals:
                                plot.add_signal(signal, stack=stack)
                    canvas.add_plot(plot, col=colnum-1)
            return canvas


class PlotsModel(QAbstractTableModel):

    def __init__(self, column_names, initial_model=None):
        super().__init__()
        self.column_names = column_names or []
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

    def __init__(self, parent=None, table_view=None):
        super().__init__(parent)
        self.table_view = table_view

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        tb = QToolBar()
        tb.addAction(self.style().standardIcon(getattr(QStyle, "SP_DirOpenIcon")), "Open CSV", self.do_import)
        tb.addAction(self.style().standardIcon(getattr(QStyle, "SP_DialogSaveButton")), "Save CSV", self.do_export)

        self.layout().addWidget(tb)

    def do_export(self):
        file = QFileDialog.getSaveFileName(self, "Save CSV")
        if file and file[0]:
            df = pandas.DataFrame(self.table_view.model().model[:-1])
            df.to_csv(file[0], header=self.table_view.model().column_names, index=False)

    def do_import(self):
        file = QFileDialog.getOpenFileName(self, "Open CSV")
        if file and file[0]:
            df = pandas.read_csv(file[0], dtype=str, keep_default_na=False)
            if not df.empty:
                self.table_view.model().set_model(df.values.tolist())


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QVBoxLayout())
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
        undo_action.setIcon(self.style().standardIcon(getattr(QStyle, "SP_ArrowBack")))
        undo_action.triggered.connect(self.undo.emit)
        self.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setIcon(self.style().standardIcon(getattr(QStyle, "SP_ArrowForward")))
        redo_action.triggered.connect(self.redo.emit)
        self.addAction(redo_action)



        detach_action = QAction("Detach", self)
        detach_action.setIcon(self.style().standardIcon(getattr(QStyle, "SP_TitleBarNormalButton")))
        detach_action.triggered.connect(self.detachPressed.emit)
        self.addAction(detach_action)

        # self?.layout().addWidget(toolbar)


class MainCanvas(QMainWindow):

    def __init__(self, detached=False, attach_parent=None, plot_canvas=None):
        super().__init__()
        self.plot_canvas = plot_canvas
        self.toolbar = CanvasToolbar()

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
            else:
                self.attach_parent = self.parent()
                self.detached_window.setCentralWidget(self)
                self.detached_window.show()
                self.detached = True

        self.toolbar.toolSelected.connect(tool_selected)
        self.toolbar.detachPressed.connect(detach)

    def set_canvas(self, canvas):
        self.plot_canvas.set_canvas(canvas)



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

class Multiwindow(QMainWindow):

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        QApplication.closeAllWindows()
        super().closeEvent(event)