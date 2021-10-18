# Description: An abstract model to describe data access modes.
# Author: Jaswant Sai Panchumarti

from PySide2.QtWidgets import QDataWidgetMapper, QFormLayout, QWidget
from PySide2.QtCore import QObject, QStringListModel


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
    def getSupportedModes():
        return [MTGenericAccessMode.TIME_RANGE, MTGenericAccessMode.PULSE_NUMBER, MTGenericAccessMode.PULSE_NUMBER]

    def properties(self):
        return {}

    def label(self) -> str:
        if self.mode == MTGenericAccessMode.PULSE_NUMBER:
            return "Pulse Id"
        elif self.mode == MTGenericAccessMode.RELATIVE_TIME:
            return "Relative"
        elif self.mode == MTGenericAccessMode.TIME_RANGE:
            return "Time range"

    def toDict(self) -> dict:
        return dict(mode=self.mode, **self.properties())

    def fromDict(self, contents: dict):
        self.mapper.toFirst()
