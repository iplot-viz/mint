# Description: A GUI to configure signal parameters for data access and so on.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]
#  Sept 2021: Add iplotProcessing context [Jaswant Sai Panchumarti]

from collections import defaultdict
import json
import os
import pandas as pd
import numpy as np
import sys
import typing

from PySide6.QtCore import QCoreApplication, QMargins, QModelIndex, Qt, Signal, QItemSelectionModel
from PySide6.QtGui import QContextMenuEvent, QShortcut, QKeySequence, QPalette
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QStyle, \
    QTabWidget, QTableView, QVBoxLayout, QWidget, QLabel, QDialog, QLineEdit, QHBoxLayout

from iplotlib.interface.iplotSignalAdapter import IplotSignalAdapter, Result, StatusInfo
from iplotProcessing.tools.parsers import Parser

from iplotWidgets.variableBrowser.variableBrowser import VariableBrowser
from mint.gui.mtSignalToolBar import MTSignalsToolBar
from mint.gui.mtFindReplace import FindReplaceDialog
from mint.gui.views import MTDataSourcesDelegate, MTSignalItemView
from mint.models import MTSignalsModel
from mint.models.mtSignalsModel import Waypoint
from mint.models.utils import mtBlueprintParser as mtbp
from mint.tools.table_parser import is_non_empty_string

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)

# These variables act as a signle point reference to define the title of the tabs.
ALL_VIEW_NAME = "All"
DA_VIEW_NAME = "Data-Access"
PLAYOUT_VIEW_NAME = "Plot-Layout"
PROC_VIEW_NAME = "Data-Processing"

# This is a pre-defined state for the signal-views.
NEAT_VIEW = {
    ALL_VIEW_NAME: {
        "DS": True,
        "Variable": True,
        "Stack": True,
        "Row span": True,
        "Col span": True,
        "Envelope": True,
        "Alias": True,
        "PulseId": True,
        "StartTime": True,
        "EndTime": True,
        "x": True,
        "y": True,
        "z": True,
        "Plot type": True,
        "Status": True
    },
    DA_VIEW_NAME: {
        "DS": True,
        "Variable": True,
        "Stack": False,
        "Row span": False,
        "Col span": False,
        "Envelope": True,
        "Alias": True,
        "PulseId": True,
        "StartTime": True,
        "EndTime": True,
        "x": False,
        "y": False,
        "z": False,
        "Plot type": False,
        "Status": True
    },
    PLAYOUT_VIEW_NAME: {
        "DS": True,
        "Variable": True,
        "Stack": True,
        "Row span": True,
        "Col span": True,
        "Envelope": False,
        "Alias": True,
        "PulseId": False,
        "StartTime": False,
        "EndTime": False,
        "x": False,
        "y": False,
        "z": False,
        "Plot type": True,
        "Status": True
    },
    PROC_VIEW_NAME: {
        "DS": True,
        "Variable": True,
        "Stack": False,
        "Row span": False,
        "Col span": False,
        "Envelope": False,
        "Alias": True,
        "PulseId": True,
        "StartTime": True,
        "EndTime": True,
        "x": True,
        "y": True,
        "z": True,
        "Plot type": False,
        "Status": True
    }
}


class RowAliasType:
    Simple = 'SIMPLE'
    Mixed = 'MIXED'
    NoAlias = 'NOALIAS'


def _row_predicate(row: pd.Series, aliases: list, blueprint: dict) -> typing.Tuple[RowAliasType, str]:
    alias = row[mtbp.get_column_name(blueprint, 'Alias')]
    name = row[mtbp.get_column_name(blueprint, 'Variable')]

    alias_valid = is_non_empty_string(alias)

    p = Parser().set_expression(name)
    raw_name = True  # True: name does not consist of any pre-defined aliases
    if p.is_valid:
        raw_name &= all(
            [var not in aliases for var in list(p.var_map.keys())])

    if alias_valid and raw_name:
        return RowAliasType.Simple, name
    elif alias_valid and not raw_name:
        return RowAliasType.Mixed, name
    else:
        return RowAliasType.NoAlias, name


