from mint.tools.sanity_checks import check_data_range

def test_none_input():
    """
    Test case to check if the input is None
    """
    assert check_data_range(None) is False


def test_no_range_input():
    """
    Test case to check if the input has no range
    """
    assert check_data_range({ }) is False


def test_invalid_range_input():
    """
    Test case to check if the range is invalid
    """
    assert check_data_range({ 'range': 99 }) is False


def test_invalid_mode_input():
    """
    Test case to check if the range is invalid
    """
    assert check_data_range({'range': {'no_mode': 99}}) is False


def test_no_value_range_input():
    """
    Test case to check valid data range
    """
    assert check_data_range({'range': {'mode': 99, 'no_value': 99}}) is False


def test_valid_input():
    """
    Test case to check if the range is invalid
    """

    assert check_data_range({'range': {'mode': 99, 'value': 99}}) is True
