from mint.models.mtSignalsModel import Waypoint


def test_waypoint_initialization():
    """
    Test case for Waypoint initialization.
    """
    waypoint = Waypoint(idx=1, col_num=2, row_num=3, col_span=4, row_span=5, stack_num=6, signal_stack_id=7, ts_start=8,
                        ts_end=9, func=None, args=[], kwargs={})
    assert waypoint.idx == 1
    assert waypoint.col_num == 2
    assert waypoint.row_num == 3
    assert waypoint.col_span == 4
    assert waypoint.row_span == 5
    assert waypoint.stack_num == 6
    assert waypoint.signal_stack_id == 7
    assert waypoint.ts_start == 8
    assert waypoint.ts_end == 9
    assert waypoint.func is None
    assert waypoint.args == []
    assert waypoint.kwargs == {}


def test_waypoint_str_representation():
    """
    Test case for Waypoint string representation.
    """
    waypoint = Waypoint(idx=1, col_num=2, row_num=3, col_span=4, row_span=5, stack_num=6, signal_stack_id=7, ts_start=8,
                        ts_end=9, func=None, args=[], kwargs={})
    assert str(waypoint) == "c:2|r:3|sn:6|si:7"
