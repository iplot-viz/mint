from gui.dataRanges.dataRange import DataRange
from qtpy.QtWidgets import QDateTimeEdit, QLabel
from qtpy.QtCore import Qt


class TimeRange(DataRange):
    TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"
    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)
        
        self.mode = DataRange.TIME_RANGE
        self.fromTime = QDateTimeEdit(parent=self.form)
        self.fromTime.setDisplayFormat(TimeRange.TIME_FORMAT)
        self.toTime = QDateTimeEdit(parent=self.form)
        self.toTime.setDisplayFormat(TimeRange.TIME_FORMAT)

        str_list = mappings.get('value') if mappings.get(
            'mode') == self.mode and mappings.get('value') else ['', '']
        self.model.setStringList(str_list)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.fromTime, 0)
        self.mapper.addMapping(self.toTime, 1)
        self.mapper.toFirst()

        self.form.layout().addRow(QLabel("From time", parent=self.form), self.fromTime)
        self.form.layout().addRow(QLabel("To time", parent=self.form), self.toTime)

    def properties(self):
        return {
            "ts_start": self.model.stringList()[0],
            "ts_end": self.model.stringList()[1]
        }

    def fromDict(self, contents: dict):
        self.mapper.model().setStringList(
            [contents.get("ts_start"), contents.get("ts_end")])
        super().fromDict(contents)