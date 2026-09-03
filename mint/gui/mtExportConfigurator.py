from PySide6.QtCore import Signal
from mint.gui.compiled.uiExportConfig import UiExportConfig
from iplotLogging import setupLogger
from PySide6.QtWidgets import *
from pathlib import Path

logger = setupLogger.get_logger(__name__, "INFO")


class MTExportConfigurator(QDialog):
    exportStarted = Signal(dict)

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.chunkSize = 100000
        self.ui = UiExportConfig(self)
        self.ui.chunksSpinBox.setValue(self.chunkSize)

        # To indicate export of data
        self.ui.exportButton.clicked.connect(self.on_data_exported)
        self.ui.cancelButton.clicked.connect(self.hide)

    def on_data_exported(self):
        data = {}
        file_format = Path(self.ui.pathLineEdit.text()).suffix
        chunks = self.ui.chunksSpinBox.value()
        output_path = self.ui.pathLineEdit.text()
        data['format'] = file_format
        data['chunks'] = chunks
        data['output_path'] = output_path
        data['relative_time'] = self.ui.timeComboBox.currentIndex() == 1
        data['resample_freq'] = self.ui.samplingComboBox.currentData()

        self.exportStarted.emit(data)
