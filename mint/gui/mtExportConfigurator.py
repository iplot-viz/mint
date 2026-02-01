from PySide6.QtCore import Signal
from mint.gui.compiled.uiExportConfig import UiExportConfig
from iplotLogging import setupLogger
from PySide6.QtWidgets import *

logger = setupLogger.get_logger(__name__, "INFO")


class MTExportConfigurator(QDialog):
    exportStarted = Signal(dict)

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.chunkSize = 100000
        self.ui = UiExportConfig(self)
        self.ui.chunksSpinBox.setValue(self.chunkSize)

        self.formatOptions = dict(parquet="parquet", hdf5="hdf5")
        for k, v in self.formatOptions.items():
            self.ui.formatComboBox.addItem(v, k)

        # To indicate export of data
        self.ui.exportButton.clicked.connect(self.on_data_exported)
        self.ui.cancelButton.clicked.connect(self.hide)

    def on_data_exported(self):
        data = {}
        format = self.ui.formatComboBox.currentText()
        chunks = self.ui.chunksSpinBox.value()
        output_path = self.ui.pathLineEdit.text()
        data['format'] = format
        data['chunks'] = chunks
        data['output_path'] = output_path

        self.exportStarted.emit(data)