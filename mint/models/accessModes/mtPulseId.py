# Description: Implements a data access mode with pulse id's.
# Author: Jaswant Sai Panchumarti

from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout, QFormLayout
from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QDoubleValidator

from iplotWidgets.pulseBrowser.pulseBrowser import PulseBrowser
from mint.models.accessModes.mtGeneric import MTGenericAccessMode


# Validator that checks if a string is a float and if it is not, it returns the value before the one entered.
# It also allows the empty character, the dot and the minus.
class MyValidator(QDoubleValidator):
    def __init__(self):
        super(MyValidator, self).__init__()

    def validate(self, s0: str, i1: int):
        if s0 in ['', '.', '-']:
            return QDoubleValidator.Acceptable, s0, i1

        try:
            float(s0)
            return QDoubleValidator.Acceptable, s0, i1
        except ValueError:
            return QDoubleValidator.Invalid, s0, i1


class MTPulseId(MTGenericAccessMode):
    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.options = [(1, "Second(s)"), (60, "Minute(s)"), (60 * 60, "Hour(s)"), (24 * 60 * 60, "Day(s)")]

        self.values = QStringListModel(self.form)
        self.values.setStringList([e[1] for e in self.options])
        self.mode = MTGenericAccessMode.PULSE_NUMBER

        self.pulseNumber = QLineEdit(parent=self.form)
        self.searchPulses = QPushButton("Search", parent=self.form)
        self.searchPulses.clicked.connect(self.on_search_pulse)

        self.units = QComboBox(parent=self.form)
        self.units.setModel(self.values)

        self.startTime = QLineEdit(parent=self.form)
        self.startTime.setValidator(MyValidator())

        self.endTime = QLineEdit(parent=self.form)
        self.endTime.setValidator(MyValidator())

        self.mapper.setOrientation(Qt.Vertical)
        if mappings.get('mode') == self.mode and mappings.get('value'):
            map_as_list = mappings.get('value')
        else:
            map_as_list = ['', '', '', '']
        self.model.setStringList(map_as_list)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.pulseNumber, 0)
        self.mapper.addMapping(self.units, 1)
        self.mapper.addMapping(self.startTime, 2)
        self.mapper.addMapping(self.endTime, 3)
        self.mapper.toFirst()

        # Layouts
        pulses_layout = QHBoxLayout()
        pulses_layout.addWidget(self.pulseNumber)
        pulses_layout.addWidget(self.searchPulses)

        self.form.layout().addRow(QLabel("Pulse id", parent=self.form), pulses_layout)
        self.form.layout().addRow(self.units)
        self.form.layout().addRow(QLabel("Start time", parent=self.form), self.startTime)
        self.form.layout().addRow(QLabel("End time", parent=self.form), self.endTime)

        self.selectPulseDialog = PulseBrowser()
        self.selectPulseDialog.srch_finish.connect(self.append_pulse)

    def properties(self):
        return {
            "pulse_nb": [e for e in self.model.stringList()[0].split(',')],
            "base": self.options[self.units.currentIndex()][0],
            "t_start": self.model.stringList()[2],
            "t_end": self.model.stringList()[3]
        }

    def from_dict(self, contents: dict):
        self.mapper.model().setStringList(
            [",".join(contents.get("pulse_nb") or []),
             contents.get("base") or 'Seconds',
             contents.get("t_start") or '',
             contents.get("t_end") or '']
        )
        super().from_dict(contents)

    def on_search_pulse(self):
        self.selectPulseDialog.flag = "button"
        self.selectPulseDialog.show()
        self.selectPulseDialog.activateWindow()

    def append_pulse(self, pulses):
        cur_pulses = self.pulseNumber.text()
        pulse_set = set(cur_pulses.replace(" ", "").split(",")) if cur_pulses else set()

        # Check that the pulse is not already added
        for pulse in pulses:
            pulse_set.add(pulse)

        final_pulses = ", ".join(pulse_set)

        self.pulseNumber.setText(final_pulses)
        self.pulseNumber.setFocus()
