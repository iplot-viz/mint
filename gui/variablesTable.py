import json
import os
import typing
from functools import partial

import numpy as np
import pandas
from datetime import datetime
from qtpy import QtGui
from qtpy.QtCore import QAbstractTableModel, QMargins, QModelIndex, QStringListModel, Qt, Signal
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QComboBox, QDataWidgetMapper, QDateTimeEdit, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QRadioButton, \
    QSizePolicy, QSpinBox, QStackedWidget, QStyle, QTabWidget, QTableView, QToolBar, QVBoxLayout, QWidget
from iplotlib.core.axis import LinearAxis
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.data_access.dataAccessSignal import DataAccessSignal

import logging2.setupLogger as ls

logger = ls.get_logger(__name__)


def _get_begin_end(time_model):
    """Extract begin and end timestamps if present in time_model"""
    def str_to_ts(val): return np.datetime64(val, 'ns').astype('int').item()

    if time_model is not None:
        if 'ts_start' in time_model and 'ts_end' in time_model:
            return str_to_ts(time_model['ts_start']), str_to_ts(time_model['ts_end'])
        elif 'relative' in time_model:
            end = int(np.datetime64(datetime.utcnow(), 'ns').astype('int64'))
            start = end - 10 ** 9 * int(time_model.get('relative')) * time_model.get('base')
            return start, end
    return None, None


def _get_pulse_number(time_model):
    """Extracts pulse numbers if present in time_model """
    if time_model is not None and 'pulsenb' in time_model:
        return time_model['pulsenb']
    return None


class VariablesTable(QWidget):
    canvasChanged = Signal(Canvas)

    def __init__(self, parent=None, data_access=None, model=None, header=None, plot_class=PlotXY,
                 signal_class=DataAccessSignal, default_dec_samples=1000):
        super().__init__(parent)

        self.data_access = data_access
        self.plot_class = plot_class
        self.signal_class = signal_class
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

    def _create_signals(self, row, time_model=None, ts_start=None, ts_end=None, pulsenb=None):

        def get_value(data_row, key, type_func=str):
            value = data_row[list(self.header).index(key)]
            if value is not None and value != '':
                return type_func(value)
            return value

        if row and get_value(row, "DataSource") and get_value(row, "Variable"):
            signal_title = get_value(row, "Alias") or None
            if signal_title is not None and signal_title.isspace():
                signal_title = None

            signal_params = dict(datasource=get_value(row, "DataSource"),
                                 title=signal_title,
                                 varname=get_value(row, "Variable"),
                                 envelope=get_value(row, "Envelope"),
                                 dec_samples=get_value(row, "DecSamples", int) or self.default_dec_samples,
                                 ts_start=ts_start,
                                 ts_end=ts_end
                                 )

            if pulsenb is not None and len(pulsenb) > 0:
                signals = [self.signal_class(**signal_params, pulsenb=e, ts_relative=True) for e in pulsenb]
            else:
                signals = [self.signal_class(**signal_params, ts_relative=False)]

            stack_val = str(get_value(row, "Stack")).split('.')
            col_num = int(stack_val[0]) if len(stack_val) > 0 and stack_val[0] else 1
            row_num = int(stack_val[1]) if len(stack_val) > 1 and stack_val[1] else 1
            stack_num = int(stack_val[2]) if len(stack_val) > 2 and stack_val[2] else 1

            row_span = str(get_value(row, "RowSpan")) or 1
            col_span = str(get_value(row, "ColSpan")) or 1

            return signals, int(col_num), int(row_num), int(stack_num), int(row_span), int(col_span)
        else:
            return None, 0, 0, 0, 1, 1

    def create_canvas(self, time_model=None, stream_window=None):
        model = {}
        x_axis_date = False if time_model is not None and 'pulsenb' in time_model else True
        x_axis_follow = True if time_model is None else False
        x_axis_window = stream_window if time_model is None else None

        refresh_interval = time_model.get('auto_refresh')*60 if time_model is not None and 'auto_refresh' in time_model else 0
        pulse_number = _get_pulse_number(time_model)
        if stream_window is not None and stream_window > 0:
            now = np.datetime64(datetime.utcnow(), 'ns').astype('int').item()
            (ts_start, ts_end) = now, now - stream_window

        else:
            (ts_start, ts_end) = _get_begin_end(time_model)

        logger.info(F"Creating canvas ts_start={ts_start} ts_end={ts_end} pulsenb={pulse_number} stream_window={stream_window}")

        for row in self.table_model.model:
            signals, colnum, rownum, stacknum, row_span, col_span = \
                self._create_signals(row, time_model, ts_start, ts_end, pulse_number)

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
        canvas.auto_refresh = refresh_interval

        if model.keys():
            canvas.cols = max(model.keys())
            canvas.rows = max([max(e.keys()) for e in model.values()])
            canvas.plots = [[] for _ in range(canvas.cols)]

            for colnum, rows in model.items():
                for row in range(max(rows.keys())):
                    plot = None
                    if row + 1 in rows.keys():
                        y_axes = [LinearAxis() for _ in range(len(rows[row + 1][2].items()))]

                        x_axis = LinearAxis(is_date=x_axis_date, follow=x_axis_follow, window=x_axis_window)

                        if x_axis_date and ts_start is not None and ts_end is not None:
                            x_axis.begin = ts_start
                            x_axis.end = ts_end

                        plot = self.plot_class(axes=[x_axis, y_axes], row_span=rows[row + 1][0],
                                               col_span=rows[row + 1][1])
                        for stack, signals in rows[row + 1][2].items():
                            for signal in signals:
                                plot.add_signal(signal, stack=stack)
                    canvas.add_plot(plot, col=colnum - 1)

        return canvas

    def export_csv(self, file_path=None):
        try:
            df = pandas.DataFrame(self.uda_table_view.model().model[:-1])
            return df.to_csv(file_path, header=self.uda_table_view.model().column_names, index=False)
        except:
            logger.info("Error when dumping variables to file:")

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

    def import_json(self, json_payload):
        df = pandas.read_json(json_payload, dtype=str, orient='values')
        if not df.empty:
            self.uda_table_view.model().set_model(df.values.tolist())


