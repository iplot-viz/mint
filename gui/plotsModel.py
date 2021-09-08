import typing

from qtpy.QtCore import QAbstractTableModel, QModelIndex, Qt

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


    def _expand_model(self, source):
        """Pad each array row with empty strings to self.columns length """
        if source is not None:
            for row in source:
                if len(row) < self.columns:
                    row += [''] * (self.columns - len(row))
        return source

    def set_model(self, model):
        self.removeRows(0, self.rowCount(QModelIndex()))
        self.model = self._expand_model(model)
        self._add_empty_row()


