from gui.dataRanges.dataRange import DataRange
from qtpy.QtWidgets import QLabel, QLineEdit
from qtpy.QtCore import Qt


class PulseId(DataRange):
    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.mode = DataRange.PULSE_NUMBER
        self.pulseNumber = QLineEdit(parent=self.form)

        self.mapper.setOrientation(Qt.Vertical)

        mapAsList = mappings.get('value') if mappings.get(
            'mode') == self.mode and mappings.get('value') else ['']
        self.model.setStringList(mapAsList)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.pulseNumber, 0)
        self.mapper.toFirst()

        self.form.layout().addRow(QLabel("Pulse id", parent=self.form), self.pulseNumber)

    def properties(self):
        return {
            "pulse_nb": [e for e in self.model.stringList()[0].split(',')]
        }

    def fromDict(self, contents: dict):
        self.mapper.model().setStringList(
            [",".join(contents.get("pulse_nb"))])
        super().fromDict(contents)
