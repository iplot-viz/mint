from iplotDataAccess.dataAccess import DataAccess
import numpy as np
import pandas
from collections import namedtuple
from datetime import datetime

from qtpy import QtGui
from qtpy.QtCore import QMargins, Signal
from qtpy.QtWidgets import QFileDialog, QMenu, QMessageBox, QStyle, QTabWidget, QTableView, QVBoxLayout, QWidget

from iplotlib.core.axis import LinearAxis
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.data_access.dataAccessSignal import DataAccessSignal
from iplotProcessing.core import Context, Processor

from gui.plotsModel import PlotsModel
from gui.variablesToolbar import VairablesToolbar
from common import converters, table_helper, time_helper

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)


SignalDescription = namedtuple('SignalDescription',
                               ['signals', 'col_num', 'row_num', 'stack_num', 'row_span',
                                   'col_span', 'pulsenb', 'start_ts', 'end_ts'],
                               defaults=[None, 0, 0, 0, 1, 1, None, None, None])
PlotDescription = namedtuple('PlotDescription', [
                             'row_span', 'col_span', 'x_range', 'signals'], defaults=[None])


def _get_begin_end(time_model):
    """Extract begin and end timestamps if present in time_model"""
    def str_to_ts(val): return np.datetime64(val, 'ns').astype('int').item()

    if time_model is not None:
        if 'ts_start' in time_model and 'ts_end' in time_model:
            return str_to_ts(time_model['ts_start']), str_to_ts(time_model['ts_end'])
        elif 'relative' in time_model:
            end = int(np.datetime64(datetime.utcnow(), 'ns').astype('int64'))
            start = end - 10 ** 9 * \
                int(time_model.get('relative')) * time_model.get('base')
            return start, end
    return None, None


def _get_pulse_number(time_model):
    """Extracts pulse numbers if present in time_model """
    if time_model is not None and 'pulsenb' in time_model:
        return time_model['pulsenb']
    return None