class MTSignalConfigurator(QWidget):
    progressChanged = Signal(float)
    statusChanged = Signal(str)
    buildAborted = Signal(str)
    showProgress = Signal()
    hideProgress = Signal()
    busy = Signal()
    ready = Signal()

    # add_dataframe = Signal(pd.DataFrame)

    def __init__(self, blueprint: dict = mtbp.DEFAULT_BLUEPRINT, csv_dir: os.PathLike = '.', data_sources: list = [],
                 signal_class: type = IplotSignalAdapter, parent=None):
        super().__init__(parent)

        self._signal_class = signal_class

        self._model = MTSignalsModel(
            blueprint=blueprint, signal_class=self._signal_class)

        self._csv_dir = csv_dir
        self.data_sources = data_sources
        self._toolbar = MTSignalsToolBar(parent=self)
        self._toolbar.openAction.triggered.connect(self.onImport)
        self._toolbar.appendAction.triggered.connect(self.onAppend)
        self._toolbar.saveAction.triggered.connect(self.onExport)
        self._toolbar.searchVarsBtn.clicked.connect(self.on_tree_view)

        self._signal_item_widgets = [MTSignalItemView(ALL_VIEW_NAME, parent=self),
                                     MTSignalItemView(DA_VIEW_NAME, parent=self),
                                     MTSignalItemView(
                                         PLAYOUT_VIEW_NAME, parent=self)]  # ,
        #  MTSignalItemView(PROC_VIEW_NAME, view_type=QTreeView, parent=self)]

        self._ds_delegate = MTDataSourcesDelegate(data_sources, self)
        self._tabs = QTabWidget(parent=self)
        self._tabs.setMovable(True)

        self.parseBtn = QPushButton("Parse", self)
        self.parseBtn.clicked.connect(self.onParseButtonPressed)

        for wdgt in self._signal_item_widgets:
            wdgt.setModel(self._model)
            wdgt.import_dict(NEAT_VIEW.get(wdgt.windowTitle()))
            self._tabs.addTab(wdgt, wdgt.windowTitle())
            wdgt.view().setItemDelegateForColumn(0, self._ds_delegate)

        self._tabs.currentChanged.connect(self.onCurrentViewChanged)
        # Set menu for configure columns button.
        self._toolbar.configureColsBtn.setMenu(self._signal_item_widgets[0].headerMenu())

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.layout().addWidget(self._toolbar)
        self.layout().addWidget(self._tabs)
        self.layout().addWidget(self.parseBtn)

        self.model.dataChanged.connect(self.resizeViewToColumns)

        self.selectVarDialog = VariableBrowser()

        self.selectVarDialog.cmd_finish.connect(self.append_dataframe)

        self.model.insertRows(0, 1, QModelIndex())
        self._find_replace_dialog = None

        shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        shortcut.activated.connect(self.copyContentsToClipboard)
        shortcut2 = QShortcut(QKeySequence("Ctrl+V"), self)
        shortcut2.activated.connect(self.pasteContentsFromClipboard)

    def onCurrentViewChanged(self, index: int):
        currentView = self.itemWidgets[index]
        self._toolbar.configureColsBtn.setMenu(currentView.headerMenu())

    def onParseButtonPressed(self, val: bool):
        logger.debug('Build order:')
        for waypt in self.build():
            logger.debug(f'Row: {waypt.idx}')
        self.resizeViewsToContents()

    def toolBar(self) -> MTSignalsToolBar:
        return self._toolbar

    @property
    def model(self) -> MTSignalsModel:
        return self._model

    @property
    def itemWidgets(self) -> typing.List[MTSignalItemView]:
        return self._signal_item_widgets

    def resizeViewToColumns(self, topLeft: QModelIndex, bottomRight: QModelIndex, roles):
        columns = range(topLeft.column(), bottomRight.column() + 1)
        for wdgt in self.itemWidgets:
            view = wdgt.view()
            if isinstance(view, QTableView):
                for col in columns:
                    view.resizeColumnToContents(col)

    def resizeViewsToContents(self):
        for wdgt in self.itemWidgets:
            view = wdgt.view()
            if isinstance(view, QTableView):
                view.resizeColumnsToContents()

    def onExport(self):
        file = QFileDialog.getSaveFileName(self, "Save CSV", filter='*.csv')
        if file and file[0]:
            if not file[0].endswith('.csv'):
                file_name = file[0] + '.csv'
            else:
                file_name = file[0]
            self.export_csv(file_name)
            self._csv_dir = os.path.dirname(file_name)

    def onImport(self):
        file = QFileDialog.getOpenFileName(self, "Open CSV", dir=self._csv_dir)
        if file and file[0]:
            self.import_csv(file[0])


    def onAppend(self):
        file = QFileDialog.getOpenFileName(self, "Append CSV", dir=self._csv_dir)
        if file and file[0]:
            self.append_csv(file[0])
    def on_tree_view(self):
        self.selectVarDialog.show()
        self.selectVarDialog.activateWindow()

    def append_dataframe(self, df):
        if not df.empty:
            self._model.append_dataframe(df)

    def insertRow(self):
        selection = []
        currentTabId = self._tabs.currentIndex()
        for idx in self._signal_item_widgets[currentTabId].view().selectionModel().selectedIndexes():
            selection.append(idx)

        if len(selection):
            self._model.insertRow(self._model.rowCount(selection[0]))
        else:
            self._model.insertRow(self._model.rowCount(QModelIndex()))

    def removeRow(self):
        selected_rows = []
        current_tab_id = self._tabs.currentIndex()
        for idx in self._signal_item_widgets[current_tab_id].view().selectionModel().selectedIndexes():
            selected_rows.append(idx.row())

        for row in reversed(sorted(selected_rows)):
            self._model.removeRow(row)

    def setBulkContents(self, text: str, indices: typing.List[QModelIndex]):
        self.busy.emit()
        left = 1 << 32
        right = 0
        top = 1 << 32
        bottom = 0
        with self._model.activate_fast_mode():
            for idx in indices:
                left = min(left, idx.column())
                right = max(right, idx.column())
                top = min(top, idx.row())
                bottom = max(bottom, idx.row())
                self._model.setData(idx, text, Qt.EditRole)
            self._model.dataChanged.emit(self._model.index(top, left), self._model.index(bottom, right))
        self.ready.emit()

    def deleteContents(self):
        current_tab_id = self._tabs.currentIndex()
        selected_ids = self._signal_item_widgets[current_tab_id].view().selectionModel().selectedIndexes()
        self.setBulkContents('', selected_ids)

    def pasteContentsFromClipboard(self):
        current_tab_id = self._tabs.currentIndex()
        selected_ids = self._signal_item_widgets[current_tab_id].view().selectionModel().selectedIndexes()

        if not len(selected_ids):
            if not self._model.rowCount(None):
                self.insertRow()
                selected_ids = [self._model.createIndex(0, 0)]
            else:
                return

        text = QCoreApplication.instance().clipboard().text()  # type: str
        text = text.strip()  # sometimes, user might have copied unnecessary line breaks at the start / end.

        data = [line.split(',') for line in text.splitlines()]
        if len(data) == 1 and len(data[0]) == 1:
            self.setBulkContents(text, selected_ids)
            return

        self.busy.emit()

        left = 1 << 32
        right = 0
        top = 1 << 32
        bottom = 0

        row = selected_ids[0].row()
        for line in data:

            col = selected_ids[0].column()
            for value in line:
                idx = self._model.createIndex(row, col)
                left = min(left, idx.column())
                right = max(right, idx.column())
                top = min(top, idx.row())
                bottom = max(bottom, idx.row())
                with self._model.activate_fast_mode():
                    self._model.setData(idx, value, Qt.EditRole)
                col += 1
            row += 1

        self._model.dataChanged.emit(self._model.index(top, left), self._model.index(bottom, right))
        self.ready.emit()

    def copyContentsToClipboard(self):
        current_tab_id = self._tabs.currentIndex()
        selected_ids = self._signal_item_widgets[current_tab_id].view().selectionModel().selectedIndexes()

        contents = defaultdict(lambda: defaultdict(str))
        rows = set()
        columns = set()
        for idx in selected_ids:
            value = self._model.data(idx, Qt.DisplayRole)
            column = idx.column()
            row = idx.row()
            contents[row][column] = value
            columns.add(column)
            rows.add(row)

        result = []
        for key, row in contents.items():
            row_text = []
            for intern_key, value in row.items():
                row_text.append(str(value))
            result.append(','.join(row_text))

        text = '\n'.join(result)

        QCoreApplication.instance().clipboard().setText(text)

    def findReplace(self):
        current_tab_id = self._tabs.currentIndex()
        table_view = self._signal_item_widgets[current_tab_id].view()

        if not self._find_replace_dialog:
            self._find_replace_dialog = FindReplaceDialog(self, model=table_view)
            palette = table_view.palette()
            palette.setColor(QPalette.ColorRole.Highlight, palette.color(QPalette.ColorRole.Highlight))
            table_view.setPalette(palette)
        else:
            self._find_replace_dialog.set_model(model=table_view)
        self._find_replace_dialog.show()

        self._find_replace_dialog.show()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        context_menu = QMenu(self)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_DialogOkButton")), "Add", self.insertRow)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_TrashIcon")), "Remove", self.removeRow)
        context_menu.addAction("Copy", self.copyContentsToClipboard)
        context_menu.addAction("Paste", self.pasteContentsFromClipboard)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_DialogResetButton")), "Clear cells", self.deleteContents)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_FileDialogContentsView")), "Find and Replace", self.findReplace)
        context_menu.popup(event.globalPos())

    def export_csv(self, file_path=None):
        try:
            self.busy.emit()
            df = self._model.get_dataframe().drop(labels=['Status', 'uid'], axis=1)
            return df.to_csv(file_path, index=False)
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(
                f"Error when dumping variables to file: {file_path} {e}")
            logger.exception(e)
            box.exec_()
        finally:
            self.ready.emit()

    def import_csv(self, file_path):
        try:
            self.busy.emit()
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            if not df.empty:
                self._model.set_dataframe(df)
            self.resizeViewsToContents()
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(f"Error parsing file. {e}")
            logger.exception(e)
            box.exec_()
        finally:
            self.ready.emit()

    def append_csv(self, file_path):
        try:
            self.busy.emit()
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            if not df.empty:
                self._model.append_dataframe(df)
            self.resizeViewsToContents()
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(f"Error parsing file. {e}")
            logger.exception(e)
            box.exec_()
        finally:
            self.ready.emit()
    def export_dict(self) -> dict:
        output = dict()
        # 1. view options.
        view_options = dict()
        for view in self._signal_item_widgets:
            view_options.update({view.windowTitle(): view.export_dict()})
        output.update({'view_options': view_options})
        # 2. Model
        output.update({'model': self._model.export_dict()})
        return output

    def import_dict(self, input_dict: dict):
        # 1. view options.
        view_options = input_dict.get('view_options') or NEAT_VIEW
        for view in self._signal_item_widgets:
            key = view.windowTitle()
            options = view_options.get(key) or NEAT_VIEW.get(key)
            for k, v in options.copy().items():
                if k not in mtbp.get_column_names(self._model.blueprint):
                    options.pop(k)
                    col_name = mtbp.get_column_name(self._model.blueprint, k)
                    if col_name:
                        options.update({col_name: v})
            view.import_dict(options)
        self._tabs.currentWidget().show()
        QCoreApplication.processEvents()

        # 2. Model
        self._model.import_dict(input_dict.get('model') or input_dict)
        self.resizeViewsToContents()

    def export_json(self):
        return json.dumps(self.export_dict())

    def import_json(self, input_file):
        self.import_dict(json.loads(input_file))

    def _abort_build(self, message):
        self.setStatusMessage("Failed")
        self.buildAborted.emit(message)
        self.hideProgress.emit()

    def build(self, **kwargs) -> typing.Iterator[Waypoint]:
        self.beginBuild()
        self.setProgress(0.0)
        self.setStatusMessage("Parsing table ..")
        QCoreApplication.instance().processEvents()

        # Load defaults from keyword args
        for key in mtbp.get_keys_with_override(self._model.blueprint):
            v = self._model.blueprint.get(key)
            code_name = v.get('code_name')
            v.update({'default': kwargs.get(code_name) if not isinstance(kwargs.get(code_name), np.int64) else int(
                kwargs.get(code_name))})
        # Initialize pre-requisites
        df = self._model.get_dataframe()
        aliases = df.loc[:, mtbp.get_column_name(
            self._model.blueprint, 'Alias')].tolist()
        duplicates = set([a for a in aliases if aliases.count(a) > 1])
        try:
            duplicates.remove('')
        except KeyError:
            pass

        # if len(duplicates):
        #     invalid_rows = [aliases.index(dup) for dup in duplicates]
        #     self._abort_build(
        #         f"Found duplicate aliases: {duplicates}. Please check row number (s): {invalid_rows}")
        #     return

        error_msgs = []
        graph = defaultdict(list)
        statusColIdx = self.model.columnCount(QModelIndex()) - 1
        with self._model.activate_fast_mode():
            for idx, row in df.iterrows():
                logger.debug(f"Row: {idx}")
                modelIdx = self.model.createIndex(idx, statusColIdx)
                row_type, name = _row_predicate(
                    row, aliases, self._model.blueprint)

                p = Parser().set_expression(name)

                for var_name in p.var_map.keys():
                    if var_name in duplicates:
                        sinfo = StatusInfo()
                        sinfo.result = Result.INVALID
                        conflict_row_ids = []
                        for alias_idx, alias in enumerate(aliases):
                            if var_name == alias:
                                conflict_row_ids.append(alias_idx)
                        sinfo.msg = f"Conflicted row: {idx + 1} , '{var_name}' is defined in row (s): {conflict_row_ids}"
                        error_msgs.append(sinfo.msg)
                        self.model.setData(modelIdx, str(sinfo), Qt.DisplayRole)
                        if idx in graph:
                            graph.pop(idx)
                else:
                    if row_type != RowAliasType.Mixed:
                        graph[idx].clear()
                        continue

                    logger.debug(f"Is a mixed alias")
                    for k in p.var_map.keys():
                        try:
                            alias_idx = aliases.index(k)
                            if alias_idx == idx:
                                sinfo = StatusInfo()
                                sinfo.result = Result.INVALID
                                sinfo.msg = f"Conflicted row: {idx + 1} , '{aliases[idx]}' short circuit in '{name}'"
                                error_msgs.append(sinfo.msg)
                                self.model.setData(modelIdx, str(sinfo), Qt.DisplayRole)
                                break
                            elif idx not in graph[alias_idx]:
                                graph[idx].append(aliases.index(k))
                            else:
                                sinfo = StatusInfo()
                                sinfo.result = Result.INVALID
                                sinfo.msg = f"Conflicted row: {idx + 1} , circular dependency with alias '{k}'"
                                error_msgs.append(sinfo.msg)
                                self.model.setData(modelIdx, str(sinfo), Qt.DisplayRole)
                                break
                        except ValueError:
                            continue

        if error_msgs:
            error_msg = '\n----\n'.join(error_msgs)
            self._abort_build(error_msg)
            return

        # Traverse the graph's edges.
        with self._model.init_create_signals():
            num_keys = len(graph.keys())
            for i, k in enumerate(graph.keys()):
                self.setStatusMessage(f"Creating signals | row: {k}")
                self.setProgress(int(i * 100 / num_keys))
                yield from self._traverse(graph, k)

        self.setProgress(100)
        self.ready.emit()
        self.endBuild()

    def _traverse(self, graph: typing.DefaultDict[int, typing.List[int]], row_idx: int, processed: set = set()) -> \
            typing.Iterator[Waypoint]:
        for idx in graph[row_idx]:
            if idx in processed:
                continue
            else:
                yield from self._traverse(graph, idx, processed)
        else:
            processed.add(row_idx)
            yield from self._model.create_signals(row_idx)

    def beginBuild(self):
        self.showProgress.emit()
        QCoreApplication.instance().processEvents()

    def endBuild(self):
        self.hideProgress.emit()
        QCoreApplication.instance().processEvents()

    def setStatusMessage(self, msg):
        self.statusChanged.emit(msg)
        QCoreApplication.instance().processEvents()

    def setProgress(self, value: int):
        self.progressChanged.emit(value)
        QCoreApplication.instance().processEvents()


