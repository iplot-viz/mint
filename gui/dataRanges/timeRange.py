from gui.dataRanges.dataRange import DataRange
from qtpy.QtWidgets import QDateTimeEdit, QLabel
from qtpy.QtCore import Qt


class TimeRange(DataRange):
    TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"
    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)
        
        self.mode = DataRange.TIME_RANGE
        self.from_time = QDateTimeEdit(parent=self.form)
        self.from_time.setDisplayFormat(TimeRange.TIME_FORMAT)
        self.to_time = QDateTimeEdit(parent=self.form)
        self.to_time.setDisplayFormat(TimeRange.TIME_FORMAT)

        str_list = mappings.get('value') if mappings.get(
            'mode') == self.mode and mappings.get('value') else ['', '']
        self.model.setStringList(str_list)

        self.mapper.setOrientation(Qt.Vertical)
        self.mapper.addMapping(self.from_time, 0)
        self.mapper.addMapping(self.to_time, 1)
        self.mapper.toFirst()

        self.form.layout().addRow(QLabel("From time", parent=self.form), self.from_time)
        self.form.layout().addRow(QLabel("To time", parent=self.form), self.to_time)

    def properties(self):
        return {
            "ts_start": self.model.stringList()[0],
            "ts_end": self.model.stringList()[1]
        }

    def from_dict(self, contents: dict):
        self.mapper.model().setStringList(
            [contents.get("ts_start"), contents.get("ts_end")])
        super().from_dict(contents)