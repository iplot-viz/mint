# Description: A widget to configure options for streaming signal data.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from mint.gui.compiled.ui_streamerconfig import Ui_StreamerConfig

from iplotlib.data_access.streamer import CanvasStreamer
from iplotLogging import setupLogger as sl

logger = sl.get_logger(__name__, "INFO")

class MTStreamConfigurator(QDialog):
    streamStarted = Signal()
    streamStopped = Signal()

    def __init__(self, parent=None, **kwargs):

        super().__init__(parent, **kwargs)

        self.streamer = CanvasStreamer(kwargs.get('da'))
        self._active = False
        self.streamTimeWindow = 3600
        self.ui = Ui_StreamerConfig()
        self.ui.setupUi(self)

        # Configure time window range
        self.ui.windowSpinBox.setMinimum(1)
        self.ui.windowSpinBox.setMaximum(100000)
        self.ui.windowSpinBox.setValue(self.streamTimeWindow)

        # Configure time window's units
        self.stwOptions = dict(seconds="Seconds")
        for k, v in self.stwOptions.items():
            self.ui.windowComboBox.addItem(v, k)
        
        # To indicate start of stream or cancellation
        self.ui.startButton.clicked.connect(self.start)
        self.ui.cancelButton.clicked.connect(self.hide)

    def timeWindow(self) -> int:
        return int(self.ui.windowSpinBox.value())

    def isActivated(self) -> bool:
        return self._active

    def start(self):
        self._active = True
        self.streamStarted.emit()

    def stop(self):
        self.streamer.stop()
        self._active = False
        self.streamStopped.emit()
    