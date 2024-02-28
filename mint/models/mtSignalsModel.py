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
import re
import uuid

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from iplotlib.interface.iplotSignalAdapter import IplotSignalAdapter, Result

from mint.models.utils import mtBlueprintParser as mtBP
from mint.tools.table_parser import get_value

import iplotLogging.setupLogger as setupLog

logger = setupLog.get_logger(__name__)


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


exp_stack = re.compile(r'(\d+)(?:[.](\d+))?(?:[.](\d+))?$')


class MTSignalsModel(QAbstractItemModel):
    SignalRole = Qt.UserRole + 10

    ROWUID_COLNAME = 'uid'

    def __init__(self, blueprint: dict = mtBP.DEFAULT_BLUEPRINT, signal_class: type = IplotSignalAdapter, parent=None):

        super().__init__(parent)

        self._entity_attribs = None
        column_names = list(mtBP.get_column_names(blueprint))

        self._blueprint = blueprint

        # When true, do not emit `dataChanged` in `setData`. That signal brings `setData` to its knees.
        self._fast_mode = False
        mtBP.parse_raw_blueprint(self._blueprint)

        self._table = pd.DataFrame(columns=column_names)
        self._signal_class = signal_class
        self._signal_stack_ids = defaultdict(            lambda: defaultdict(lambda: defaultdict(int)))

    @property
    def blueprint(self) -> dict:
        return self._blueprint

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        return self.createIndex(row, column)

    def parent(self, child: QModelIndex) -> QModelIndex:
        return QModelIndex()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self._table.index.size

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self._table.columns.size

    def data(self, index: QModelIndex, role: int = ...):
        if index.isValid():
            value = self._table.iloc[index.row()][index.column()]
            if role == Qt.DisplayRole or role == Qt.EditRole:
                return value
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            try:
                return self._table.columns[section]
            except IndexError:
                return "N/A"

    @contextmanager
    def activate_fast_mode(self):
        try:
            self._fast_mode = True
            yield None
        finally:
            self._fast_mode = False

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if not index.isValid():
            return False
        row = index.row()
        column = index.column()
        if role != Qt.EditRole and role != Qt.DisplayRole:
            return False

        if isinstance(value, str):
            value = value.strip()
            if ',' in value:
                # replaces " with ' if value has , in it.
                value = value.replace('"', "'")

        if row + 1 >= self._table.index.size:
            self.insertRows(row + 1, 1, QModelIndex())
        self._table.iloc[row, column] = value

        if not self._fast_mode:
            self.dataChanged.emit(self.createIndex(row, column), self.createIndex(row, column))

        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if index.isValid():
            if index.column() != self._table.columns.size - 1:
                return Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled
            else:
                return Qt.ItemIsEnabled

    def insertRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        self.beginInsertRows(parent, row, row + count)

        for new_row in range(row, row + count):
            # Create empty row
            data = [["" for _ in range(self._table.columns.size)]]
            empty_row = pd.DataFrame(data=data, columns=self._table.columns)
            # Set default Datasource
            empty_row.loc[0, mtBP.get_column_name(                self.blueprint, 'DataSource')] = self.blueprint.get('DataSource').get('default')
            # Generate uid
            empty_row.loc[0, self.ROWUID_COLNAME] = str(uuid.uuid4())
            self._table = pd.concat([self._table.iloc[:new_row],                                     empty_row,                                     self._table.iloc[new_row:]]).reset_index(drop=True)
        self.layoutChanged.emit()

        self.endInsertRows()

        return super().insertRows(row, count, parent=parent)

    def removeRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        self.beginRemoveRows(parent, row, row + count)

        try:
            self._table = self._table.drop(list(range(row, row + count)), axis=0).reset_index(drop=True)
            self.layoutChanged.emit()
            success = True
        except KeyError:
            success = False

        self.endRemoveRows()

        return success

    def get_dataframe(self):
        filtered_rows = self._table[self._table.iloc[:, 1:-3].any(axis=1)]
        if not filtered_rows.empty:
            max_idx = filtered_rows.index[-1]
            return self._table[:max_idx + 1]
        else:
            return pd.DataFrame(columns=self._table.columns)

    def remove_empty_rows(self):
        columns = ['Variable', 'Stack', 'Row span', 'Col span', 'Envelope', 'Alias', 'PulseId', 'StartTime', 'EndTime',
                   'x', 'y', 'z', 'Plot type', 'Status']
        self._table = self._table[(self._table[columns].isnull().sum(1) + (self._table[columns] == "").sum(1)) < 14]

    def accommodate(self, df: pd.DataFrame):
        # Accommodate for missing columns in df.
        columns = list(mtBP.get_column_names(self._blueprint))
        for df_column_name in df.columns:
            if df_column_name not in columns:
                if df_column_name == self.ROWUID_COLNAME:
                    # Generate missing UID
                    df.insert(df.columns.size, self.ROWUID_COLNAME,                              [str(uuid.uuid4()) for _ in range(df.index.size)])
                else:
                    logger.warning(f"{df_column_name} is not a valid column name.")
                    if df_column_name in self._blueprint.keys():
                        df.rename({df_column_name: mtBP.get_column_name(                            self._blueprint, df_column_name)}, axis=1, inplace=True)
                    elif df_column_name.lower() in columns:
                        df.rename({df_column_name: df_column_name.lower()}, axis=1, inplace=True)
                    elif df_column_name.upper() in columns:
                        df.rename({df_column_name: df_column_name.upper()}, axis=1, inplace=True)
                    elif df_column_name.capitalize() in columns:
                        df.rename({df_column_name: df_column_name.capitalize()}, axis=1, inplace=True)
                    else:
                        logger.warning(f"{df_column_name} is not possible to convert the column name.")
                        df.drop(df_column_name, axis=1, inplace=True)
        return df

    def set_dataframe(self, df: pd.DataFrame):
        oldSz = self.rowCount()
        self.removeRows(0, oldSz)
        newSz = df.index.size
        self.insertRows(0, newSz)

        df = self.accommodate(df)

        # Force blueprint to have uid column
        if not self._blueprint.get(self.ROWUID_COLNAME):
            self._blueprint[self.ROWUID_COLNAME] = {
                "code_name": "uid",
                "default": "",
                "label": "uid",
                "type_name": "str",
                "type": str
            }
        columns = list(mtBP.get_column_names(self._blueprint))

        for c, col_name in enumerate(columns):
            if col_name in df.columns:
                self._table.iloc[:df.index.size, c] = df.loc[:, col_name]
            else:
                logger.debug(f"{col_name} is not present in given dataframe.")
                continue

    def append_dataframe(self, df: pd.DataFrame):
        if df.empty:
            return
        df = self.accommodate(df)
        df['uid'] = [str(uuid.uuid4()) for _ in range(len(df.index))]

        self._table = pd.concat([self._table, df], ignore_index=True).fillna('')

        # Check if last row is empty
        if self._table.iloc[-1:, 1:-3].any(axis=1).bool():
            self.insertRows(0, 1, QModelIndex())

        self.layoutChanged.emit()

    def export_dict(self) -> dict:
        # 1. blueprint defines columns..
        output = dict()
        output.update({'blueprint': mtBP.remove_type_info(self.blueprint)})
        # 2. table
        output.update({'table': json.loads(self.get_dataframe().to_json(orient='values'))})
        return output

    def import_dict(self, input_dict: dict):
        # 1. blueprint defines columns..
        try:
            self._blueprint = mtBP.parse_raw_blueprint(input_dict['blueprint'])
            if not self._blueprint.get("PulseNumber").get("label"):
                self._blueprint.get("PulseNumber").update({"label": "PulseId"})
        except KeyError:
            pass
        # 2. table
        column_names = list(mtBP.get_column_names(self.blueprint))
        self._entity_attribs = list(mtBP.get_code_names(self.blueprint))
        if input_dict.get('table'):
            df = pd.DataFrame(input_dict.get('table'),                              dtype=str, columns=column_names)
        elif input_dict.get('variables_table'):  # old style.
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
        with self.activate_fast_mode():
            model_idx = self.createIndex(row_idx, self._table.columns.get_loc('Status'))
            signal.status_info.reset()
            self.setData(model_idx, str(signal.status_info), Qt.DisplayRole)

            if fetch_data:
                self.setData(model_idx, Result.BUSY, Qt.DisplayRole)
                signal.get_data()

            self.setData(model_idx, str(signal.status_info), Qt.DisplayRole)

    @contextmanager
    def init_create_signals(self):
        try:
            self._signal_stack_ids.clear()
            yield None
        finally:
            self._signal_stack_ids.clear()

    def create_signals(self, row_idx: int) -> typing.Iterator[Waypoint]:
        signal_params = dict()

        for i, parsed_row in enumerate(self._parse_series(self._table.loc[row_idx])):
            signal_params.update(mtBP.construct_params_from_series(self.blueprint, parsed_row))

            if i == 0:  # grab these from the first row we encounter.
                stack_val = signal_params.get('stack_val')
                stack_m = exp_stack.match(stack_val)

                if stack_m:
                    stack_groups = stack_m.groups()
                    row_num = int(stack_groups[0])
                    col_num = int(stack_groups[1] or '1')
                    stack_num = int(stack_groups[2] or '1')

                    bad_stack = col_num == 0 or row_num == 0 or stack_num == 0
                else:
                    bad_stack = True

                if bad_stack:
                    stack_num = 1
                    col_num = row_num = 0
                    if stack_val:
                        # This message for status?
                        logger.warning(f'Ignored wrong stack value: {stack_val}')

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
                                func=mtBP.construct_signal,
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

            column_name = mtBP.get_column_name(self._blueprint, k)
            default_value = v.get('default')
            if not default_value:
                if column_name == 'uid':
                    default_value = str(uuid.uuid4())
                elif default_value is None:
                    default_value = ""
            out.update({column_name: default_value})

            type_func = v.get('type')
            if not callable(type_func):
                continue

            # Override global values with locals for fields with 'override' attribute
            if v.get('override'):
                override_global |= (get_value(inp, column_name, type_func) is not None)
                if override_global:
                    value = get_value(inp, column_name, type_func)
                    if column_name == 'PulseId':
                        plus_pattern = re.compile(r"\+\((.*)\)")
                        minus_pattern = re.compile(r"-\((.*)\)")

                        # Lists to store the elements corresponding to every pattern
                        elements = [[], [], []]

                        # Iterar sobre la lista y clasificar los elementos
                        for element in value:
                            match_plus = plus_pattern.match(element)
                            match_minus = minus_pattern.match(element)
                            if match_plus:
                                elements[0].append(match_plus.group(1))
                            elif match_minus:
                                elements[1].append(match_minus.group(1))
                            else:
                                elements[2].append(element)

                        if len(elements[2]) == 0:
                            # Remove pulses from global
                            value = [i for i in default_value if i not in elements[1]]
                            # Add pulses from global
                            value.extend([i for i in elements[0] if i not in default_value])

                else:
                    value = default_value
            else:
                if k == 'DataSource':  # Do not read default value when parsing an already filled in table.
                    value = get_value(inp, column_name, type_func)
                else:
                    value = get_value(inp, column_name, type_func) or default_value

            out.update({column_name: value})

        for k, v in out.items():
            if isinstance(v, list) and len(v) > 0:
                for member in v:
                    serie = out.copy()
                    serie.update({k: member})
                    # Checks if there is more than one pulseId to change de uid of the signal
                    if "uid" in out and len(v) > 1:
                        # append pulse nb to uid to make it unique
                        serie['uid'] = str(uuid.uuid5(uuid.UUID(serie['uid']), member))
                    yield pd.Series(serie)
                break
        else:
            yield pd.Series(out)
