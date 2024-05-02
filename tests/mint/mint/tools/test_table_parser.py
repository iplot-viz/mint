import pytest
import numpy as np
from mint.tools.table_parser import str_to_arr
from mint.tools.table_parser import get_value
from mint.tools.table_parser import is_numeric
from mint.tools.table_parser import parse_timestamp


##############################################
# Test cases for str_to_arr
##############################################
def test_str_to_arr_normal_input():
    """
    Test case for normal input
    """
    assert str_to_arr("apple,banana,orange") == ["apple", "banana", "orange"]


def test_str_to_arr_with_spaces():
    """
    Test case for input with spaces around the commas
    """
    assert str_to_arr(" apple , banana , orange ") == ["apple", "banana", "orange"]


def test_str_to_arr_with_empty_elements():
    """
    Test case for input with empty elements
    """
    assert str_to_arr("apple,,banana,,orange") == ["apple", "banana", "orange"]


def test_str_to_arr_with_only_spaces():
    """
    Test case for input with only spaces
    """
    assert str_to_arr(" , , ") is None


def test_str_to_arr_with_none_input():
    """
    Test case for None input
    """
    assert str_to_arr(None) is None


def test_str_to_arr_with_empty_string_input():
    """
    Test case for empty string input
    """
    assert str_to_arr("") is None


def test_str_to_arr_with_single_element():
    """
    Test case for single element input
    """
    assert str_to_arr("apple") == ["apple"]


def test_str_to_arr_with_single_empty_element():
    """
    Test case for single empty element input
    """
    assert str_to_arr(",") is None


def test_str_to_arr_with_mixed_elements():
    """
    Test case for mixed elements input
    """
    assert str_to_arr("apple, banana, , orange") == ["apple", "banana", "orange"]


def test_str_to_arr_with_one_empty_element():
    """
    Test case for an edge case where only one empty element is present
    """
    assert str_to_arr(",apple") == ["apple"]


def test_str_to_arr_with_multiple_empty_elements():
    """
    Test case for an edge case where multiple empty elements are present
    """
    assert str_to_arr(",apple,,,banana,,,") == ["apple", "banana"]


##############################################
# Test cases for get_value
##############################################

def test_get_value_normal_input():
    """
    Test case for normal input.
    """
    assert get_value({"apple": "10"}, "apple") == "10"


def test_get_value_with_no_value():
    """
    Test case for input with no value.
    """
    assert get_value({"apple": None}, "apple") == ''


def test_get_value_with_no_key():
    """
    Test case for input with no existing key
    """
    with pytest.raises(KeyError):
        get_value({"apple": "10"}, "no_apple")


def test_get_value_with_boolean():
    """
    Test case for boolean input.
    """
    assert get_value({"apple": "1"}, "apple", bool) is True


def test_get_value_with_invalid_value_type():
    """
    Test case for input with invalid value type
    """
    assert get_value({"apple": "abc"}, "apple", int) == 0


##############################################
# Test cases for is_numeric
##############################################
def test_is_numeric_with_integer():
    """
    Test case for integer input.
    """
    assert is_numeric(10) is True


def test_is_numeric_with_float():
    """
    Test case for float input.
    """
    assert is_numeric(10.5) is True


def test_is_numeric_with_negative_number():
    """
    Test case for negative number input.
    """
    assert is_numeric(-10) is True


def test_is_numeric_with_string_number():
    """
    Test case for string number input.
    """
    assert is_numeric("10") is True


def test_is_numeric_with_string_negative_number():
    """
    Test case for string negative number input.
    """
    assert is_numeric("-10") is True


def test_is_numeric_with_non_numeric_string():
    """
    Test case for non-numeric string input.
    """
    assert is_numeric("apple") is False


def test_is_numeric_with_none_input():
    """
    Test case for None input.
    """
    assert is_numeric(None) is False


##############################################
# Test cases for parse_timestamp
##############################################
def test_parse_timestamp_with_integer_string():
    """
    Test case for integer string input.
    """
    assert parse_timestamp("1617926400000") == 1617926400000


def test_parse_timestamp_with_float_string():
    """
    Test case for float string input.
    """
    assert parse_timestamp("1617926400000.123") == 1617926400000.123


def test_parse_timestamp_with_datetime_string():
    """
    Test case for datetime string input.
    """
    assert parse_timestamp("2021-04-09T00:00:00") == int(np.datetime64("2021-04-09T00:00:00", 'ns'))


def test_parse_timestamp_with_non_numeric_string():
    """
    Test case for non-numeric string input.
    """
    assert parse_timestamp("apple") is None


def test_parse_timestamp_with_none_input():
    """
    Test case for None input.
    """
    assert parse_timestamp(None) is None
