import json

from qtpy.QtWidgets import QDataWidgetMapper, QFormLayout, QWidget
from qtpy.QtCore import QObject, QStringListModel

class DataRange(QObject):
    PULSE_NUMBER = "PULSE_NUMBER"
    RELATIVE_TIME = "RELATIVE_TIME"
    TIME_RANGE = "TIME_RANGE"
    UNKNOWN = "UNKNOWN"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = DataRange.UNKNOWN
        self.form = QWidget(parent)
        self.form.setLayout(QFormLayout())
        self.model = QStringListModel(self.form)
        self.mapper = QDataWidgetMapper(self.form)
        self.mapper.setModel(self.model)

    def properties(self):
        return {}
    
    def human_readable_name(self) -> str:
        if self.mode == DataRange.PULSE_NUMBER:
            return "Pulse Id"
        elif self.mode == DataRange.RELATIVE_TIME:
            return "Relative"
        elif self.mode == DataRange.TIME_RANGE:
            return "Time range"
        
    def to_dict(self) -> dict:
        return dict(mode=self.mode, **self.properties())
    
    def from_dict(self, contents: dict):
        self.mapper.toFirst()