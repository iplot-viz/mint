from gui.dataRanges.dataRange import DataRange
from qtpy.QtWidgets import QLabel, QLineEdit
from qtpy.QtCore import Qt


class PulseId(DataRange):
    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.mode = DataRange.PULSE_NUMBER
        self.pulse_number = QLineEdit(parent=self.form)

        self.mapper.setOrientation(Qt.Vertical)

        str_list = mappings.get('value') if mappings.get(
            'mode') == self.mode and mappings.get('value') else ['']
        self.model.setStringList(str_list)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.pulse_number, 0)
        self.mapper.toFirst()

        self.form.layout().addRow(QLabel("Pulse id", parent=self.form), self.pulse_number)

    def properties(self):
        return {
            "pulsenb": [e for e in self.model.stringList()[0].split(',')]
        }

    def from_dict(self, contents: dict):
        self.mapper.model().setStringList(
            [",".join(contents.get("pulsenb"))])
        super().from_dict(contents)
