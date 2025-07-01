# Copyright (c) 2020-2025 ITER Organization,
#               CS 90046
#               13067 St Paul Lez Durance Cedex
#               France
# Author IO
#
# This file is part of mint module.
# mint python module is free software: you can redistribute it and/or modify it under
# the terms of the MIT license.
#
# This file is part of ITER CODAC software.
# For the terms and conditions of redistribution or use of this software
# refer to the file LICENSE located in the top level directory
# of the distribution package
#


# Description: A widget to configure options for streaming signal data.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from mint.gui.compiled.uiStreamerConfig import UiStreamerConfig

from iplotlib.data_access.streamer import CanvasStreamer
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__, "INFO")


class MTStreamConfigurator(QDialog):
    streamStarted = Signal()
    streamStopped = Signal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.streamer = CanvasStreamer(kwargs.get('da'))
        self._active = False
        self.streamTimeWindow = 3600
        self.ui = UiStreamerConfig(self)
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

    def time_window(self) -> int:
        return int(self.ui.windowSpinBox.value())

    def is_activated(self) -> bool:
        return self._active

    def start(self):
        self._active = True
        self.streamStarted.emit()

    def stop(self):
        self.streamer.stop()
        self._active = False
        self.streamStopped.emit()
