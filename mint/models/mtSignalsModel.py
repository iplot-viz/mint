# Description: A light-weight translation of a dataframe to benefit QTableView
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import os
import pandas as pd
import typing

from PySide2.QtCore import QAbstractTableModel, QModelIndex, Qt

from iplotProcessing.core import Environment
from iplotProcessing.core.environment import DEFAULT_BLUEPRINT_FILE

class MTSignalsModel(QAbstractTableModel):

    def __init__(self, blueprint: os.PathLike=DEFAULT_BLUEPRINT_FILE, parent=None):
        super().__init__()

        self._data = pd.DataFrame(columns=list(Environment(blueprint_file=blueprint).get_column_names()))
        self.add_empty_row()

    def columnCount(self, parent):
        return self._data.columns.size

    def rowCount(self, parent):
        return self._data.index.size

    def data(self, index: QModelIndex, role: int = ...):
        if index.isValid():
            if role == Qt.DisplayRole or role == Qt.EditRole:
                return self._data.iloc[index.row()][index.column()]
        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if role == Qt.EditRole:

            if ',' in value:
                value.replace('"', "'") # replaces " with ' if value has , in it.

            self._data.iloc[index.row()][index.column()] = value

            if index.row() == self._data.index.size - 1:
                self.add_empty_row()

            self.dataChanged.emit(self.createIndex(0, 0), self.createIndex(
                self._data.index.size, self._data.columns.size))

            return True
        else:
            return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            try:
                return self._data.columns[section]
            except IndexError:
                return "N/A"

    def add_empty_row(self):
        data = [["" for _ in range(self._data.columns.size)]]
        empty_row = pd.DataFrame(data=data, columns=self._data.columns)
        self._data = self._data.append(empty_row).reset_index(drop=True)
        self.layoutChanged.emit()

    def removeRow(self, row: int, parent=QModelIndex()) -> bool:
        if row < self._data.index.size:
            self._data = self._data.drop(row, axis=0).reset_index(drop=True)
            self.layoutChanged.emit()
            return True
        else:
            return False

    def get_dataframe(self) -> pd.DataFrame:
        return self._data.drop(self._data.tail(1).index)

    def set_dataframe(self, df: pd.DataFrame):
        self.removeRows(0, self.rowCount(QModelIndex()))
        self._data = df
        Environment.adjust_dataframe(self._data)
        self.add_empty_row()
