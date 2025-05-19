# Description: Implements a relative time model.
# Author: Jaswant Sai Panchumarti

from PySide6.QtWidgets import QComboBox, QLabel, QHBoxLayout, QPushButton, QSpinBox, QWidget
from PySide6.QtCore import QMargins, QStringListModel, Qt

from mint.models.accessModes.mtGeneric import MTGenericAccessMode


class MTRelativeTime(MTGenericAccessMode):

    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.mode = MTGenericAccessMode.RELATIVE_TIME
        self.magnitude = QSpinBox(parent=self.form)
        self.magnitude.setMinimum(0)
        self.magnitude.setValue(1)

        self.options = [(1, "Second(s)"), (60, "Minute(s)"), (60 * 60, "Hour(s)"), (24 * 60 * 60, "Day(s)")]

        self.values = QStringListModel(self.form)
        self.values.setStringList([e[1] for e in self.options])

        self.units = QComboBox(parent=self.form)
        self.units.setModel(self.values)

        self.cancelButton = QPushButton(parent=self.form)
        self.cancelButton.setText("Cancel")
        self.cancelButton.setDisabled(True)

        self.model.setStringList(
            mappings.get('value') if mappings.get('mode') == self.mode and mappings.get('value') else ['', '', ''])

        self.refreshInterval = QSpinBox(parent=self.form)
        self.refreshInterval.setMinimum(1)
        self.refreshInterval.setValue(5)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.magnitude, 0)
        self.mapper.addMapping(self.units, 1)
        self.mapper.addMapping(self.refreshInterval, 2)
        self.mapper.toFirst()

        self.timeInput = QWidget(parent=self.form)
        self.timeInput.setLayout(QHBoxLayout())
        self.timeInput.layout().setContentsMargins(QMargins())
        self.timeInput.layout().addWidget(self.magnitude)
        self.timeInput.layout().addWidget(self.units)
        self.timeInput.layout().setStretch(0, 1)
        self.timeInput.layout().setStretch(1, 2)

        self.refreshWidget = QWidget(parent=self.form)
        self.refreshWidget.setLayout(QHBoxLayout())
        self.refreshWidget.layout().setContentsMargins(QMargins())
        self.refreshWidget.layout().addWidget(self.refreshInterval)
        self.refreshWidget.layout().addWidget(self.cancelButton)
        self.refreshWidget.layout().setStretch(0, 1)
        self.refreshWidget.layout().setStretch(1, 2)

        self.form.layout().addRow(QLabel("Last", parent=self.form), self.timeInput)
        self.form.layout().addRow(QLabel("Refresh (mins)", parent=self.form), self.refreshWidget)

    def properties(self):
        return {
            "relative": int(self.magnitude.value()),
            "base": self.options[self.units.currentIndex()][0],
            "auto_refresh": int(self.refreshInterval.value())
        }

    def from_dict(self, contents: dict):
        relative = str(contents.get("relative"))
        base = str(contents.get("base"))
        auto_refresh = str(contents.get("auto_refresh"))

        self.mapper.model().setStringList([relative, base, auto_refresh])

        # Update ComboBox index
        try:
            index = [str(option[0]) for option in self.options].index(base)
            self.units.setCurrentIndex(index)
        except ValueError:
            self.units.setCurrentIndex(0)

        super().from_dict(contents)
