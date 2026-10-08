# Description: A widget to configure options for streaming signal data.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from mint.gui.compiled.uiStreamerConfig import UiStreamerConfig

from iplotlib.data_access.streamer import CanvasStreamer
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__, "INFO")


class MTStreamConfigurator(QDialog):
    streamStarted = Signal()
    streamStopped = Signal()

    MAX_WINDOW_SECONDS = 7 * 24 * 3600  # 7 days

    # Per-signal sample cap while streaming. Kept off the dialog because it
    # drives CPU/memory: overridable through MINT_MAX_STREAMING_POINTS for
    # tuning without a UI change.
    DEFAULT_MAX_POINTS = 10_000
    MAX_POINTS_LIMIT = 100_000

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.streamer = CanvasStreamer(kwargs.get('da'))
        self._active = False
        self.streamTimeWindow = 3600
        self.ui = UiStreamerConfig(self)

        # Time window units (key -> (display label, seconds multiplier))
        self.stwOptions = {
            "seconds": ("Seconds", 1),
            "minutes": ("Minutes", 60),
            "hours": ("Hours", 3600),
            "days": ("Days", 86400),
        }
        for key, (label, _) in self.stwOptions.items():
            self.ui.windowComboBox.addItem(label, key)

        self.ui.windowComboBox.setCurrentIndex(list(self.stwOptions).index("hours"))

        self.ui.windowSpinBox.setMinimum(1)
        self._update_spinbox_range()
        self.ui.windowSpinBox.setValue(self.streamTimeWindow // self._unit_multiplier())

        # Connected after the initial setup so it does not fire during construction.
        # The number stays as typed when the unit changes; only its range follows.
        self.ui.windowComboBox.currentIndexChanged.connect(self._update_spinbox_range)

        self.ui.startButton.clicked.connect(self.start)
        self.ui.cancelButton.clicked.connect(self.hide)

    def _unit_multiplier(self) -> int:
        return self.stwOptions[self.ui.windowComboBox.currentData()][1]

    def _update_spinbox_range(self):
        self.ui.windowSpinBox.setMaximum(self.MAX_WINDOW_SECONDS // self._unit_multiplier())

    def time_window(self) -> int:
        return int(self.ui.windowSpinBox.value()) * self._unit_multiplier()

    def max_points(self) -> int:
        """Per-signal sample cap, read from MINT_MAX_STREAMING_POINTS and
        clamped to a safe upper bound. Off the dialog because it drives
        CPU/memory rather than being a per-session choice."""
        try:
            value = int(os.environ.get('MINT_MAX_STREAMING_POINTS',
                                       self.DEFAULT_MAX_POINTS))
        except (TypeError, ValueError):
            value = self.DEFAULT_MAX_POINTS
        return max(1, min(value, self.MAX_POINTS_LIMIT))

    def is_activated(self) -> bool:
        return self._active

    def start(self):
        self._active = True
        self.streamStarted.emit()

    def stop(self):
        self.streamer.stop()
        self._active = False
        self.streamStopped.emit()
