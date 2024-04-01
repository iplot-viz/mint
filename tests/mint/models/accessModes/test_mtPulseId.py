from PySide6.QtGui import QDoubleValidator
from pytestqt.qtbot import QtBot

from mint.models.accessModes.mtPulseId import MyValidator, MTPulseId
from PySide6.QtWidgets import QLineEdit, QComboBox

#
# MyValidator(...)
#
def test_my_validator_initialization():
    """
    Test case for MyValidator initialization.
    """
    validator = MyValidator()
    assert isinstance(validator, QDoubleValidator)


def test_my_validator_validate_acceptable_inputs():
    """
    Test case for validate method with acceptable inputs.
    """
    validator = MyValidator()
    assert validator.validate('', 0) == (QDoubleValidator.Acceptable, '', 0)
    assert validator.validate('.', 0) == (QDoubleValidator.Acceptable, '.', 0)
    assert validator.validate('-', 0) == (QDoubleValidator.Acceptable, '-', 0)
    assert validator.validate('1.23', 0) == (QDoubleValidator.Acceptable, '1.23', 0)


def test_my_validator_validate_invalid_input():
    """
    Test case for validate method with invalid input.
    """
    validator = MyValidator()
    assert validator.validate('abc', 0) == (QDoubleValidator.Invalid, 'abc', 0)


#
# MTPulseId(...)
#
def test_mt_pulse_id_initialization(qtbot: QtBot):
    """
    Test case for MTPulseId initialization.
    """
    mode = MTPulseId({})
    qtbot.addWidget(mode.form)
    assert mode.mode == MTPulseId.PULSE_NUMBER
    assert isinstance(mode.pulseNumber, QLineEdit)
    assert isinstance(mode.units, QComboBox)
    assert isinstance(mode.startTime, QLineEdit)
    assert isinstance(mode.endTime, QLineEdit)
    assert isinstance(mode.startTime.validator(), MyValidator)
    assert isinstance(mode.endTime.validator(), MyValidator)


def test_mt_pulse_id_properties(qtbot: QtBot):
    """
    Test case for properties method.
    """
    mode = MTPulseId({})
    qtbot.addWidget(mode.form)
    mode.model.setStringList(["1,2,3", "Second(s)", "00:00:00", "23:59:59"])
    assert mode.properties() == {
        "pulse_nb": ["1", "2", "3"],
        "base": 1,
        "t_start": "00:00:00",
        "t_end": "23:59:59"
    }


def test_mt_pulse_id_from_dict(qtbot: QtBot):
    """
    Test case for fromDict method.
    """
    mode = MTPulseId({})
    qtbot.addWidget(mode.form)
    mode.fromDict({
        "pulse_nb": ["1", "2", "3"],
        "base": "Second(s)",
        "t_start": "00:00:00",
        "t_end": "23:59:59"
    })
    assert mode.model.stringList() == ["1,2,3", "Second(s)", "00:00:00", "23:59:59"]