# Description: Implements an absolute time model.
# Author: Jaswant Sai Panchumarti


from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QDateTimeEdit, QLabel, QLineEdit, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QRegularExpression

from mint.models.accessModes.mtGeneric import MTGenericAccessMode


class MTAbsoluteTime(MTGenericAccessMode):
    TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"

    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.mode = MTGenericAccessMode.TIME_RANGE

        str_list = mappings.get('value') if mappings.get('mode') == self.mode and mappings.get('value') else ['', '']
        str_list.extend(["0" * 9, "0" * 9])
        self.model.setStringList(str_list)

        self.fromTime = QDateTimeEdit(parent=self.form)
        self.fromTime.setFixedWidth(22 * self.fromTime.fontMetrics().averageCharWidth())
        self.fromTime.setDisplayFormat(MTAbsoluteTime.TIME_FORMAT)

        self.toTime = QDateTimeEdit(parent=self.form)
        self.toTime.setFixedWidth(22 * self.toTime.fontMetrics().averageCharWidth())
        self.toTime.setDisplayFormat(MTAbsoluteTime.TIME_FORMAT)

        regex = QRegularExpression("[0-9]{1,9}")  # Regular expression for 0 to 9 digits
        regex_validator = QRegularExpressionValidator(regex, self)

        self.fromTimeNs = QLineEdit(parent=self.form)
        self.fromTimeNs.setFixedWidth(11 * self.fromTimeNs.fontMetrics().averageCharWidth())
        self.fromTimeNs.setValidator(regex_validator)
        self.fromTimeNs.editingFinished.connect(self.handle_time_validation)
        self.fromTimeNs.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.toTimeNs = QLineEdit(parent=self.form)
        self.toTimeNs.setFixedWidth(11 * self.toTimeNs.fontMetrics().averageCharWidth())
        self.toTimeNs.setValidator(regex_validator)
        self.toTimeNs.editingFinished.connect(self.handle_time_validation)
        self.toTimeNs.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.fromTime, 0)
        self.mapper.addMapping(self.toTime, 1)
        self.mapper.addMapping(self.fromTimeNs, 2)
        self.mapper.addMapping(self.toTimeNs, 3)
        self.mapper.toFirst()

        # Create layout for the "From time" row
        fromTimeLayout = QHBoxLayout()
        fromTimeLayout.addWidget(self.fromTime)
        fromTimeLayout.addWidget(QLabel(".", parent=self.form))
        fromTimeLayout.addWidget(self.fromTimeNs)
        fromTimeLayout.addWidget(QLabel("ns", parent=self.form))
        fromTimeLayout.setAlignment(Qt.AlignLeft)

        # Create layout for the "To time" row
        toTimeLayout = QHBoxLayout()
        toTimeLayout.addWidget(self.toTime)
        toTimeLayout.addWidget(QLabel(".", parent=self.form))
        toTimeLayout.addWidget(self.toTimeNs)
        toTimeLayout.addWidget(QLabel("ns", parent=self.form))
        toTimeLayout.setAlignment(Qt.AlignLeft)  # Align items to the left

        # Add the rows to the form layout
        self.form.layout().addRow(QLabel("From time", parent=self.form), fromTimeLayout)
        self.form.layout().addRow(QLabel("To time", parent=self.form), toTimeLayout)

    def properties(self):
        return {
            "ts_start": self.model.stringList()[0].split(".")[0] + "." + self.model.stringList()[2],
            "ts_end": self.model.stringList()[1].split(".")[0] + "." + self.model.stringList()[3]
        }

    def from_dict(self, contents: dict):
        self.mapper.model().setStringList([contents.get("ts_start"), contents.get("ts_end")])
        super().from_dict(contents)

    def handle_time_validation(self):
        if self.sender() == self.fromTimeNs:
            self.fromTimeNs.setText(self.fromTimeNs.text().ljust(9, '0'))
        elif self.sender() == self.toTimeNs:
            self.toTimeNs.setText(self.toTimeNs.text().ljust(9, '0'))
