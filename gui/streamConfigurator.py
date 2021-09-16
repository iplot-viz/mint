from qtpy.QtCore import Signal
from qtpy.QtWidgets import QDialog
from gui.compiled.ui_streamerconfig import Ui_StreamerConfig

from iplotLogging import setupLogger as sl

logger = sl.get_logger(__name__, "INFO")

class StreamConfigurator(QDialog):
    streamStarted = Signal()

    def __init__(self, parent=None, **kwargs):

        super().__init__(parent, **kwargs)

        self.streamer = None
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
        self.ui.startButton.clicked.connect(self.streamStarted.emit)
        self.ui.cancelButton.clicked.connect(self.hide)

    def timeWindow(self) -> int:
        return self.ui.windowSpinBox.value()

    def isActivated(self) -> bool:
        return self.streamer is not None

    def activate(self):
        self.streamerCfgWidget.show()

    def deActivate(self):
        self.streamer.stop()
        self.streamer = None