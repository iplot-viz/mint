# Description: A generic signal item viewer. Supports QTableView and QTreeView with options for columns.
# Author: Jaswant Panchumarti

import json
import typing
from functools import partial

from PySide2.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide2.QtWidgets import QAbstractItemView, QCheckBox, QGroupBox, QHBoxLayout, QTableView, QTreeView, QVBoxLayout, QWidget

class MTSignalItemView(QWidget):
    def __init__(self, title='SignalView', view_type: typing.Union[QTableView, QTreeView]=QTableView, parent: typing.Optional[QWidget] = None, f: Qt.WindowFlags = Qt.Widget):
        super().__init__(parent=parent, f=f)
        self.setWindowTitle(title)
        self.setLayout(QVBoxLayout())
        
        self._view = view_type(parent=self) # type: QAbstractItemView
        self._options = QGroupBox(title, parent=self)
        
        self.layout().addWidget(self._options)
        self.layout().addWidget(self._view)

    def view(self):
        return self._view

    def setModel(self, model: QAbstractItemModel):
        self._view.setModel(model)
        self._options.setLayout(QHBoxLayout())
        for column in range(model.columnCount(QModelIndex())):
            column_name = model.headerData(column, Qt.Horizontal, Qt.DisplayRole)
            cb = QCheckBox(column_name)
            self._options.layout().addWidget(cb)
            cb.toggled.connect(partial(self.toggleColumn, column))
            cb.setChecked(True)
        self._options.layout().addStretch(1)

    def toggleColumn(self, column: int, state: bool):
        if state:
            self._view.showColumn(column)
        else:
            self._view.hideColumn(column)

    def model(self):
        return self._view.model()

    def export_dict(self) -> dict:
        options = dict()
        for column in range(self.model().columnCount(QModelIndex())):
            column_name = self.model().headerData(column, Qt.Horizontal, Qt.DisplayRole)
            widget = self._options.layout().itemAt(column).widget()
            if isinstance(widget, QCheckBox):
                options.update({column_name: widget.isChecked()})
        return options

    def import_dict(self, options: dict):
        for column in range(self.model().columnCount(QModelIndex())):
            column_name = self.model().headerData(column, Qt.Horizontal, Qt.DisplayRole)
            widget = self._options.layout().itemAt(column).widget()
            if isinstance(widget, QCheckBox):
                widget.setChecked(options.get(column_name))

    def export_json(self):
        return json.dumps(self.export_dict())

    def import_json(self, input_file):
        self.import_dict(json.loads(input_file))
        