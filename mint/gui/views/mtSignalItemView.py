# Description: A generic signal item viewer. Supports QTableView and QTreeView with options for columns.
# Author: Jaswant Panchumarti

import json
from typing import Optional, Type, Union
from functools import partial

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QMenu, QTableView, QTreeView, QVBoxLayout, QWidget, \
    QWidgetAction

from mint.models.mtSignalsModel import MTSignalsModel


class MTSignalItemView(QWidget):
    def __init__(self, title='SignalView',
                 view_type: Union[Type[QTableView], Type[QTreeView]] = QTableView,
                 parent: Optional[QWidget] = None, f: Qt.WindowFlags = Qt.WindowType.Widget):
        super().__init__(parent=parent, f=f)
        self.setWindowTitle(title)
        self.setLayout(QVBoxLayout())

        self._view = view_type(parent=self)
        self._menu = QMenu('', self)
        self._actions = []  # to avoid unexpected deletion of c++ actions

        self.layout().addWidget(self._view)

    def view(self) -> QAbstractItemView:
        return self._view

    def header_menu(self) -> QMenu:
        return self._menu

    def set_model(self, model: QAbstractItemModel):
        self._view.setModel(model)

        # remove old actions.
        for act in self._actions:
            if act is not None:
                self._menu.removeAction(act)
        self._actions.clear()

        # add new actions and keep a reference on python side.
        for column in range(model.columnCount(QModelIndex())):
            column_name = model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            if column_name == MTSignalsModel.ROWUID_COLNAME:
                self.toggle_column(column, False)
                self._actions.append(None)  # None for keep aligned index
            else:
                cbox = QCheckBox(column_name, self._menu)
                cbox.setChecked(True)
                act = QWidgetAction(self._menu)
                act.setDefaultWidget(cbox)
                cbox.toggled.connect(partial(self.toggle_column, column))
                self._actions.append(act)

        # fill menu with actions
        for act in self._actions:
            if act is not None:
                self._menu.addAction(act)
        self._menu.setContentsMargins(5, 0, 0, 0)

    def toggle_column(self, column: int, state: bool):
        if state:
            self._view.showColumn(column)
            self._view.resizeColumnsToContents()
        else:
            self._view.hideColumn(column)

    def model(self):
        return self._view.model()

    def export_dict(self) -> dict:
        options = dict()
        for column in range(self.model().columnCount(QModelIndex())):
            column_name = self.model().headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            if column_name != MTSignalsModel.ROWUID_COLNAME:
                act = self._actions[column]
                if isinstance(act, QWidgetAction):
                    options.update({column_name: act.defaultWidget().isChecked()})
        return options

    def import_dict(self, options: dict):
        for column in range(self.model().columnCount(QModelIndex())):
            column_name = self.model().headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            if column_name != MTSignalsModel.ROWUID_COLNAME:
                act = self._actions[column]
                if isinstance(act, QWidgetAction):
                    act.defaultWidget().setChecked(options.get(column_name, True))

    def export_json(self):
        return json.dumps(self.export_dict())

    def import_json(self, input_file):
        self.import_dict(json.loads(input_file))
