import pandas as pd
import sys
import os

from qtpy.QtCore import QMargins, Signal
from qtpy.QtGui import QContextMenuEvent
from qtpy.QtWidgets import QFileDialog, QMenu, QMessageBox, QStyle, QTabWidget, QTableView, QVBoxLayout, QWidget, QSizePolicy

from iplotlib.core.canvas import Canvas
from iplotProcessing.core.environment import DEFAULT_BLUEPRINT_FILE

from mint.models import MTSignalsModel
from mint.gui.mtSignalToolBar import MTSignalsToolBar

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)


class MTSignalTable(QWidget):
    canvasChanged = Signal(Canvas)

    def __init__(self, blueprint: os.PathLike=DEFAULT_BLUEPRINT_FILE, parent=None):
        super().__init__(parent)

        self.model = MTSignalsModel(blueprint)

        self.table_view = QTableView()
        self.table_view.setModel(self.model)

        self.toolbar = MTSignalsToolBar()
        self.toolbar.exportCsv.connect(self.onExport)
        self.toolbar.importCsv.connect(self.onImport)

        self.tab = QWidget()
        self.tab.setLayout(QVBoxLayout())
        self.tab.layout().setContentsMargins(QMargins())
        self.tab.layout().addWidget(self.toolbar)
        self.tab.layout().addWidget(self.table_view)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.tab, "Data")

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.layout().addWidget(self.tab_widget)

    def onExport(self):
        file = QFileDialog.getSaveFileName(self, "Save CSV")
        if file and file[0]:
            self.exportCsv(file[0])

    def onImport(self):
        file = QFileDialog.getOpenFileName(self, "Open CSV")
        if file and file[0]:
            self.importCsv(file[0])

    def removeRow(self):
        selected_rows = [
            e.row() for e in self.table_view.selectionModel().selectedIndexes()]
        for row in reversed(sorted(selected_rows)):
            self.model.removeRow(row)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        context_menu = QMenu(self)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_TrashIcon")), "Remove", self.removeRow)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_DialogOkButton")), "Add", self.model.add_empty_row)
        context_menu.popup(event.globalPos())

    def exportCsv(self, file_path=None):
        try:
            return self.table_view.model().get_dataframe().to_csv(file_path, index=False)
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(f"Error when dumping variables to file: {file_path} {e}")
            logger.exception(e)
            box.exec_()

    def importCsv(self, file_path):
        try:
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            if not df.empty:
                self.table_view.model().set_dataframe(df)
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText(f"Error parsing file. {e}")
            logger.exception(e)
            box.exec_()

    def exportJson(self):
        return self.table_view.model().get_dataframe().to_json(orient='values')

    def importJson(self, json_payload):
        df = pd.read_json(json_payload, dtype=str, orient='values')
        if not df.empty:
            self.table_view.model().set_dataframe(df)

    def getModel(self):
        return self.model


def main():
    import argparse
    from qtpy.QtWidgets import QApplication
    
    parser = argparse.ArgumentParser('Quick demonstration of Signal Table')
    parser.add_argument('-b', '--blueprint', help="Path to blueprint.json file", default=DEFAULT_BLUEPRINT_FILE, type=str)
    parser.add_argument('-i', '--input', help="Path to input *.csv file", type=str, required=False)
    args = parser.parse_args()

    app = QApplication([])

    sigTable = MTSignalTable(blueprint=args.blueprint)
    sigTable.resize(1280, 720)
    sigTable.show()

    if isinstance(args.input, str) and args.input.endswith('.csv'):
        sigTable.importCsv(args.input)
    
    sys.exit(app.exec_())
