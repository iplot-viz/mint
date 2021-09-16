import pandas

from qtpy import QtGui
from qtpy.QtCore import QMargins, Signal
from qtpy.QtWidgets import QFileDialog, QMenu, QMessageBox, QStyle, QTabWidget, QTableView, QVBoxLayout, QWidget

from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import PlotXY
from iplotlib.data_access import DataAccessSignal

from gui.plotsModel import PlotsModel
from gui.variablesToolbar import VairablesToolbar

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)



class VariablesTable(QWidget):
    canvasChanged = Signal(Canvas)

    def __init__(self, header: dict, model: dict, plot_class=PlotXY, signal_class=DataAccessSignal, parent=None):
        super().__init__(parent)

        self.plot_class = plot_class
        self.signal_class = signal_class
        self.header = header
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.table_model = PlotsModel(self.header, initial_model=model)

        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)

        self.toolbar = VairablesToolbar()
        self.toolbar.exportCsv.connect(self.onExport)
        self.toolbar.importCsv.connect(self.onImport)

        self.tab = QWidget()
        self.tab.setLayout(QVBoxLayout())
        self.tab.layout().setContentsMargins(QMargins())
        self.tab.layout().addWidget(self.toolbar)
        self.tab.layout().addWidget(self.table_view)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.tab, "Data")

        self.layout().addWidget(self.tab_widget)

    def onExport(self):
        file = QFileDialog.getSaveFileName(self, "Save CSV")
        if file and file[0]:
            self.export_csv(file[0])

    def onImport(self):
        file = QFileDialog.getOpenFileName(self, "Open CSV")
        if file and file[0]:
            self.import_csv(file[0])

    def removeRow(self):
        selected_rows = [
            e.row() for e in self.table_view.selectionModel().selectedIndexes()]
        for row in reversed(sorted(selected_rows)):
            self.table_model.removeRow(row)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        context_menu = QMenu(self)
        context_menu.addAction(self.style().standardIcon(
            getattr(QStyle, "SP_TrashIcon")), "Remove", self.removeRow)
        context_menu.popup(event.globalPos())

    def export_csv(self, file_path=None):
        try:
            return self.exportDataframe().to_csv(file_path, index=False)
        except:
            logger.info(f"Error when dumping variables to file: {file_path}")

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

    def exportDataframe(self) -> pandas.DataFrame:
        return pandas.DataFrame(self.table_view.model().model[:-1], columns=self.table_view.model().column_names)

    def export_json(self):
        return self.exportDataframe().to_json(orient='values')

    def import_json(self, json_payload):
        df = pandas.read_json(json_payload, dtype=str, orient='values')
        if not df.empty:
            self.table_view.model().set_model(df.values.tolist())

    def getModel(self):
        return self.table_model