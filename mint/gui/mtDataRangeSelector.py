# Description: A widget to select data access modes and configure individual
#              mode specific parameters. (start time, end time or pulse number or relative time, etc)
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

from datetime import datetime
from functools import partial
import numpy as np

from typing import Union, List, Tuple

from PySide6.QtCore import QMargins, Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QRadioButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from mint.tools.converters import to_unix_time_stamp
from mint.models import MTGenericAccessMode, MTAbsoluteTime, MTPulseId, MTRelativeTime

from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)


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
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum))

        self.radioGroup = QGroupBox(parent=self)
        self.radioGroup.setSizePolicy(QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum))
        self.radioGroup.setLayout(QHBoxLayout())

        self.accessModes = [MTAbsoluteTime(self.mappings),
                            MTPulseId(self.mappings),
                            MTRelativeTime(self.mappings)]  # type: List[MTGenericAccessMode]

        self.stack = QStackedWidget(parent=self)

        for idx, item in enumerate(self.accessModes):
            self.stack.addWidget(item.form)
            button = QRadioButton(parent=self.radioGroup)
            button.setText(item.label())
            button.setToolTip(item.tooltip())
            button.clicked.connect(partial(self.select_page, idx))
            self.radioGroup.layout().addWidget(button)

            if self.mappings.get('mode') == item.mode:
                button.setChecked(True)

        self.layout().addWidget(self.radioGroup)
        self.layout().addWidget(self.stack)

        if not self.mappings.get('mode'):
            self.stack.setCurrentIndex(0)
            self.radioGroup.layout().itemAt(0).widget().setChecked(True)

        # special connections
        self.accessModes[2].cancelButton.clicked.connect(self.cancelRefresh.emit)
        self.refreshActivate.connect(partial(self.accessModes[2].cancelButton.setDisabled, False))
        self.refreshDeactivate.connect(partial(self.accessModes[2].cancelButton.setDisabled, True))

    def export_dict(self) -> dict:
        item = self.accessModes[self.stack.currentIndex()]
        return item.to_dict()

    def import_dict(self, input_dict: dict):
        # older versions of MINT did not set the appropriate mode in the workspace.
        # for ex: even if pulse numbers were specified, the 'mode' key was set to TIME_RANGE.
        # We fix that inconsistency here.
        for idx, mode_name in enumerate(MTGenericAccessMode.get_supported_modes()):
            if mode_name == input_dict['mode']:
                self.radioGroup.layout().itemAt(idx).widget().click()
                break
        else:  # cannot understand input_dict, log error and fail.
            msg = f"Failed to initialize DataRangeSelector. data_range = {input_dict}"
            logger.error(msg)
            raise Exception(msg)

        item = self.accessModes[self.stack.currentIndex()]
        item.from_dict(input_dict)

    def select_page(self, page_id: int):
        self.stack.setCurrentIndex(page_id)
        self.modeChanged.emit()
        # Emit cancelRefresh if we are leaving relative mode
        if self.accessModes[self.stack.currentIndex()].mode == MTGenericAccessMode.RELATIVE_TIME:
            self.cancelRefresh.emit()
            logger.info("Canvas auto-refresh cancelled (left relative mode)")

    def is_x_axis_date(self) -> bool:
        mode = self.accessModes[self.stack.currentIndex()].mode
        return mode in [MTGenericAccessMode.TIME_RANGE, MTGenericAccessMode.RELATIVE_TIME]

    def get_pulse_number(self) -> List[int]:
        """Extracts pulse numbers if present in time_model """
        model = self.accessModes[self.stack.currentIndex()]
        if model.mode == MTGenericAccessMode.PULSE_NUMBER:
            return model.properties().get("pulse_nb")

    @staticmethod
    def get_time_now() -> int:
        return np.datetime64(datetime.utcnow(), 'ns').astype('int64')

    def get_time_range(self) -> Tuple[Union[int, str], Union[int, str]]:
        """Extract begin and end timestamps if present in time_model"""
        model = self.accessModes[self.stack.currentIndex()]
        model_properties = model.properties()
        if model.mode == MTGenericAccessMode.TIME_RANGE:
            ts_start = model_properties.get("ts_start") + "." + model_properties.get("ts_ns_start")
            ts_end = model_properties.get("ts_end") + "." + model_properties.get("ts_ns_end")
            return to_unix_time_stamp(ts_start), to_unix_time_stamp(ts_end)
        elif model.mode == MTGenericAccessMode.RELATIVE_TIME:
            time_base = model_properties.get("base")
            ts_end = int(self.get_time_now())
            ts_start = ts_end - 10 ** 9 * int(time_base) * int(model_properties.get("relative"))
            return ts_start, ts_end
        else:
            time_base = model_properties.get("base")
            try:
                t_start = float(model_properties.get("t_start")) * int(time_base)
            except (ValueError, TypeError):
                t_start = ''
            try:
                t_end = float(model_properties.get("t_end")) * int(time_base)
            except (ValueError, TypeError):
                t_end = ''
            return t_start, t_end

    def get_auto_refresh(self) -> int:
        model = self.accessModes[self.stack.currentIndex()]
        if model.mode == MTGenericAccessMode.RELATIVE_TIME:
            return model.properties().get("auto_refresh") * 60
        else:
            return 0
