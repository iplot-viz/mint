# Description: Implements an absolute time model.
# Author: Jaswant Sai Panchumarti

import pandas as pd
from PySide6.QtGui import QRegularExpressionValidator, QFontMetrics
from PySide6.QtWidgets import QDateTimeEdit, QLabel, QLineEdit, QHBoxLayout, QSizePolicy, QPushButton
from PySide6.QtCore import Qt, QRegularExpression, Signal, QDateTime

from iplotWidgets.pulseBrowser.pulseBrowser import PulseBrowser
from mint.models.accessModes.mtGeneric import MTGenericAccessMode


class CustomQLineEdit(QLineEdit):
    # Reimplements the editingFinished signal to handle the special case.
    editingFinished = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Connect the loss of focus event to the customEditingFinished method.
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        # Detect the loss of focus event and if it is on this QLineEdit
        if event.type() == event.Type.FocusOut and obj is self:
            self.editingFinished.emit()
        return super().eventFilter(obj, event)


class MTAbsoluteTime(MTGenericAccessMode):
    TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"

    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)

        self.mode = MTGenericAccessMode.TIME_RANGE

        str_list = mappings.get('value') if mappings.get('mode') == self.mode and mappings.get('value') else ['', '']
        str_list.extend(["0" * 9, "0" * 9])
        self.model.setStringList(str_list)

        self.fromTime = QDateTimeEdit(parent=self.form)
        self.fromTime.setDisplayFormat(MTAbsoluteTime.TIME_FORMAT)

        self.toTime = QDateTimeEdit(parent=self.form)
        self.toTime.setDisplayFormat(MTAbsoluteTime.TIME_FORMAT)

        regex = QRegularExpression("[0-9]{1,9}")  # Regular expression for 0 to 9 digits
        regex_validator = QRegularExpressionValidator(regex, self)

        self.fromTimeNs = CustomQLineEdit(parent=self.form)
        self.fromTimeNs.setFixedWidth(11 * QFontMetrics(self.fromTimeNs.font()).horizontalAdvance("0"))
        self.fromTimeNs.setValidator(regex_validator)
        self.fromTimeNs.editingFinished.connect(self.handle_time_validation)
        self.fromTimeNs.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.toTimeNs = CustomQLineEdit(parent=self.form)
        self.toTimeNs.setFixedWidth(11 * QFontMetrics(self.toTimeNs.font()).horizontalAdvance("0"))
        self.toTimeNs.setValidator(regex_validator)
        self.toTimeNs.editingFinished.connect(self.handle_time_validation)
        self.toTimeNs.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.fromTime.adjustSize()
        self.fromTime.setFixedWidth(self.fromTime.width() + 2)
        self.toTime.adjustSize()
        self.toTime.setFixedWidth(self.toTime.width() + 2)

        # Pulse search widgets
        self.pulseUsed = QLineEdit(parent=self.form)
        self.pulseUsed.setReadOnly(True)
        self.pulseUsed.setPlaceholderText("No pulse selected")
        self.searchPulseBtn = QPushButton("Search", parent=self.form)
        self.searchPulseBtn.clicked.connect(self.on_search_pulse)
        self.clearPulseBtn = QPushButton("Clear", parent=self.form)
        self.clearPulseBtn.clicked.connect(self.clear_pulse)

        self.selectPulseDialog = PulseBrowser()
        self.selectPulseDialog.srch_finish.connect(self.fill_from_pulse)

        # Store time values before pulse selection so Clear can restore them
        self._saved_time_before_pulse = None

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.fromTime, 0)
        self.mapper.addMapping(self.toTime, 1)
        self.mapper.addMapping(self.fromTimeNs, 2)
        self.mapper.addMapping(self.toTimeNs, 3)
        self.mapper.toFirst()

        # Create layout for pulse search row
        pulseLayout = QHBoxLayout()
        pulseLayout.addWidget(self.pulseUsed)
        pulseLayout.addWidget(self.searchPulseBtn)
        pulseLayout.addWidget(self.clearPulseBtn)
        pulseLayout.setAlignment(Qt.AlignLeft)

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
        self.form.layout().addRow(QLabel("From pulse", parent=self.form), pulseLayout)

    def properties(self):
        return {
            "ts_start": self.model.stringList()[0].split(".")[0],
            "ts_end": self.model.stringList()[1].split(".")[0],
            "ts_ns_start": self.model.stringList()[2],
            "ts_ns_end": self.model.stringList()[3]
        }

    def set_valid_date(self, valid: bool):
        color = "white" if valid else "red"
        style = f"QDateTimeEdit {{background : {color}; }}"
        self.toTime.setStyleSheet(style)
        self.fromTime.setStyleSheet(style)

    def from_dict(self, contents: dict):
        self.mapper.model().setStringList([contents.get("ts_start"),
                                           contents.get("ts_end"),
                                           contents.get("ts_ns_start", "000000000"),
                                           contents.get("ts_ns_end", "000000000")])
        super().from_dict(contents)

    def clear_pulse(self):
        """Clear the pulse reference field and restore the time fields to their pre-pulse state."""
        self.pulseUsed.setText("")

        if self._saved_time_before_pulse is not None:
            # Restore the time values that were present before the pulse was selected
            saved = self._saved_time_before_pulse
            self.fromTime.setDateTime(saved['from_time'])
            self.toTime.setDateTime(saved['to_time'])
            self.fromTimeNs.setText(saved['from_ns'])
            self.toTimeNs.setText(saved['to_ns'])
            # Update the underlying model
            self.model.setStringList([
                saved['from_time'].toString(MTAbsoluteTime.TIME_FORMAT) if not saved['from_time'].isNull() else '',
                saved['to_time'].toString(MTAbsoluteTime.TIME_FORMAT) if not saved['to_time'].isNull() else '',
                saved['from_ns'],
                saved['to_ns']
            ])
            self.mapper.toFirst()
            self._saved_time_before_pulse = None
        # If no saved state, just clear the pulse text (times remain as they are)

    def handle_time_validation(self):
        if self.sender() == self.fromTimeNs:
            self.fromTimeNs.editingFinished.disconnect()
            self.fromTimeNs.setText(self.fromTimeNs.text().ljust(9, '0'))
            self.fromTimeNs.editingFinished.connect(self.handle_time_validation)
        elif self.sender() == self.toTimeNs:
            self.toTimeNs.setText(self.toTimeNs.text().ljust(9, '0'))

    def on_search_pulse(self):
        """Open the pulse browser dialog."""
        self.selectPulseDialog.flag = "time_range"
        self.selectPulseDialog.set_selection_mode(single=True, require_timestamps=True)
        self.selectPulseDialog.show()
        self.selectPulseDialog.activateWindow()

    def fill_from_pulse(self, pulses):
        """Fill the timestamp fields from the selected pulse."""
        # Only process if opened from Time Range
        if self.selectPulseDialog.flag != "time_range":
            return
        if not pulses:
            return
        # Only use the first pulse
        pulse = pulses[0]

        # Get pulse info from the data source used in the pulse browser
        ds = self.selectPulseDialog.get_current_source()

        # Only UDA data sources support timeFrom/timeTo
        if ds.source_type != "CODAC_UDA":
            self.pulseUsed.setText(f"{pulse} (timestamps not available)")
            return

        pulse_info = ds.get_pulse_info(pulse_id=pulse)

        if pulse_info is None:
            self.pulseUsed.setText(f"{pulse} (not found)")
            return

        # Convert nanoseconds timestamps to QDateTime + nanoseconds part
        time_from_ns = pulse_info.timeFrom
        time_to_ns = pulse_info.timeTo

        # Convert to pandas Timestamp for easy manipulation
        ts_from = pd.Timestamp(time_from_ns)
        ts_to = pd.Timestamp(time_to_ns)

        # Create QDateTime (seconds precision)
        qdt_from = QDateTime.fromString(ts_from.strftime("%Y-%m-%dT%H:%M:%S"), MTAbsoluteTime.TIME_FORMAT)
        qdt_to = QDateTime.fromString(ts_to.strftime("%Y-%m-%dT%H:%M:%S"), MTAbsoluteTime.TIME_FORMAT)

        # Extract nanoseconds part (nanoseconds within the second)
        ns_from = str(ts_from.nanosecond).zfill(9)
        ns_to = str(ts_to.nanosecond).zfill(9)

        # Set the values in the UI
        # Save current time values before overwriting so Clear can restore them
        self._saved_time_before_pulse = {
            'from_time': QDateTime(self.fromTime.dateTime()),
            'to_time': QDateTime(self.toTime.dateTime()),
            'from_ns': self.fromTimeNs.text(),
            'to_ns': self.toTimeNs.text()
        }

        self.fromTime.setDateTime(qdt_from)
        self.toTime.setDateTime(qdt_to)
        self.fromTimeNs.setText(ns_from)
        self.toTimeNs.setText(ns_to)

        # Show the pulse used
        self.pulseUsed.setText(pulse)