class VariablesTable(QWidget):
    canvasChanged = Signal(Canvas)

    def __init__(self, context: Context, data_access: DataAccess, model: dict, header: dict, plot_class=PlotXY,
                 signal_class=DataAccessSignal, default_dec_samples=1000, parent=None):
        super().__init__(parent)

        self.context = context
        self.data_access = data_access
        self.plot_class = plot_class
        self.signal_class = signal_class
        self.default_dec_samples = default_dec_samples
        self.header = header
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.table_model = PlotsModel(self.header, initial_model=model)

        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)

        self.toolbar = VairablesToolbar()
        self.toolbar.exportCsv.connect(self.export_clicked)
        self.toolbar.importCsv.connect(self.import_clicked)

        self.tab = QWidget()
        self.tab.setLayout(QVBoxLayout())
        self.tab.layout().setContentsMargins(QMargins())
        self.tab.layout().addWidget(self.toolbar)
        self.tab.layout().addWidget(self.table_view)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.tab, "Data")

        self.layout().addWidget(self.tab_widget)

    def export_clicked(self):
        file = QFileDialog.getSaveFileName(self, "Save CSV")
        if file and file[0]:
            self.export_csv(file[0])

    def import_clicked(self):
        file = QFileDialog.getOpenFileName(self, "Open CSV")
        if file and file[0]:
            self.import_csv(file[0])

    def remove_row(self):
        selected_rows = [
            e.row() for e in self.table_view.selectionModel().selectedIndexes()]
        for row in reversed(sorted(selected_rows)):
            self.table_model.removeRow(row)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        context_menu = QMenu(self)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_TrashIcon")), "Remove", self.remove_row)
        context_menu.popup(event.globalPos())

    def _create_signals(self, row, time_model=None, ts_start=None, ts_end=None, pulsenb=None):

        if row and table_helper.get_value(self.header, row, "DataSource") and table_helper.get_value(self.header, row, "Variable"):
            signal_title = table_helper.get_value(self.header, row, "Alias") or None
            if signal_title is not None and signal_title.isspace():
                signal_title = None

            signal_pulsenb = pulsenb or None
            signal_start_ts = ts_start or None
            signal_end_ts = ts_end or None

            # this "or" here will cause 0 to convert to None
            start_ts_override = table_helper.get_value(self.header, row, "StartTime", time_helper.parse_timestamp)
            end_ts_override = table_helper.get_value(self.header, row, "EndTime", time_helper.parse_timestamp)
            pulsenb_override = table_helper.get_value(self.header, row, "PulseNumber", converters.str_to_arr)

            # If any of the override values is set we discard values from RangeSelector
            # if start_ts_override is not None or end_ts_override is not None or pulsenb_override is not None:
            #     signal_pulsenb = pulsenb_override
            #     signal_start_ts = start_ts_override
            #     signal_end_ts = end_ts_override

            ts_threshold = 10**10

            if pulsenb_override is not None:
                signal_pulsenb = pulsenb_override
                signal_start_ts = start_ts_override
                signal_end_ts = end_ts_override

            signal_params = dict(datasource=table_helper.get_value(self.header, row, "DataSource"),
                                 title=signal_title,
                                 varname=table_helper.get_value(self.header, row, "Variable"),
                                 envelope=table_helper.get_value(self.header, row, "Envelope"),
                                 dec_samples=table_helper.get_value(self.header, 
                                     row, "DecSamples", int) or self.default_dec_samples,
                                 ts_start=signal_start_ts,
                                 ts_end=signal_end_ts
                                 )

            # xexpr = utility.get_value(self.header, row, "x") or DEFAULT_X
            # yexpr = utility.get_value(self.header, row, "y") or DEFAULT_Y
            # zexpr = utility.get_value(self.header, row, "z") or DEFAULT_Z

            if signal_params.get("envelope") == '0':
                signal_params.update({"envelope": False})
            elif signal_params.get("envelope") == '':
                signal_params.update({"envelope": False})
            else:
                signal_params.update({"envelope": True})

            signals = []
            if signal_pulsenb is not None and len(signal_pulsenb) > 0:
                for e in signal_pulsenb:
                    signal = self.signal_class(
                        **signal_params, pulsenb=e, ts_relative=True)
                    # signal.xexpr = xexpr
                    # signal.yexpr = yexpr
                    # signal.zexpr = zexpr
                    signal_params["title"] = signal.title
                    p = Processor()
                    p.setParamsA(**signal_params)
                    p.params.update({"pulsenb": e, "ts_relative": True})
                    # signal.data_fetch_callback = self.context.setInputData
                    # signal.data_processing_callback = self.context.getOutputData
                    signals.append(signal)
                    self.context.register(p)
            else:
                signal = self.signal_class(**signal_params, ts_relative=False)
                # signal.xexpr = xexpr
                # signal.yexpr = yexpr
                # signal.zexpr = zexpr
                signal_params["title"] = signal.title
                # signal.data_fetch_callback = self.context.setInputData
                # signal.data_processing_callback = self.context.getOutputData
                signals.append(signal)
                p = Processor()
                p.setParamsA(**signal_params)
                p.params.update({"ts_relative": False})
                self.context.register(p)

            stack_val = str(table_helper.get_value(self.header, row, "Stack")).split('.')
            col_num = int(stack_val[0]) if len(
                stack_val) > 0 and stack_val[0] else 1
            row_num = int(stack_val[1]) if len(
                stack_val) > 1 and stack_val[1] else 1
            stack_num = int(stack_val[2]) if len(
                stack_val) > 2 and stack_val[2] else 1

            row_span = table_helper.get_value(self.header, row, "RowSpan") or 1
            col_span = table_helper.get_value(self.header, row, "ColSpan") or 1

            return SignalDescription(signals=signals, col_num=int(col_num), row_num=int(row_num), stack_num=int(stack_num),
                                     row_span=int(row_span), col_span=int(col_span), pulsenb=signal_pulsenb, start_ts=signal_start_ts, end_ts=signal_end_ts)
            # return signals, int(col_num), int(row_num), int(stack_num), int(row_span), int(col_span), signal_pulsenb, signal_start_ts, signal_end_ts

        else:
            return SignalDescription()

    def create_canvas(self, time_model=None, stream_window=None):
        model = {}
        self.context.reset()

        x_axis_date = False if time_model is not None and 'pulsenb' in time_model else True
        x_axis_follow = True if time_model is None else False
        x_axis_window = stream_window if time_model is None else None

        refresh_interval = time_model.get(
            'auto_refresh')*60 if time_model is not None and 'auto_refresh' in time_model else 0
        pulse_number = _get_pulse_number(time_model)
        if stream_window is not None and stream_window > 0:
            now = np.datetime64(datetime.utcnow(), 'ns').astype('int').item()
            (ts_start, ts_end) = now, now - stream_window

        else:
            (ts_start, ts_end) = _get_begin_end(time_model)

        logger.info(F"Creating canvas ts_start={ts_start} ts_end={ts_end} pulsenb={pulse_number} stream_window={stream_window}")

        for row in self.table_model.model:
            desc = self._create_signals(
                row, time_model, ts_start, ts_end, pulse_number)

            if desc.signals:
                if desc.col_num not in model:
                    model[desc.col_num] = {}
                if desc.row_num not in model[desc.col_num]:
                    model[desc.col_num][desc.row_num] = [desc.row_span,
                                                         desc.col_span, {}, [desc.start_ts, desc.end_ts]]
                else:
                    existing = model[desc.col_num][desc.row_num]
                    existing[0] = desc.row_span if desc.row_span > existing[0] else existing[0]
                    existing[1] = desc.col_span if desc.col_span > existing[1] else existing[1]

                    if desc.start_ts is not None or desc.end_ts is not None:
                        if existing[3][0] is None or desc.start_ts < existing[3][0]:
                            existing[3][0] = desc.start_ts
                        if existing[3][1] is None or desc.end_ts > existing[3][1]:
                            existing[3][1] = desc.end_ts

                if desc.stack_num not in model[desc.col_num][desc.row_num][2]:
                    model[desc.col_num][desc.row_num][2][desc.stack_num] = []
                for signal in desc.signals:
                    model[desc.col_num][desc.row_num][2][desc.stack_num].append(
                        signal)

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
                        y_axes = [LinearAxis()
                                  for _ in range(len(rows[row + 1][2].items()))]

                        x_axis = LinearAxis(
                            is_date=x_axis_date, follow=x_axis_follow, window=x_axis_window)

                        if rows[row+1][3][0] is not None and rows[row+1][3][1] is not None:
                            x_axis.begin = rows[row+1][3][0]
                            x_axis.end = rows[row+1][3][1]
                            x_axis.original_begin = x_axis.begin
                            x_axis.original_end = x_axis.end

                        plot = self.plot_class(axes=[x_axis, y_axes], row_span=rows[row + 1][0],
                                               col_span=rows[row + 1][1])
                        for stack, signals in rows[row + 1][2].items():
                            for signal in signals:
                                plot.add_signal(signal, stack=stack)
                    canvas.add_plot(plot, col=colnum - 1)

        return canvas

    def export_csv(self, file_path=None):
        try:
            df = pandas.DataFrame(self.table_view.model().model[:-1])
            return df.to_csv(file_path, header=self.table_view.model().column_names, index=False)
        except:
            logger.info("Error when dumping variables to file:")

    def import_csv(self, file_path):
        try:
            df = pandas.read_csv(file_path, dtype=str, keep_default_na=False)
            if not df.empty:
                self.table_view.model().set_model(df.values.tolist())
        except:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText("Error parsing file")
            box.exec_()

    def export_json(self):
        df = pandas.DataFrame(self.table_view.model().model[:-1])
        return df.to_json(orient='values')

    def import_json(self, json_payload):
        df = pandas.read_json(json_payload, dtype=str, orient='values')
        if not df.empty:
            self.table_view.model().set_model(df.values.tolist())
