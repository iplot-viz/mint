"""Read the visible x-range of the active plot, in nanoseconds since epoch."""
from __future__ import annotations

from typing import Optional, Tuple

NS_PER_DAY = 86_400 * 1_000_000_000


def _first_plot(canvas) -> Optional[object]:
    plots_grid = getattr(canvas, "plots", None)
    if not plots_grid:
        return None
    for col in plots_grid:
        if not col:
            continue
        for plot in col:
            if plot is not None:
                return plot
    return None


def _impl_plot_for(parser, plot) -> Optional[object]:
    lut = getattr(parser, "_plot_impl_plot_lut", None)
    if not lut:
        return None
    impls = lut.get(id(plot))
    if not impls:
        return None
    return impls[0]


def _is_date_axis(plot) -> bool:
    try:
        return bool(plot.axes[0].is_date)
    except (AttributeError, IndexError, TypeError):
        return False


def _matplotlib_view_to_ns(value: float, impl_plot) -> int:
    formatter = getattr(impl_plot.xaxis, "get_major_formatter", None)
    offset_ns = 0
    if callable(formatter):
        offset_ns = getattr(formatter(), "offset_ns", 0) or 0
    if offset_ns == 100_000:
        return int(value * 100_000)
    if offset_ns > 0:
        return int(value + offset_ns)
    return int(value * NS_PER_DAY)


def _pyqtgraph_view_to_ns(value: float, impl_plot) -> int:
    try:
        axis = impl_plot.getAxis('bottom')
    except Exception:
        return int(value)
    real = getattr(axis, 'get_real_value', None)
    if callable(real):
        try:
            return int(real(value))
        except Exception:
            pass
    offset_ns = getattr(axis, 'offset', 0) or 0
    if offset_ns == 100_000:
        return int(value * 100_000)
    return int(value + offset_ns)


def read_x_range_ns(canvas, parser, plot=None) -> Optional[Tuple[int, int]]:
    """Return (start_ns, end_ns) for ``plot`` (the plot under the right-click),
    or the first plot when the caller passes none. None if unavailable."""
    if plot is None:
        plot = _first_plot(canvas)
    if plot is None:
        return None
    if not _is_date_axis(plot):
        return None
    impl_plot = _impl_plot_for(parser, plot)
    if impl_plot is None:
        return None
    try:
        x_min, x_max = parser.get_impl_x_axis_limits(impl_plot)
    except Exception:
        return None
    if x_min is None or x_max is None:
        return None
    backend = parser.__class__.__name__.lower()
    if "matplotlib" in backend:
        return _matplotlib_view_to_ns(x_min, impl_plot), _matplotlib_view_to_ns(x_max, impl_plot)
    if "pyqtgraph" in backend:
        return _pyqtgraph_view_to_ns(x_min, impl_plot), _pyqtgraph_view_to_ns(x_max, impl_plot)
    return int(x_min), int(x_max)


def read_x_range_pulse_seconds(canvas, parser, plot=None) -> Optional[Tuple[float, float]]:
    """Return (start_sec, end_sec) for ``plot`` (the plot under the right-click)
    in PULSE mode, or the first plot when the caller passes none."""
    if plot is None:
        plot = _first_plot(canvas)
    if plot is None:
        return None
    if _is_date_axis(plot):
        return None
    impl_plot = _impl_plot_for(parser, plot)
    if impl_plot is None:
        return None
    try:
        x_min, x_max = parser.get_impl_x_axis_limits(impl_plot)
    except Exception:
        return None
    if x_min is None or x_max is None:
        return None
    return float(x_min), float(x_max)
