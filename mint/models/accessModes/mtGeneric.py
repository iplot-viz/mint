# Description: An abstract model to describe data access modes.
# Author: Jaswant Sai Panchumarti

from PySide6.QtWidgets import QDataWidgetMapper, QFormLayout, QWidget
from PySide6.QtCore import QObject, QStringListModel


class MTGenericAccessMode(QObject):
    PULSE_NUMBER = "PULSE_NUMBER"
    RELATIVE_TIME = "RELATIVE_TIME"
    TIME_RANGE = "TIME_RANGE"
    UNKNOWN = "UNKNOWN"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = MTGenericAccessMode.UNKNOWN
        self.form = QWidget(parent)
        self.form.setLayout(QFormLayout())
        self.model = QStringListModel(self.form)
        self.mapper = QDataWidgetMapper(self.form)
        self.mapper.setModel(self.model)

    @staticmethod
    def get_supported_modes():
        return [MTGenericAccessMode.TIME_RANGE, MTGenericAccessMode.PULSE_NUMBER, MTGenericAccessMode.RELATIVE_TIME]

    def properties(self):
        return {}

    def label(self) -> str:
        if self.mode == MTGenericAccessMode.PULSE_NUMBER:
            return "Pulse Id"
        elif self.mode == MTGenericAccessMode.RELATIVE_TIME:
            return "Relative"
        elif self.mode == MTGenericAccessMode.TIME_RANGE:
            return "Time range"

    def tooltip(self) -> str:
        if self.mode == MTGenericAccessMode.PULSE_NUMBER:
            return "Select data by pulse/run (ITER:PCS/123) or IMAS URI (imas:hdf5?path=/path/to/data/entry). In " \
                   "case of multiple pulse id, the separator used is coma"
        elif self.mode == MTGenericAccessMode.RELATIVE_TIME:
            return "Select data by relative time to now"
        elif self.mode == MTGenericAccessMode.TIME_RANGE:
            return "Select data by time range"

    def to_dict(self) -> dict:
        return dict(mode=self.mode, **self.properties())

    def from_dict(self, contents: dict):
        self.mapper.toFirst()
