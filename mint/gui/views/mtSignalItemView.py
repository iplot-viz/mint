# Description: A generic signal item viewer. Supports QTableView and QTreeView with options for columns.
# Author: Jaswant Panchumarti

import json
import typing
from functools import partial

from PySide2.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide2.QtWidgets import QAbstractItemView, QAction, QActionGroup, QMenu, QVBoxLayout, QTableView, QTreeView, QVBoxLayout, QWidget

class MTSignalItemView(QWidget):
    def __init__(self, title='SignalView', view_type: typing.Union[QTableView, QTreeView]=QTableView, parent: typing.Optional[QWidget] = None, f: Qt.WindowFlags = Qt.Widget):
        super().__init__(parent=parent, f=f)
        self.setWindowTitle(title)
        self.setLayout(QVBoxLayout())
        
        self._view = view_type(parent=self) # type: QAbstractItemView
        self._config_cols_menu = QMenu('', self)
        self._actions = [] # to avoid unexpected deletion of c++ actions
        
        self.layout().addWidget(self._view)

    def view(self) -> QAbstractItemView:
        return self._view

    def configureColsMenu(self) -> QActionGroup:
        return self._config_cols_menu

    def setModel(self, model: QAbstractItemModel):
        self._view.setModel(model)

        # remove old actions.
        for act in self._actions:
            self._config_cols_menu.removeAction(act)
        self._actions.clear()
        
        # add new actions and keep a reference on python side.
        for column in range(model.columnCount(QModelIndex())):
            column_name = model.headerData(column, Qt.Horizontal, Qt.DisplayRole)
            act = QAction(column_name)
            act.setCheckable(True)
            act.toggled.connect(partial(self.toggleColumn, column))
            act.setChecked(True)
            self._actions.append(act)

        # fill menu with actions.
        self._config_cols_menu.addActions(self._actions)

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
            act = self._actions[column]
            if isinstance(act, QAction):
                options.update({column_name: act.isChecked()})
        return options

    def import_dict(self, options: dict):
        for column in range(self.model().columnCount(QModelIndex())):
            column_name = self.model().headerData(column, Qt.Horizontal, Qt.DisplayRole)
            act = self._actions[column]
            if isinstance(act, QAction):
                act.setChecked(options.get(column_name))

    def export_json(self):
        return json.dumps(self.export_dict())

    def import_json(self, input_file):
        self.import_dict(json.loads(input_file))
        