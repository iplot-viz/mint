from functools import partial

from gui.dataRanges.dataRange import DataRange
from qtpy.QtWidgets import QComboBox, QLabel, QHBoxLayout, QPushButton, QSpinBox, QWidget
from qtpy.QtCore import QMargins, QStringListModel, Qt, Signal


class RelativeTime(DataRange):

    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.mode = DataRange.RELATIVE_TIME
        self.time_magnitude = QSpinBox(parent=self.form)
        self.time_magnitude.setMinimum(0)
        self.time_magnitude.setValue(1)

        self.options = [(1, "Second(s)"), (60, "Minute(s)"),
                        (60*60, "Hour(s)"), (24*60*60, "Day(s)")]

        self.values = QStringListModel(self.form)
        self.values.setStringList([e[1] for e in self.options])

        self.time_units = QComboBox(parent=self.form)
        self.time_units.setModel(self.values)

        self.cancel_button = QPushButton(parent=self.form)
        self.cancel_button.setText("Cancel")
        self.cancel_button.setDisabled(True)

        self.model.setStringList(
            mappings.get('value') if mappings.get('mode') == self.mode and mappings.get(
                'value') else ['', '', ''])

        self.refresh_interval = QSpinBox(parent=self.form)
        self.refresh_interval.setMinimum(1)
        self.refresh_interval.setValue(5)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.time_magnitude, 0)
        self.mapper.addMapping(self.time_units, 1)
        self.mapper.addMapping(self.refresh_interval, 2)
        self.mapper.toFirst()

        self.time_input = QWidget(parent=self.form)
        self.time_input.setLayout(QHBoxLayout())
        self.time_input.layout().setContentsMargins(QMargins())
        self.time_input.layout().addWidget(self.time_magnitude, 1)
        self.time_input.layout().addWidget(self.time_units, 2)

        self.refresh_widget = QWidget(parent=self.form)
        self.refresh_widget.setLayout(QHBoxLayout())
        self.refresh_widget.layout().setContentsMargins(QMargins())
        self.refresh_widget.layout().addWidget(self.refresh_interval, 1)
        self.refresh_widget.layout().addWidget(self.cancel_button, 2)

        self.form.layout().addRow(QLabel("Last", parent=self.form), self.time_input)
        self.form.layout().addRow(
            QLabel("Refresh (mins)", parent=self.form), self.refresh_widget)

    def properties(self):
        return {
            "relative": int(self.time_magnitude.value()),
            "base": self.options[self.time_units.currentIndex()][0],
            "auto_refresh": int(self.refresh_interval.value())
        }

    def from_dict(self, contents: dict):
        self.mapper.model().setStringList([str(contents.get("relative")), str(
            contents.get("base")), str(contents.get("auto_refresh"))])
        super().from_dict(contents)
