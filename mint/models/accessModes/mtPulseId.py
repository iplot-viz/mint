# Description: Implements a data access mode with pulse id's.
# Author: Jaswant Sai Panchumarti

from PySide2.QtWidgets import QLabel, QLineEdit
from PySide2.QtCore import Qt
from PySide2.QtGui import QIntValidator

from mint.models.accessModes.mtGeneric import MTGenericAccessMode

class MTPulseId(MTGenericAccessMode):
    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.mode = MTGenericAccessMode.PULSE_NUMBER
        self.pulseNumber = QLineEdit(parent=self.form)
        self.fromTime = QLineEdit(parent=self.form)
        self.fromTime.setValidator(QIntValidator())
        self.toTime = QLineEdit(parent=self.form)
        self.toTime.setValidator(QIntValidator())
        self.fromTime.validator().setRange(-9999, 9999)
        self.toTime.validator().setRange(-9999, 9999)

        self.mapper.setOrientation(Qt.Vertical)

        mapAsList = mappings.get('value') if mappings.get(
            'mode') == self.mode and mappings.get('value') else ['', '', '']
        self.model.setStringList(mapAsList)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.pulseNumber, 0)
        self.mapper.addMapping(self.fromTime, 1)
        self.mapper.addMapping(self.toTime, 2)
        self.mapper.toFirst()

        self.form.layout().addRow(QLabel("Pulse id", parent=self.form), self.pulseNumber)
        self.form.layout().addRow(QLabel("From time", parent=self.form), self.fromTime)
        self.form.layout().addRow(QLabel("To time", parent=self.form), self.toTime)

    def properties(self):
        return {
            "pulse_nb": [e for e in self.model.stringList()[0].split(',')],
            "ts_start": self.model.stringList()[1],
            "ts_end": self.model.stringList()[2]
        }

    def fromDict(self, contents: dict):
        self.mapper.model().setStringList(
            [",".join(contents.get("pulse_nb"))])
        super().fromDict(contents)