class VairablesToolbar(QWidget):
    exportCsv = Signal()
    importCsv = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins())

        tb = QToolBar()
        tb.addAction(QIcon(os.path.join(os.path.dirname(__file__), "icons/open_file.png")), "Open CSV",
                     self.importCsv.emit)
        tb.addAction(QIcon(os.path.join(os.path.dirname(__file__), "icons/save_as.png")), "Save CSV",
                     self.exportCsv.emit)
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
        return None

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

    PULSE_NUMBER = "PULSE_NUMBER"
    TIME_RANGE = "TIME_RANGE"
    RELATIVE_TIME = "RELATIVE_TIME"

    TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"

    cancel_refresh = Signal()
    refresh_activate = Signal()
    refresh_deactivate = Signal()

    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        if model is None:
            model = {}
        self.model = model or {}
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum))

        self.forms = dict()
        self.selected = self.TIME_RANGE
        self.models = dict()

        self.radiogroup = QGroupBox()
        self.radiogroup.setSizePolicy(QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum))
        self.radiogroup.setLayout(QHBoxLayout())

        self._create_stacked_form()

    def add_form(self, label, widget):
        self.forms[label] = widget
        self.models[label] = None

    def get_model(self):
        model = self.items[self.stack.currentIndex()][3]
        return model()

    def export_json(self):
        return json.dumps(dict(mode=self.model.get('mode'), **self.get_model()))

    def import_json(self, json_string):
        loaded = json.loads(json_string)




        if loaded.get("ts_start") is not None and loaded.get("ts_end") is not None:
            self.stack.setCurrentIndex(0)
            self.radiogroup.layout().itemAt(0).widget().setChecked(True)
            mapper = self.items[self.stack.currentIndex()][4]
            mapper.model().setStringList([loaded.get("ts_start"), loaded.get("ts_end")])
            mapper.toFirst()

        elif loaded.get("pulsenb") is not None:
            self.stack.setCurrentIndex(1)
            self.radiogroup.layout().itemAt(1).widget().setChecked(True)
            mapper = self.items[self.stack.currentIndex()][4]
            mapper.model().setStringList([",".join(loaded.get("pulsenb"))])
            mapper.toFirst()

        elif loaded.get("relative") is not None:
            self.stack.setCurrentIndex(2)
            self.radiogroup.layout().itemAt(2).widget().setChecked(True)
            mapper = self.items[self.stack.currentIndex()][4]
            mapper.model().setStringList([str(loaded.get("relative")), str(loaded.get("base")), str(loaded.get("auto_refresh"))])
            mapper.toFirst()

    def _create_stacked_form(self):
        self.items = [self._create_timerange_form(), self._create_puslenumber_form(), self._create_relativerime_form()]

        self.stack = QStackedWidget()

        def switchForm(selected):
            self.stack.setCurrentIndex(selected)

        for idx, item in enumerate(self.items):
            self.stack.addWidget(item[2])
            button = QRadioButton(item[1])
            button.clicked.connect(partial(switchForm, idx))
            self.radiogroup.layout().addWidget(button)

            if self.model.get('mode') == item[0]:
                button.setChecked(True)
                self.stack.setCurrentIndex(idx)

        self.layout().addWidget(self.radiogroup)
        self.layout().addWidget(self.stack)

        if not self.model.get('mode'):
            self.stack.setCurrentIndex(0)
            self.radiogroup.layout().itemAt(0).widget().setChecked(True)

    def _create_puslenumber_form(self):
        form = QWidget()
        form.setLayout(QFormLayout())

        pulse_number = QLineEdit()

        model = QStringListModel(form)
        model.setStringList(
            self.model.get('value') if self.model.get('mode') == DataRangeSelector.PULSE_NUMBER and self.model.get(
                'value') else [''])

        mapper = QDataWidgetMapper(form)
        mapper.setOrientation(Qt.Vertical)
        mapper.setModel(model)
        mapper.addMapping(pulse_number, 0)
        mapper.toFirst()

        form.layout().addRow(QLabel("Pulse id"), pulse_number)

        def ret():
            return {"pulsenb": [e for e in model.stringList()[0].split(',')]}

        return DataRangeSelector.PULSE_NUMBER, "Pulse id", form, ret, mapper

    def _create_timerange_form(self):
        form = QWidget()
        form.setLayout(QFormLayout())

        from_time = QDateTimeEdit()
        from_time.setDisplayFormat(self.TIME_FORMAT)
        to_time = QDateTimeEdit()
        to_time.setDisplayFormat(self.TIME_FORMAT)

        model = QStringListModel(form)
        model.setStringList(
            self.model.get('value') if self.model.get('mode') == DataRangeSelector.TIME_RANGE and self.model.get(
                'value') else ['', ''])

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

        return DataRangeSelector.TIME_RANGE, "Time range", form, ret, mapper

    def _create_relativerime_form(self):
        form = QWidget()
        form.setLayout(QFormLayout())

        time_input = QSpinBox()
        time_input.setMinimum(0)
        time_input.setValue(1)

        options = [(1, "Second(s)"), (60, "Minute(s)"), (60*60, "Hour(s)"), (24*60*60, "Day(s)")]

        values = QStringListModel()
        values.setStringList([e[1] for e in options])

        relative_time = QComboBox()
        relative_time.setModel(values)

        cancel_button = QPushButton()
        cancel_button.setText("Cancel")
        cancel_button.setDisabled(True)
        cancel_button.clicked.connect(self.cancel_refresh.emit)

        self.refresh_activate.connect(partial(cancel_button.setDisabled, False))
        self.refresh_deactivate.connect(partial(cancel_button.setDisabled, True))

        model = QStringListModel(form)
        # model.setStringList(
        #     self.model.get('value') if self.model.get('mode') == DataRangeSelector.TIME_RANGE and self.model.get(
        #         'value') else ['', ''])



        refresh_input = QSpinBox()
        refresh_input.setMinimum(5)
        refresh_input.setValue(5)

        time_widget = QWidget()
        time_widget.setLayout(QHBoxLayout())
        time_widget.layout().setContentsMargins(QMargins())
        time_widget.layout().addWidget(time_input, 1)
        time_widget.layout().addWidget(relative_time, 2)

        refresh_widget = QWidget()
        refresh_widget.setLayout(QHBoxLayout())
        refresh_widget.layout().setContentsMargins(QMargins())
        refresh_widget.layout().addWidget(refresh_input, 1)
        refresh_widget.layout().addWidget(cancel_button, 2)

        form.layout().addRow(QLabel("Last"), time_widget)
        form.layout().addRow(QLabel("Refresh (mins)"), refresh_widget)

        mapper = QDataWidgetMapper(form)
        mapper.setOrientation(Qt.Vertical)
        mapper.setModel(model)
        mapper.addMapping(time_input, 0)
        mapper.addMapping(relative_time, 1)
        mapper.addMapping(refresh_input, 2)
        mapper.toFirst()


        def ret():
            return {"relative": int(time_input.value()), "base": options[relative_time.currentIndex()][0], "auto_refresh":int(refresh_input.value())}

        return DataRangeSelector.RELATIVE_TIME, "Relative", form, ret, mapper
