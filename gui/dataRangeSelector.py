from datetime import datetime
import numpy as np
import json
import typing
from functools import partial

from qtpy.QtCore import QMargins, Signal
from qtpy.QtWidgets import QGroupBox, QHBoxLayout, QRadioButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from common.converters import to_unix_time_stamp
from gui.dataRanges.relativeTime import RelativeTime
from gui.dataRanges.pulseId import PulseId
from gui.dataRanges.timeRange import TimeRange
from gui.dataRanges.dataRange import DataRange


class DataRangeSelector(QWidget):
    modeChanged = Signal()
    cancelRefresh = Signal()
    refreshActivate = Signal()
    refreshDeactivate = Signal()

    def __init__(self, mappings: dict, parent=None):
        super().__init__(parent)
        self.mappings = mappings

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        self.setSizePolicy(QSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Maximum))

        self.radioGroup = QGroupBox(parent=self)
        self.radioGroup.setSizePolicy(QSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.Maximum))
        self.radioGroup.setLayout(QHBoxLayout())

        self.dataRangeModels = [TimeRange(self.mappings),
                                PulseId(self.mappings),
                                RelativeTime(self.mappings)]  # type: typing.List[DataRange]

        self.stack = QStackedWidget(parent=self)

        for idx, item in enumerate(self.dataRangeModels):
            self.stack.addWidget(item.form)
            button = QRadioButton(parent=self.radioGroup)
            button.setText(item.label())
            button.clicked.connect(partial(self.selectPage, idx))
            self.radioGroup.layout().addWidget(button)

            if self.mappings.get('mode') == item.mode:
                button.setChecked(True)

        self.layout().addWidget(self.radioGroup)
        self.layout().addWidget(self.stack)

        if not self.mappings.get('mode'):
            self.stack.setCurrentIndex(0)
            self.radioGroup.layout().itemAt(0).widget().setChecked(True)

        # special connections
        self.dataRangeModels[2].cancelButton.clicked.connect(
            self.cancelRefresh.emit)
        self.refreshActivate.connect(
            partial(self.dataRangeModels[2].cancelButton.setDisabled, False))
        self.refreshDeactivate.connect(
            partial(self.dataRangeModels[2].cancelButton.setDisabled, True))

    def getModel(self):
        return self.dataRangeModels[self.stack.currentIndex()].to_dict()

    def exportJson(self):
        item = self.dataRangeModels[self.stack.currentIndex()]
        return json.dumps(item.toDict())

    def importJson(self, json_string):
        contents = json.loads(json_string)
        idx = [DataRange.TIME_RANGE, DataRange.PULSE_NUMBER,
               DataRange.RELATIVE_TIME].index(contents.get('mode'))
        self.radioGroup.layout().itemAt(idx).widget().click()
        item = self.dataRangeModels[self.stack.currentIndex()]
        item.fromDict(contents)

    def selectPage(self, pageId: int):
        self.stack.setCurrentIndex(pageId)
        self.modeChanged.emit()

    def isXAxisDate(self) -> bool:
        mode = self.dataRangeModels[self.stack.currentIndex()].mode
        return mode in [DataRange.TIME_RANGE, DataRange.RELATIVE_TIME]

    def getPulseNumber(self) -> typing.List[int]:
        """Extracts pulse numbers if present in time_model """
        model = self.dataRangeModels[self.stack.currentIndex()]
        if model.mode == DataRange.PULSE_NUMBER:
            return model.properties().get("pulse_nb")

    @staticmethod
    def getTimeNow() -> int:
        return np.datetime64(datetime.utcnow(), 'ns').astype('int64')

    def getTimeRange(self) -> typing.Tuple[int, int]:
        """Extract begin and end timestamps if present in time_model"""
        model = self.dataRangeModels[self.stack.currentIndex()]
        if model.mode == DataRange.TIME_RANGE:
            ts_start = model.properties().get("ts_start")
            ts_end = model.properties().get("ts_end")
            return to_unix_time_stamp(ts_start), to_unix_time_stamp(ts_end)
        elif model.mode == DataRange.RELATIVE_TIME:
            time_base = model.properties().get("base")
            ts_end = int(self.getTimeNow())
            ts_start = ts_end - 10 ** 9 * int(time_base)
            return ts_start, ts_end
        else:
            return None, None

    def getAutoRefresh(self) -> int:
        model = self.dataRangeModels[self.stack.currentIndex()]
        if model.mode == DataRange.RELATIVE_TIME:
            return model.properties().get("auto_refresh") * 60
        else:
            return 0