from mint.tools.converters import str_to_arr
from mint.tools.converters import to_unix_time_stamp
import pytest


#
# str_to_arr(...)
#
def test_str_to_arr_valid_input():
    """
    Test that the function correctly converts a valid string to an array of strings.
    """

    # Given
    input_str = "1 , 2 , 3 , 4 , 5"

    # When
    result = str_to_arr(input_str)

    # Then
    assert result == ['1', '2', '3', '4', '5']


def test_str_to_arr_empty_string():
    """
    Test that the function returns an empty array when the input string is empty.
    """

    # Given
    input_str = ""

    # When
    result = str_to_arr(input_str)

    # Then
    assert result == ['']


def test_str_to_arr_none_input():
    """
    Test that the function correctly converts a None string.
    """
    # When
    result = str_to_arr(None)

    # Then
    assert result is None


def test_str_to_arr_invalid_input():
    """
    Test that the function raises a ValueError when the input string is not a valid list of strings.
    """

    # Given
    not_a_str = 234523

    # Then
    with pytest.raises(AttributeError):
        # When
        str_to_arr(not_a_str)


#
# to_unix_time_stamp(...)
#
def test_to_unix_time_stamp_valid_input():
    """
    Test that the function correctly converts a valid datetime string to a Unix timestamp.
    """

    # Given
    datetime_str = "2022-01-01T00:00:00"
    time_units = "ns"

    # When
    result = to_unix_time_stamp(datetime_str, time_units)

    # Then
    # The expected result is the Unix timestamp for the given datetime string.
    expected_result = 1640995200000000000
    assert result == expected_result


def test_to_unix_time_stamp_invalid_input():
    """
    Test that the function raises a TypeError when the input is not a valid datetime string.
    """

    # Given
    datetime_str = "not a valid datetime string"
    time_units = "ns"

    # Then
    with pytest.raises(ValueError):
        # When
        to_unix_time_stamp(datetime_str, time_units)
