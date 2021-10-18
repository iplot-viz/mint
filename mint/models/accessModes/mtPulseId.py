# Description: Implements a data access mode with pulse id's.
# Author: Jaswant Sai Panchumarti

from PySide2.QtWidgets import QComboBox, QLabel, QLineEdit
from PySide2.QtCore import QStringListModel, Qt
from PySide2.QtGui import QDoubleValidator

from mint.models.accessModes.mtGeneric import MTGenericAccessMode


class MTPulseId(MTGenericAccessMode):
    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.options = [(1, "Second(s)"), (60, "Minute(s)"),
                        (60*60, "Hour(s)"), (24*60*60, "Day(s)")]

        self.values = QStringListModel(self.form)
        self.values.setStringList([e[1] for e in self.options])

        self.mode = MTGenericAccessMode.PULSE_NUMBER
        self.pulseNumber = QLineEdit(parent=self.form)

        self.units = QComboBox(parent=self.form)
        self.units.setModel(self.values)

        self.startTime = QLineEdit(parent=self.form)
        self.startTime.setValidator(QDoubleValidator())

        self.endTime = QLineEdit(parent=self.form)
        self.endTime.setValidator(QDoubleValidator())

        self.mapper.setOrientation(Qt.Vertical)

        mapAsList = mappings.get('value') if mappings.get(
            'mode') == self.mode and mappings.get('value') else ['', '', '', '']
        self.model.setStringList(mapAsList)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.pulseNumber, 0)
        self.mapper.addMapping(self.units, 1)
        self.mapper.addMapping(self.startTime, 2)
        self.mapper.addMapping(self.endTime, 3)
        self.mapper.toFirst()

        self.form.layout().addRow(QLabel("Pulse id", parent=self.form), self.pulseNumber)
        self.form.layout().addRow(self.units)
        self.form.layout().addRow(QLabel("Start time", parent=self.form), self.startTime)
        self.form.layout().addRow(QLabel("End time", parent=self.form), self.endTime)

    def properties(self):
        return {
            "pulse_nb": [e for e in self.model.stringList()[0].split(',')],
            "base": self.options[self.units.currentIndex()][0],
            "t_start": self.model.stringList()[2],
            "t_end": self.model.stringList()[3]
        }

    def fromDict(self, contents: dict):
        self.mapper.model().setStringList(
            [",".join(contents.get("pulse_nb")),
             contents.get("base") or 'Seconds',
             contents.get("t_start") or '',
             contents.get("t_end") or '']
        )
        super().fromDict(contents)
