import json
import typing
from functools import partial

from qtpy.QtCore import QMargins, Signal
from qtpy.QtWidgets import QGroupBox, QHBoxLayout, QRadioButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from gui.dataRanges.relativeTime import RelativeTime
from gui.dataRanges.pulseId import PulseId
from gui.dataRanges.timeRange import TimeRange
from gui.dataRanges.dataRange import DataRange


class DataRangeSelector(QWidget):
    mode_changed = Signal()
    cancel_refresh = Signal()
    refresh_activate = Signal()
    refresh_deactivate = Signal()

    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)
        self.mappings = mappings

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.setSizePolicy(QSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Maximum))

        self.radiogroup = QGroupBox(parent=self)
        self.radiogroup.setSizePolicy(QSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.Maximum))
        self.radiogroup.setLayout(QHBoxLayout())

        self.items = [TimeRange(self.mappings),
                      PulseId(self.mappings),
                      RelativeTime(self.mappings)]  # type: typing.List[DataRange]

        self.stack = QStackedWidget(parent=self)

        for idx, item in enumerate(self.items):
            self.stack.addWidget(item.form)
            button = QRadioButton(parent=self.radiogroup)
            button.setText(item.human_readable_name())
            button.clicked.connect(partial(self.switch_form, idx))
            self.radiogroup.layout().addWidget(button)

            if self.mappings.get('mode') == item.mode:
                button.setChecked(True)

        self.layout().addWidget(self.radiogroup)
        self.layout().addWidget(self.stack)

        if not self.mappings.get('mode'):
            self.stack.setCurrentIndex(0)
            self.radiogroup.layout().itemAt(0).widget().setChecked(True)
        
        # special connections
        self.items[2].cancel_button.clicked.connect(self.cancel_refresh.emit)
        self.refresh_activate.connect(
            partial(self.items[2].cancel_button.setDisabled, False))
        self.refresh_deactivate.connect(
            partial(self.items[2].cancel_button.setDisabled, True))

    def get_model(self):
        return self.items[self.stack.currentIndex()].to_dict()

    def export_json(self):
        item = self.items[self.stack.currentIndex()]
        return json.dumps(item.to_dict())

    def import_json(self, json_string):
        contents = json.loads(json_string)
        idx = [DataRange.TIME_RANGE, DataRange.PULSE_NUMBER,
               DataRange.RELATIVE_TIME].index(contents.get('mode'))
        self.radiogroup.layout().itemAt(idx).widget().click()
        item = self.items[self.stack.currentIndex()]
        item.from_dict(contents)

    def switch_form(self, selected: int):
        self.stack.setCurrentIndex(selected)
        self.mode_changed.emit()
