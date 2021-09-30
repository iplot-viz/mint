# Description: A widget to select data access modes and configure individual
#              mode specific parameters. (start time, end time or pulse number or relative time, etc)
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from datetime import datetime
from functools import partial
import numpy as np
import json
import typing

from PySide2.QtCore import QMargins, Signal
from PySide2.QtWidgets import QGroupBox, QHBoxLayout, QRadioButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from mint.tools.converters import to_unix_time_stamp
from mint.models import MTGenericAccessMode, MTAbsoluteTime, MTPulseId, MTRelativeTime


class MTDataRangeSelector(QWidget):
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

        self.accesModes = [MTAbsoluteTime(self.mappings),
                           MTPulseId(self.mappings),
                           MTRelativeTime(self.mappings)]  # type: typing.List[MTGenericAccessMode]

        self.stack = QStackedWidget(parent=self)

        for idx, item in enumerate(self.accesModes):
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
        self.accesModes[2].cancelButton.clicked.connect(
            self.cancelRefresh.emit)
        self.refreshActivate.connect(
            partial(self.accesModes[2].cancelButton.setDisabled, False))
        self.refreshDeactivate.connect(
            partial(self.accesModes[2].cancelButton.setDisabled, True))

    def getModel(self):
        return self.accesModes[self.stack.currentIndex()].to_dict()

    def exportJson(self):
        item = self.accesModes[self.stack.currentIndex()]
        return json.dumps(item.toDict())

    def importJson(self, json_string):
        contents = json.loads(json_string)
        idx = [MTGenericAccessMode.TIME_RANGE, MTGenericAccessMode.PULSE_NUMBER,
               MTGenericAccessMode.RELATIVE_TIME].index(contents.get('mode'))
        self.radioGroup.layout().itemAt(idx).widget().click()
        item = self.accesModes[self.stack.currentIndex()]
        item.fromDict(contents)

    def selectPage(self, pageId: int):
        self.stack.setCurrentIndex(pageId)
        self.modeChanged.emit()

    def isXAxisDate(self) -> bool:
        mode = self.accesModes[self.stack.currentIndex()].mode
        return mode in [MTGenericAccessMode.TIME_RANGE, MTGenericAccessMode.RELATIVE_TIME]

    def getPulseNumber(self) -> typing.List[int]:
        """Extracts pulse numbers if present in time_model """
        model = self.accesModes[self.stack.currentIndex()]
        if model.mode == MTGenericAccessMode.PULSE_NUMBER:
            return model.properties().get("pulse_nb")

    @staticmethod
    def getTimeNow() -> int:
        return np.datetime64(datetime.utcnow(), 'ns').astype('int64')

    def getTimeRange(self) -> typing.Tuple[int, int]:
        """Extract begin and end timestamps if present in time_model"""
        model = self.accesModes[self.stack.currentIndex()]
        if model.mode == MTGenericAccessMode.TIME_RANGE:
            ts_start = model.properties().get("ts_start")
            ts_end = model.properties().get("ts_end")
            return to_unix_time_stamp(ts_start), to_unix_time_stamp(ts_end)
        elif model.mode == MTGenericAccessMode.RELATIVE_TIME:
            time_base = model.properties().get("base")
            ts_end = int(self.getTimeNow())
            ts_start = ts_end - 10 ** 9 * int(time_base)
            return ts_start, ts_end
        else:
            return None, None

    def getAutoRefresh(self) -> int:
        model = self.accesModes[self.stack.currentIndex()]
        if model.mode == MTGenericAccessMode.RELATIVE_TIME:
            return model.properties().get("auto_refresh") * 60
        else:
            return 0