def main():
    import argparse
    from PySide6.QtWidgets import QApplication

    parser = argparse.ArgumentParser('Quick demonstration of Signal Table')
    parser.add_argument(
        '-b', '--blueprint', help="Path to blueprint.json file", type=str, required=False)
    parser.add_argument(
        '-i', '--input', help="Path to input *.csv file", type=str, required=False)
    args = parser.parse_args()

    app = QApplication([])

    if args.blueprint:
        blueprint = json.load(args.blueprint)
    else:
        blueprint = mtbp.DEFAULT_BLUEPRINT
        blueprint = mtbp.DEFAULT_BLUEPRINT

    main_win = QMainWindow()
    progress_bar = QProgressBar(main_win)
    main_win.statusBar().addPermanentWidget(progress_bar)
    progress_bar.hide()

    sig_table = MTSignalConfigurator(blueprint=blueprint, parent=main_win)
    sig_table.statusChanged.connect(main_win.statusBar().showMessage)
    sig_table.progressChanged.connect(progress_bar.setValue)
    sig_table.showProgress.connect(progress_bar.show)
    sig_table.hideProgress.connect(progress_bar.hide)
    sig_table.buildAborted.connect(show_msg)

    main_win.setCentralWidget(sig_table)

    if isinstance(args.input, str) and args.input.endswith('.csv'):
        sig_table.import_csv(args.input)
    main_win.show()
    main_win.resize(1280, 720)
    sys.exit(app.exec_())


def show_msg(message):
    box = QMessageBox()
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle("Table parse failed")
    box.setText(message)
    box.exec_()

