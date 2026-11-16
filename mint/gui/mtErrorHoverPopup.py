from typing import Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from iplotWidgets.sizing import scaled_px
from mint.gui.mtAppearance import blend, is_dark


class MTErrorHoverPopup(QFrame):
    moreInfoRequested = Signal(str)

    HIDE_DELAY_MS = 180

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setObjectName("mtErrorHoverPopup")
        self._set_style_sheet()

        self._title = QLabel(self)
        self._title.setObjectName("mtErrorTitle")
        self._title.setWordWrap(True)
        # Relative to the widget font, which is what the UI scale moves; a
        # style-sheet font-size only takes absolute units.
        title_font = self._title.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.2)
        self._title.setFont(title_font)

        self._explanation = QLabel(self)
        self._explanation.setWordWrap(True)
        # Grown with the font so the callout keeps its measure at any UI scale
        # instead of turning into a narrow column of wrapped text.
        self._explanation.setMinimumWidth(scaled_px(self, 360))
        self._explanation.setMaximumWidth(scaled_px(self, 420))

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

    def _set_style_sheet(self):
        """A yellow note in a light palette; in a dark one, a tooltip in the colours of the palette."""
        # That of the application: a style sheet of its own changes that of the popup.
        palette = QGuiApplication.palette()
        if is_dark(palette):
            colors = dict(background=palette.color(QPalette.ColorRole.ToolTipBase).name(), border='#d4a800',
                          text=palette.color(QPalette.ColorRole.ToolTipText).name(),
                          title=palette.color(QPalette.ColorRole.Link).name(),
                          button=palette.color(QPalette.ColorRole.Highlight).name(),
                          button_text=palette.color(QPalette.ColorRole.HighlightedText).name(),
                          hover=blend(palette.color(QPalette.ColorRole.Highlight),
                                      palette.color(QPalette.ColorRole.HighlightedText), 0.15).name())
        else:
            colors = dict(background='#fff8d6', border='#d4a800', text='#222', title='#1a4d80', button='#1a4d80',
                          button_text='white', hover='#2a5d90')
        sheet = """
            #mtErrorHoverPopup {{
                background: {background};
                border: 1px solid {border};
                border-radius: 4px;
            }}
            QLabel {{ background: transparent; color: {text}; }}
            QLabel#mtErrorTitle {{ color: {title}; font-weight: bold; }}
            QPushButton {{
                background: {button}; color: {button_text}; border: 0; border-radius: 3px;
                padding: 0.3em 1em;
            }}
            QPushButton:hover {{ background: {hover}; }}
        """.format(**colors)
        # Set only when it changes: setting it may bring a palette change of its own.
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == QEvent.Type.PaletteChange:
            self._set_style_sheet()

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
