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


import psutil

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel


class MTMemoryMonitor(QLabel):
    def __init__(self, pid: int = None, text: str = '', parent=None) -> None:
        super().__init__(text, parent)
        self._process = psutil.Process(pid)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.CoarseTimer)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self.update)
        self._timer.start(5_000)
        self.update()

    def update(self):
        try:
            value = self.get_value_as_mbytes()
            self.setText("{:.1f} MB".format(value))
        except (KeyboardInterrupt, Exception) as _:
            self._timer.stop()

    def get_value_as_mbytes(self):
        return self._process.memory_info().rss / (1024.0 ** 2)
