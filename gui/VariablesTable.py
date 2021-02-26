import json
import os
import typing
from functools import partial

import numpy as np
import pandas
from PyQt5 import QtGui
from PyQt5.QtCore import QAbstractTableModel, QMargins, QModelIndex, QStringListModel, QVariant, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QComboBox, QDataWidgetMapper, QDateTimeEdit, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QRadioButton, QSizePolicy, \
    QStackedWidget, QStyle, QTabWidget, QTableView, QToolBar, QVBoxLayout, QWidget
from iplotlib.Axis import LinearAxis
from iplotlib.Canvas import Canvas
from iplotlib.Plot import Plot2D
from iplotlib.Signal import UDAPulse


class VariablesTable(QWidget):

    canvasChanged = pyqtSignal(Canvas)

    def __init__(self, parent=None, data_access=None, model=None, header=None, plot_class=Plot2D, default_dec_samples=1000):
        super().__init__(parent)

        self.data_access = data_access
        self.plot_class = plot_class
        self.default_dec_samples = default_dec_samples
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


        uda_toolbar = VairablesToolbar()
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
            signal_params = dict(datasource=get_value(row, "DataSource"),
                                 title=get_value(row, "Alias") or None,
                                 varname=get_value(row, "Variable"),
                                 envelope=get_value(row, "Envelope"),
                                 dec_samples=get_value(row, "DecSamples") or self.default_dec_samples)

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

    def create_canvas(self, time_model=None, stream_window=3600):
        model = {}

        x_axis_date = False if time_model is not None and 'pulsenb' in time_model else True
        x_axis_follow = True if time_model is None else False
        x_axis_window = stream_window if time_model is None else None

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
        canvas.autoscale = False if x_axis_date else True

        if model.keys():
            canvas.cols = max(model.keys())
            canvas.rows = max([max(e.keys()) for e in model.values()])
            canvas.plots = [[] for _ in range(canvas.cols)]

            for colnum, rows in model.items():
                for row in range(max(rows.keys())):
                    plot = None
                    if row+1 in rows.keys():
                        y_axes = [LinearAxis() for _ in range(len(rows[row + 1][2].items()))]

                        if x_axis_date and time_model is not None:
                            x_axis = LinearAxis(is_date=x_axis_date, follow=x_axis_follow, window=x_axis_window,
                                                begin=np.datetime64(time_model.get('ts_start'), 'ns').astype('int').item(),
                                                end=np.datetime64(time_model.get('ts_end'), 'ns').astype('int').item())
                        else:
                            x_axis = LinearAxis(is_date=x_axis_date, follow=x_axis_follow, window=x_axis_window)

                        plot = self.plot_class(axes=[x_axis, y_axes], row_span=rows[row+1][0], col_span=rows[row+1][1])
                        for stack, signals in rows[row+1][2].items():
                            for signal in signals:
                                plot.add_signal(signal, stack=stack)
                    canvas.add_plot(plot, col=colnum-1)

        return canvas

    def export_csv(self, file_path=None):
        try:
            df = pandas.DataFrame(self.uda_table_view.model().model[:-1])
            return df.to_csv(file_path, header=self.uda_table_view.model().column_names, index=False)
        except:
            print("Error when dumping variables to file:")

    def import_csv(self, file_path):
        try:
            df = pandas.read_csv(file_path, dtype=str, keep_default_na=False)
            if not df.empty:
                self.uda_table_view.model().set_model(df.values.tolist())
        except:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText("Error parsing file")
            box.exec_()

    def export_json(self):
        df = pandas.DataFrame(self.uda_table_view.model().model[:-1])
        return df.to_json(orient='values')

    def import_json(self, json):
        df = pandas.read_json(json, dtype=str, orient='values')
        if not df.empty:
            self.uda_table_view.model().set_model(df.values.tolist())


class VairablesToolbar(QWidget):

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

class DataRangeSelector(QWidget):

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
        return model()

    def export_json(self):
        return json.dumps(self.get_model())

    def import_json(self, json_string):
        self.model = json.loads(json_string)

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
        model.setStringList(self.model.get('value') if self.model.get('mode') == DataRangeSelector.PULSE_NUMBER and self.model.get('value') else [''])

        mapper = QDataWidgetMapper(form)
        mapper.setOrientation(Qt.Vertical)
        mapper.setModel(model)
        mapper.addMapping(pulse_number, 0)
        mapper.toFirst()

        form.layout().addRow(QLabel("Pulse id"), pulse_number)

        def ret():
            return {"pulsenb": [e for e in model.stringList()[0].split(',')]}

        return DataRangeSelector.PULSE_NUMBER, "Pulse id", form, ret,

    def _createTimeRangeForm(self):
        form = QWidget()
        form.setLayout(QFormLayout())

        from_time = QDateTimeEdit()
        from_time.setDisplayFormat(self.TIME_FORMAT)
        to_time = QDateTimeEdit()
        to_time.setDisplayFormat(self.TIME_FORMAT)

        model = QStringListModel(form)
        model.setStringList(self.model.get('value') if self.model.get('mode') == DataRangeSelector.TIME_RANGE and self.model.get('value') else ['', ''])

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

        return DataRangeSelector.TIME_RANGE, "Time range", form, ret


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

        return DataRangeSelector.RELATIVE_TIME, "Relative", form, ret,
