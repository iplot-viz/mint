from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class MTErrorHoverPopup(QFrame):
    moreInfoRequested = Signal(str)

    HIDE_DELAY_MS = 180

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setObjectName("mtErrorHoverPopup")
        self.setStyleSheet("""
            #mtErrorHoverPopup {
                background: #fff8d6;
                border: 1px solid #d4a800;
                border-radius: 4px;
            }
            QLabel { background: transparent; color: #222; }
            QLabel#mtErrorTitle { color: #1a4d80; font-weight: bold; font-size: 11pt; }
            QPushButton {
                background: #1a4d80; color: white; border: 0; border-radius: 3px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: #2a5d90; }
        """)

        self._title = QLabel(self)
        self._title.setObjectName("mtErrorTitle")
        self._title.setWordWrap(True)

        self._explanation = QLabel(self)
        self._explanation.setWordWrap(True)
        self._explanation.setMinimumWidth(360)
        self._explanation.setMaximumWidth(420)

        self._more_btn = QPushButton("More info →", self)
        self._more_btn.setCursor(Qt.PointingHandCursor)
        self._more_btn.clicked.connect(self._on_more_clicked)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch(1)
        button_row.addWidget(self._more_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(self._title)
        layout.addWidget(self._explanation)
        layout.addLayout(button_row)

        self._anchor: Optional[str] = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._maybe_hide)

    def populate(self, title: str, explanation: str, anchor: Optional[str]):
        self._title.setText(title)
        self._explanation.setText(explanation)
        self._anchor = anchor
        self._more_btn.setVisible(bool(anchor))
        self.adjustSize()

    def schedule_hide(self):
        self._hide_timer.start(self.HIDE_DELAY_MS)

    def cancel_hide(self):
        self._hide_timer.stop()

    def _maybe_hide(self):
        if not self.underMouse():
            self.hide()

    def enterEvent(self, ev):
        self.cancel_hide()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.schedule_hide()
        super().leaveEvent(ev)

    def _on_more_clicked(self):
        if self._anchor:
            self.moreInfoRequested.emit(self._anchor)
        self.hide()
