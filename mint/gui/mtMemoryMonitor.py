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
            value = self.getValueAsMbytes()
            self.setText("{:.1f} MB".format(value))
        except (KeyboardInterrupt, Exception) as _:
            self._timer.stop()

    def getValueAsMbytes(self):
        return self._process.memory_info().rss / (1024.0 ** 2)
