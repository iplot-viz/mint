from qtpy.QtCore import QMargins, Signal
from qtpy.QtWidgets import QDialog, QSpinBox, QPushButton, QComboBox, QHBoxLayout, QWidget, QFormLayout, QVBoxLayout, QLabel

class StreamerDialog(QDialog):
    stream_started = Signal()

    def __init__(self, parent=None, **kwargs):

        super().__init__(parent, **kwargs)

        self.streamer = None
        self.stream_window = 3600
        self.stream_window_spinbox = QSpinBox(parent=self)

        self.stream_window_spinbox.setMinimum(1)
        self.stream_window_spinbox.setMaximum(100_000)
        self.stream_window_spinbox.setValue(self.stream_window)
        
        self.start_btn = QPushButton("Start", parent=self)
        self.cancel_btn = QPushButton("Cancel", parent=self)

        self.stream_window_options = dict(seconds="Seconds")
        self.stream_window_combo = QComboBox(parent=self)
        for k, v in self.stream_window_options.items():
            self.stream_window_combo.addItem(v, k)
        
        self.stream_window_widget = QWidget()
        self.stream_window_widget.setLayout(QHBoxLayout())
        self.stream_window_widget.layout().setContentsMargins(QMargins())
        self.stream_window_widget.layout().addWidget(self.stream_window_spinbox)
        self.stream_window_widget.layout().addWidget(self.stream_window_combo)

        self.form = QWidget()
        self.form.setLayout(QFormLayout())
        self.form.layout().addRow("Window", self.stream_window_widget)
        
        self.buttons = QWidget()
        self.buttons.setLayout(QHBoxLayout())
        self.buttons.layout().setContentsMargins(QMargins())
        self.buttons.layout().addWidget(self.start_btn)
        self.buttons.layout().addWidget(self.cancel_btn)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(QLabel("Stream settings"))
        self.layout().addWidget(self.form)
        self.layout().addWidget(self.buttons)

        self.start_btn.clicked.connect(self.stream_started.emit)
        self.cancel_btn.clicked.connect(self.hide)
