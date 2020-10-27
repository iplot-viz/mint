import typing
from functools import partial

from PyQt5 import QtGui
from PyQt5.QtCore import QAbstractTableModel, QMargins, QModelIndex, QStringListModel, QVariant, Qt, pyqtSignal
from PyQt5.QtWidgets import QAction, QComboBox, QDataWidgetMapper, QDateTimeEdit, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMenuBar, QPushButton, QRadioButton, \
    QSizePolicy, QStackedWidget, QStyle, QTabWidget, QTableView, QTableWidget, QVBoxLayout, QWidget
from iplotlib.Canvas import Canvas
from iplotlib.Plot import Plot2D
from iplotlib.Signal import UDAPulse
from qt.gnuplot.QtGnuplotMultiwidgetCanvas import QtGnuplotMultiwidgetCanvas


class UDAVariablesTable(QWidget):

    canvasChanged = pyqtSignal(Canvas)

    def __init__(self, parent=None, data_access=None, model=[], header=[], plot_class=Plot2D):
        super().__init__(parent)
        self.data_access = data_access
        self.plot_class = plot_class

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.table = QTableWidget()
        self.table.setRowCount(10)
        self.table.setColumnCount(5)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionsMovable(True)

        self.table_model = PlotsModel(header, initial_model=model)

        table_view = QTableView()
        table_view.setModel(self.table_model)

        tabwidget = QTabWidget()
        tabwidget.addTab(table_view, "Data")

        self.layout().addWidget(tabwidget)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        context_menu = QMenu(self)
        context_menu.addAction(QAction("Properties", context_menu))
        context_menu.popup(event.globalPos())

    def _create_signals(self, row, time_model):
        if row and row[0]:
            # signal = UDAPulse(da, "MAG_G5_TX1/IP", int(time_model[0]))
            if 'pulsenb' in time_model:
                signals = [UDAPulse(self.data_access, row[0], int(e)) for e in time_model['pulsenb']]
            else:
                signals = [UDAPulse(self.data_access, row[0], pulsenb=None, **time_model)]

            stack_val = row[1].split('.')
            col_num = int(stack_val[0]) if len(stack_val) > 0 and stack_val[0] else 1
            row_num = int(stack_val[1]) if len(stack_val) > 1 and stack_val[1] else 1
            stack_num = int(stack_val[2]) if len(stack_val) > 2 and stack_val[2] else 1

            return signals, int(col_num), int(row_num), int(stack_num)
        else:
            return None, 0, 0, 0

    def to_canvas(self, time_model):
        model = {}
        for row in self.table_model.model:
            signals, colnum, rownum, stacknum = self._create_signals(row, time_model)
            if signals:
                if colnum not in model:
                    model[colnum] = {}
                if rownum not in model[colnum]:
                    model[colnum][rownum] = {}
                if stacknum not in model[colnum][rownum]:
                    model[colnum][rownum][stacknum] = []
                for signal in signals:
                    model[colnum][rownum][stacknum].append(signal)

        if model.keys():
            total_cols = max(model.keys())
            total_rows = max([max(e.keys()) for e in model.values()])
            canvas = Canvas(total_rows, total_cols)

            for colnum, rows in model.items():
                for row in range(max(rows.keys())):
                    plot = None
                    if row+1 in rows.keys():
                        plot = self.plot_class()
                        for stack, signals in rows[row+1].items():
                            for signal in signals:
                                plot.add_signal(signal, stack=stack)
                    canvas.add_plot(plot, col=colnum-1)
                    print("ADDED PLOT: " + str(plot))
            return canvas

class PlotsModel(QAbstractTableModel):

    def __init__(self, column_names, initial_model=[]):
        super().__init__()
        self.model = initial_model or []
        self.column_names = column_names
        self.columns = len(self.column_names)
        self._add_empty_row()

    def columnCount(self, parent):
        return self.columns

    def rowCount(self, parent):
        return len(self.model)

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return self.model[index.row()][index.column()]
        return QVariant()

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if role == Qt.EditRole:
            self.model[index.row()][index.column()] = value

            print(self.model)
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


class UDARangeSelector(QWidget):

    PULSE_NUMBER = 1
    TIME_RANGE = 2
    RELATIVE_TIME = 3

    TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"

    def __init__(self, parent=None, model={}):
        super().__init__(parent)
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
            return {"pulsenb": [int(e) for e in model.stringList()[0].split(',')]}

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

#TODO: Crosshair should be separated as a checkbox, see: IDV-28
class PlotToolbar(QGroupBox):

    toolSelected = pyqtSignal(str)
    detachPressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum))
        self.setLayout(QHBoxLayout())

        self.second_window = None

        def selectTool(selected):
            self.toolSelected.emit(selected)

        # crosshair_button = QCheckBox("Crosshair")
        # self.layout().addWidget(crosshair_button)

        for e in [Canvas.MOUSE_MODE_CROSSHAIR, Canvas.MOUSE_MODE_PAN, Canvas.MOUSE_MODE_ZOOM]:
            button = QRadioButton(e)
            button.clicked.connect(partial(selectTool, e))
            self.layout().addWidget(button)


        detach_button = QPushButton("")
        detach_button.setToolTip("Detach/Reattach this window from the main window")
        detach_button.setIcon(detach_button.style().standardIcon(getattr(QStyle, "SP_TitleBarNormalButton")))

        def detach():
            self.detachPressed.emit()


        detach_button.clicked.connect(detach)
        self.layout().addWidget(detach_button)



class MainCanvas(QWidget):

    def __init__(self, detached=False, attach_parent=None, canvas_class=QtGnuplotMultiwidgetCanvas):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.plot_canvas = canvas_class()
        self.toolbar = PlotToolbar()
        self.layout().addWidget(self.toolbar)
        self.layout().addWidget(self.plot_canvas)
        self.layout().setContentsMargins(QMargins())

        self.detached = False
        self.attach_parent = attach_parent
        self.detached_window = QWidget()
        # self.detached_window.setStyleSheet("border: 1px solid blue")
        self.detached_window.setLayout(QVBoxLayout())
        self.detached_window.layout().setContentsMargins(QMargins())
        self.detached_window.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)

        def tool_selected(tool):
            self.plot_canvas.set_mouse_mode(tool)

        def detach():
            if self.detached:
                self.setParent(self.attach_parent)
                self.detached_window.hide()
                self.detached = False
            else:
                self.attach_parent = self.parent()
                self.setParent(self.detached_window)
                self.detached_window.layout().addWidget(self)
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


