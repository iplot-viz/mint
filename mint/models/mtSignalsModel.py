# Description: A light-weight translation of a dataframe to benefit QTableView
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import json
import pandas as pd
import typing

from PySide2.QtCore import QAbstractItemModel, QCoreApplication, QModelIndex, Qt

from iplotlib.interface.iplotSignalAdapter import IplotSignalAdapter, Result

from mint.models.utils import mtBlueprintParser as mtbp
from mint.tools.table_parser import get_value

import iplotLogging.setupLogger as ls

from numpy.core.shape_base import stack

logger = ls.get_logger(__name__)


@dataclass
class Waypoint:
    idx: int = -1
    col_num: int = -1
    row_num: int = -1
    col_span: int = -1
    row_span: int = -1
    stack_num: int = -1
    signal_stack_id: int = -1
    ts_start: int = -1
    ts_end: int = -1
    func: typing.Callable = None
    args: list = None
    kwargs: dict = None

    def __str__(self):
        return f"c:{self.col_num}|r:{self.row_num}|sn:{self.stack_num}|si:{self.signal_stack_id}"


class MTSignalsModel(QAbstractItemModel):
    SignalRole = Qt.UserRole + 10

    def __init__(self, blueprint: dict = mtbp.DEFAULT_BLUEPRINT, signal_class: type = IplotSignalAdapter, parent=None):

        super().__init__(parent)

        column_names = list(mtbp.get_column_names(blueprint))

        self._blueprint = blueprint
        mtbp.parse_raw_blueprint(self._blueprint)

        self._table = pd.DataFrame(columns=column_names)
        self._signal_class = signal_class
        self._signal_stack_ids = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int)))

    @property
    def blueprint(self) -> dict:
        return self._blueprint

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        return self.createIndex(row, column)

    def parent(self, child: QModelIndex) -> QModelIndex:
        return QModelIndex()

    def rowCount(self, parent: QModelIndex):
        return self._table.index.size

    def columnCount(self, parent: QModelIndex):
        return self._table.columns.size

    def data(self, index: QModelIndex, role: int = ...):
        if index.isValid():
            if role == Qt.DisplayRole or role == Qt.EditRole:
                return self._table.iloc[index.row()][index.column()]

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            try:
                return self._table.columns[section]
            except IndexError:
                return "N/A"

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if index.isValid():
            if role == Qt.EditRole or role == Qt.DisplayRole:

                if ',' in value:
                    # replaces " with ' if value has , in it.
                    value.replace('"', "'")

                self._table.iloc[index.row()][index.column()] = value

                self.dataChanged.emit(self.createIndex(0, 0), self.createIndex(
                    self._table.index.size, self._table.columns.size))

                return True
            else:
                return False
        else:
            return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if index.isValid():
            if index.column() != self._table.columns.size - 1:
                return Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled
            else:
                return Qt.ItemIsEnabled

    def insertRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        self.beginInsertRows(parent, row, row + count)

        for _ in range(count):
            data = [["" for _ in range(len(self._table.columns))]]
            empty_row = pd.DataFrame(data=data, columns=self._table.columns)
            empty_row.loc[0, mtbp.get_column_name(
                self.blueprint, 'DataSource')] = self.blueprint.get('DataSource').get('default')
            self._table = self._table.append(empty_row).reset_index(drop=True)
            self.layoutChanged.emit()

        self.endInsertRows()

        return super().insertRows(row, count, parent=parent)

    def removeRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        self.beginRemoveRows(parent, row, row + count)

        try:
            self._table = self._table.drop(
                list(range(row, row + count)), axis=0).reset_index(drop=True)
            self.layoutChanged.emit()
            success = True
        except KeyError:
            success = False

        self.endRemoveRows()

        return success

    def get_dataframe(self):
        return self._table

    def set_dataframe(self, df: pd.DataFrame):
        self.removeRows(0, self.rowCount(None))
        self.insertRows(0, df.index.size)

        # Accomodate for missing columns in df.
        columns = list(mtbp.get_column_names(self._blueprint))
        for df_column_name in df.columns:
            if df_column_name not in columns:
                logger.warning(f"{df_column_name} is not a valid column name.")
                if df_column_name in self._blueprint.keys():
                    df.rename({df_column_name: mtbp.get_column_name(
                        self._blueprint, df_column_name)}, axis=1, inplace=True)

        for r, row in df.iterrows():
            for c, col_name in enumerate(columns):
                val = ''
                if col_name in df.columns:
                    val = row[col_name]
                elif col_name.lower() in df.columns:
                    val = row[col_name.lower()]
                elif col_name.upper() in df.columns:
                    val = row[col_name.upper()]
                elif col_name.capitalize() in df.columns:
                    val = row[col_name.capitalize()]
                else:
                    logger.debug(
                        f"{col_name} is not present in given dataframe.")
                self._table.iloc[r, c] = val

    def export_dict(self) -> dict:
        # 1. blueprint defines columns..
        output = dict()
        output.update({'blueprint': mtbp.remove_type_info(self.blueprint)})
        # 2. table
        output.update(
            {'table': json.loads(self.get_dataframe().to_json(orient='values'))})
        return output

    def import_dict(self, input_dict: dict):
        # 1. blueprint defines columns..
        try:
            self._blueprint = mtbp.parse_raw_blueprint(input_dict['blueprint'])
        except KeyError:
            pass
        # 2. table
        column_names = list(mtbp.get_column_names(self.blueprint))
        self._entity_attribs = list(mtbp.get_code_names(self.blueprint))
        if input_dict.get('table'):
            df = pd.DataFrame(input_dict.get('table'),
                              dtype=str, columns=column_names)
        elif input_dict.get('variables_table'): # old style.
            df = pd.DataFrame(input_dict.get('variables_table'), dtype=str)
            df.set_axis(column_names[:df.columns.size], axis=1, inplace=True)
        else:
            raise Exception('No variables table in workspace!')
        if not df.empty:
            self.set_dataframe(df)

    def export_json(self):
        return json.dumps(self.export_dict())

    def import_json(self, input_file):
        self.import_dict(json.loads(input_file))

    def update_signal_data(self, row_idx: int, signal: IplotSignalAdapter, fetch_data=False):
        signal.status_info.reset()
        self.setData(self.createIndex(
            row_idx, self._table.columns.size - 1), Result.BUSY, Qt.DisplayRole)
        QCoreApplication.processEvents()

        if fetch_data:
            self.setData(self.createIndex(
                row_idx, self._table.columns.size - 1), Result.BUSY, Qt.DisplayRole)
            QCoreApplication.processEvents()
            signal.get_data()

        self.setData(self.createIndex(
            row_idx, self._table.columns.size - 1), str(signal.status_info), Qt.DisplayRole)
        QCoreApplication.processEvents()

    @contextmanager
    def init_create_signals(self):
        try:
            self._signal_stack_ids.clear()
            yield None
        finally:
            self._signal_stack_ids.clear()

    def create_signals(self, row_idx: int) -> typing.Iterator[Waypoint]:
        signal_params = dict()
        col_span = row_span = stack_num = 1
        col_num = row_num = 0
        ts_start = ts_end = -1

        for i, parsed_row in enumerate(self._parse_series(self._table.loc[row_idx])):
            signal_params.update(
                mtbp.construct_params_from_series(self.blueprint, parsed_row))

            if i == 0:  # grab these from the first row we counter.
                stack_val = signal_params.get('stack_val').split('.')
                col_num = int(stack_val[0]) if len(
                    stack_val) > 0 and stack_val[0] else 0
                row_num = int(stack_val[1]) if len(
                    stack_val) > 1 and stack_val[1] else 0
                stack_num = int(stack_val[2]) if len(
                    stack_val) > 2 and stack_val[2] else 1
                col_span = signal_params.get('col_span') or 1
                row_span = signal_params.get('row_span') or 1
                ts_start = signal_params.get('ts_start')
                ts_end = signal_params.get('ts_end')

            waypoint = Waypoint(row_idx,
                                col_num,
                                row_num,
                                col_span,
                                row_span,
                                stack_num,
                                self._signal_stack_ids[col_num][row_num][stack_num],
                                ts_start,
                                ts_end,
                                func=mtbp.construct_signal,
                                args=[self.blueprint],
                                kwargs={
                                    'signal_class': self._signal_class, **signal_params}
                                )
            self._signal_stack_ids[col_num][row_num][stack_num] += 1
            yield waypoint

    def _parse_series(self, inp: pd.Series) -> typing.Iterator[pd.Series]:

        out = dict()
        override_global = False

        for k, v in self._blueprint.items():
            if k.startswith('$'):
                continue

            type_func = v.get('type')

            if not callable(type_func):
                continue

            column_name = mtbp.get_column_name(self._blueprint, k)
            default_value = v.get('default')

            # Override global values with locals for fields with 'override' attribute
            if v.get('override'):
                override_global |= (
                    get_value(inp, column_name, type_func) is not None)
                if override_global:
                    value = get_value(inp, column_name, type_func)
                else:
                    value = default_value
            else:
                value = get_value(inp, column_name, type_func) or default_value

            out.update({column_name: value})

        for k, v in out.items():
            if isinstance(v, list) and len(v) > 0:
                for member in v:
                    out.update({k: member})
                    yield pd.Series(out)
                break
        else:
            yield pd.Series(out)
