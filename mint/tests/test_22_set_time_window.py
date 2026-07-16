"""Tests for Set as Time Window: plot-range helper conversion, the access
mode range setters and the plot context-menu extender."""
import unittest
import unittest.mock
from unittest.mock import MagicMock

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.gui import plotRange
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    # MTPulseId (built unconditionally by MTDataRangeSelector) eventually
    # touches AppDataAccess.da.default_ds via PulseTable. Same idempotent
    # CSV bootstrap used by the rest of the suite.
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class PlotRangeHelperTests(unittest.TestCase):
    def _fake_canvas_with_plot(self, plot):
        canvas = MagicMock()
        canvas.plots = [[plot]]
        return canvas

    def test_returns_none_when_no_plots(self):
        canvas = MagicMock()
        canvas.plots = []
        self.assertIsNone(plotRange.read_x_range_ns(canvas, MagicMock()))

    def test_returns_none_when_parser_has_no_lut_entry(self):
        plot = MagicMock()
        plot.axes = [MagicMock(is_date=False)]
        canvas = self._fake_canvas_with_plot(plot)
        parser = MagicMock()
        parser._plot_impl_plot_lut = {}
        self.assertIsNone(plotRange.read_x_range_ns(canvas, parser))

    def test_pyqtgraph_view_to_ns_uses_axis_offset(self):
        plot = MagicMock()
        plot.axes = [MagicMock(is_date=True)]
        axis = MagicMock(spec=['offset'])
        axis.offset = 1_000_000_000_000
        impl_plot = MagicMock()
        impl_plot.getAxis = MagicMock(return_value=axis)
        canvas = self._fake_canvas_with_plot(plot)
        parser = MagicMock()
        parser.__class__ = type("PyQtGraphParser", (object,), {})
        parser._plot_impl_plot_lut = {id(plot): [impl_plot]}
        parser.get_impl_x_axis_limits = MagicMock(return_value=(13.0, 713.0))
        result = plotRange.read_x_range_ns(canvas, parser)
        self.assertEqual(result, (1_000_000_000_013, 1_000_000_000_713))

    def test_pyqtgraph_view_to_ns_prefers_get_real_value(self):
        plot = MagicMock()
        plot.axes = [MagicMock(is_date=True)]
        axis = MagicMock()
        axis.get_real_value = MagicMock(side_effect=lambda v: 1_000_000_000 + int(v))
        impl_plot = MagicMock()
        impl_plot.getAxis = MagicMock(return_value=axis)
        canvas = self._fake_canvas_with_plot(plot)
        parser = MagicMock()
        parser.__class__ = type("PyQtGraphParser", (object,), {})
        parser._plot_impl_plot_lut = {id(plot): [impl_plot]}
        parser.get_impl_x_axis_limits = MagicMock(return_value=(10.0, 20.0))
        result = plotRange.read_x_range_ns(canvas, parser)
        self.assertEqual(result, (1_000_000_010, 1_000_000_020))

    def test_matplotlib_days_to_ns_no_offset(self):
        plot = MagicMock()
        plot.axes = [MagicMock(is_date=True)]
        impl_plot = MagicMock()
        impl_plot.xaxis.get_major_formatter = MagicMock(
            return_value=MagicMock(offset_ns=0))
        canvas = self._fake_canvas_with_plot(plot)
        parser = MagicMock()
        parser.__class__ = type("MatplotlibParser", (object,), {})
        parser._plot_impl_plot_lut = {id(plot): [impl_plot]}
        # 19000 days since epoch → 19000 * 86400 * 1e9 ns
        parser.get_impl_x_axis_limits = MagicMock(return_value=(19000.0, 19000.5))
        result = plotRange.read_x_range_ns(canvas, parser)
        expected_start = int(19000.0 * 86_400 * 1_000_000_000)
        expected_end = int(19000.5 * 86_400 * 1_000_000_000)
        self.assertEqual(result, (expected_start, expected_end))

    def test_non_date_axis_rejected_by_read_x_range_ns(self):
        plot = MagicMock()
        plot.axes = [MagicMock(is_date=False)]
        impl_plot = MagicMock()
        canvas = self._fake_canvas_with_plot(plot)
        parser = MagicMock()
        parser.__class__ = type("MatplotlibParser", (object,), {})
        parser._plot_impl_plot_lut = {id(plot): [impl_plot]}
        parser.get_impl_x_axis_limits = MagicMock(return_value=(0.0, 659.6))
        self.assertIsNone(plotRange.read_x_range_ns(canvas, parser))

    def test_date_axis_rejected_by_read_x_range_pulse_seconds(self):
        plot = MagicMock()
        plot.axes = [MagicMock(is_date=True)]
        impl_plot = MagicMock()
        canvas = self._fake_canvas_with_plot(plot)
        parser = MagicMock()
        parser._plot_impl_plot_lut = {id(plot): [impl_plot]}
        parser.get_impl_x_axis_limits = MagicMock(return_value=(19000.0, 19000.5))
        self.assertIsNone(plotRange.read_x_range_pulse_seconds(canvas, parser))

    def test_pulse_seconds_returns_raw_floats(self):
        plot = MagicMock()
        plot.axes = [MagicMock(is_date=False)]
        impl_plot = MagicMock()
        canvas = self._fake_canvas_with_plot(plot)
        parser = MagicMock()
        parser._plot_impl_plot_lut = {id(plot): [impl_plot]}
        parser.get_impl_x_axis_limits = MagicMock(return_value=(120.5, 480.25))
        result = plotRange.read_x_range_pulse_seconds(canvas, parser)
        self.assertEqual(result, (120.5, 480.25))

    def test_pulse_seconds_returns_none_when_no_plots(self):
        canvas = MagicMock()
        canvas.plots = []
        self.assertIsNone(
            plotRange.read_x_range_pulse_seconds(canvas, MagicMock()))


class SetTimeWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_force_apply_switches_from_pulse_to_time_range(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.TIME_RANGE})
        try:
            selector.stack.setCurrentIndex(1)
            selector.force_apply_canvas_range_ns(
                1_641_760_133_123_456_789, 1_641_760_833_123_456_789)
            self.assertEqual(selector.stack.currentIndex(), 0)
            abs_mode = selector.accessModes[0]
            self.assertEqual(abs_mode.fromTimeNs.text(), "123456789")
            self.assertEqual(abs_mode.toTimeNs.text(), "123456789")
        finally:
            selector.deleteLater()

    def test_force_apply_when_already_in_time_range(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.TIME_RANGE})
        try:
            self.assertEqual(selector.stack.currentIndex(), 0)
            selector.force_apply_canvas_range_ns(
                1_641_760_133_123_456_789, 1_641_760_833_123_456_789)
            self.assertEqual(selector.stack.currentIndex(), 0)
        finally:
            selector.deleteLater()

    def test_force_apply_syncs_model_for_draw_and_export(self):
        # Regression (#107 / IDV-756): set_from_ns must push the zoom range
        # into the backing model, not just the widgets. properties() — and
        # through it get_time_range(), consumed by draw/export/save — reads
        # from the model, so without the sync "Set as time window" would leave
        # the plot on the previous range even though the fields show the new one.
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.TIME_RANGE})
        try:
            selector.force_apply_canvas_range_ns(
                1_641_760_133_123_456_789, 1_641_760_833_123_456_789)
            props = selector.accessModes[0].properties()
            # 1_641_760_133.123456789 s → 2022-01-09T20:28:53 UTC (+123456789 ns);
            # 1_641_760_833.123456789 s → 2022-01-09T20:40:33 UTC.
            self.assertEqual(props["ts_start"], "2022-01-09T20:28:53")
            self.assertEqual(props["ts_end"], "2022-01-09T20:40:33")
            self.assertEqual(props["ts_ns_start"], "123456789")
            self.assertEqual(props["ts_ns_end"], "123456789")
        finally:
            selector.deleteLater()

    def test_apply_pulse_seconds_respects_unit_and_keeps_mode(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.PULSE_NUMBER})
        try:
            pulse_mode = selector.accessModes[1]
            pulse_mode.units.setCurrentIndex(1)
            pulse_idx = selector.stack.currentIndex()
            selector.apply_canvas_range_pulse_seconds(120.0, 480.0)
            self.assertEqual(selector.stack.currentIndex(), pulse_idx)
            self.assertEqual(pulse_mode.startTime.text(), "2")
            self.assertEqual(pulse_mode.endTime.text(), "8")
            self.assertEqual(pulse_mode.units.currentText(), "Minute(s)")
            props = pulse_mode.properties()
            self.assertEqual(props["t_start"], "2")
            self.assertEqual(props["t_end"], "8")
            self.assertEqual(props["base"], 60)
        finally:
            selector.deleteLater()

    def test_apply_pulse_seconds_seconds_unit_passthrough(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.PULSE_NUMBER})
        try:
            pulse_mode = selector.accessModes[1]
            pulse_mode.units.setCurrentIndex(0)
            selector.apply_canvas_range_pulse_seconds(123.456, 789.0)
            self.assertEqual(pulse_mode.startTime.text(), "123.456")
            self.assertEqual(pulse_mode.endTime.text(), "789")
            props = pulse_mode.properties()
            self.assertEqual(props["t_start"], "123.456")
            self.assertEqual(props["t_end"], "789")
        finally:
            selector.deleteLater()

    def test_apply_pulse_seconds_preserves_pulse_number(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.PULSE_NUMBER})
        try:
            pulse_mode = selector.accessModes[1]
            pulse_mode.pulseNumber.setText("12345")
            pulse_mode.units.setCurrentIndex(0)
            selector.apply_canvas_range_pulse_seconds(1.0, 2.0)
            self.assertEqual(pulse_mode.pulseNumber.text(), "12345")
            self.assertEqual(pulse_mode.properties()["pulse_nb"], ["12345"])
        finally:
            selector.deleteLater()

    def test_from_dict_restores_hour_unit_after_export(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.PULSE_NUMBER})
        try:
            pulse_mode = selector.accessModes[1]
            pulse_mode.from_dict({
                "pulse_nb": ["ITER:test/1"],
                "base": 3600,
                "t_start": "0.339317",
                "t_end": "0.417859",
            })
            self.assertEqual(pulse_mode.units.currentText(), "Hour(s)")
            self.assertEqual(pulse_mode.units.currentIndex(), 2)
            props = pulse_mode.properties()
            self.assertEqual(props["base"], 3600)
            self.assertEqual(props["t_start"], "0.339317")
            self.assertEqual(props["t_end"], "0.417859")
        finally:
            selector.deleteLater()

    def test_from_dict_handles_minute_and_day_units(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.PULSE_NUMBER})
        try:
            pulse_mode = selector.accessModes[1]
            pulse_mode.from_dict({"pulse_nb": [], "base": 60, "t_start": "1", "t_end": "2"})
            self.assertEqual(pulse_mode.units.currentText(), "Minute(s)")
            pulse_mode.from_dict({"pulse_nb": [], "base": 86400, "t_start": "1", "t_end": "2"})
            self.assertEqual(pulse_mode.units.currentText(), "Day(s)")
        finally:
            selector.deleteLater()

    def test_from_dict_falls_back_to_seconds_on_unknown_base(self):
        from mint.gui.mtDataRangeSelector import MTDataRangeSelector
        from mint.models import MTGenericAccessMode

        selector = MTDataRangeSelector({"mode": MTGenericAccessMode.PULSE_NUMBER})
        try:
            pulse_mode = selector.accessModes[1]
            pulse_mode.from_dict({"pulse_nb": [], "base": "garbage", "t_start": "", "t_end": ""})
            self.assertEqual(pulse_mode.units.currentText(), "Second(s)")
        finally:
            selector.deleteLater()

    def test_format_pulse_time_handles_non_finite_values(self):
        from mint.models.accessModes.mtPulseId import MTPulseId
        self.assertEqual(MTPulseId._format_pulse_time(float("inf")), "0")
        self.assertEqual(MTPulseId._format_pulse_time(float("-inf")), "0")
        self.assertEqual(MTPulseId._format_pulse_time(float("nan")), "0")
        self.assertEqual(MTPulseId._format_pulse_time(0.0), "0")
        self.assertEqual(MTPulseId._format_pulse_time(1.5), "1.5")
        self.assertEqual(MTPulseId._format_pulse_time(-3.0), "-3")

    def test_install_registers_context_menu_extender(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        mw_mod.MTMainWindow._install_set_time_window(fake_self)
        parser = fake_self.canvasStack.currentWidget.return_value._parser
        self.assertIs(parser.context_menu_extender,
                      fake_self._extend_plot_context_menu)

    def test_extender_disables_set_time_window_when_axis_not_date(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self.dataRangeSelector.is_x_axis_date.return_value = False
        fake_self.dataRangeSelector.is_x_axis_pulse_relative.return_value = False
        menu = MagicMock()
        mw_mod.MTMainWindow._extend_plot_context_menu(fake_self, menu)
        menu.addSeparator.assert_called_once()
        self.assertEqual(menu.addAction.call_count, 1)
        menu.addAction.return_value.setEnabled.assert_called_with(False)

    def test_extender_enables_time_window_in_pulse_mode(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self.dataRangeSelector.is_x_axis_date.return_value = False
        fake_self.dataRangeSelector.is_x_axis_pulse_relative.return_value = True
        menu = MagicMock()
        mw_mod.MTMainWindow._extend_plot_context_menu(fake_self, menu)
        menu.addAction.return_value.setEnabled.assert_called_with(True)


class CanvasAxisGatingTests(unittest.TestCase):
    def _fake_self(self, *, is_date: bool):
        fake_self = MagicMock()
        fake_self.dataRangeSelector.is_x_axis_date.return_value = is_date
        return fake_self

    def test_set_time_window_noop_when_no_visible_range(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self(is_date=True)
        fake_self.dataRangeSelector.is_x_axis_pulse_relative.return_value = False
        with unittest.mock.patch.object(mw_mod, "read_x_range_ns",
                                        return_value=None):
            mw_mod.MTMainWindow.on_set_time_window(fake_self)
        fake_self.dataRangeSelector.force_apply_canvas_range_ns.assert_not_called()

    def test_set_time_window_pulse_mode_routes_to_pulse_seconds(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self(is_date=False)
        fake_self.dataRangeSelector.is_x_axis_pulse_relative.return_value = True
        with unittest.mock.patch.object(mw_mod, "read_x_range_pulse_seconds",
                                        return_value=(120.0, 480.0)) as rpr:
            mw_mod.MTMainWindow.on_set_time_window(fake_self)
        rpr.assert_called_once()
        fake_self.dataRangeSelector.apply_canvas_range_pulse_seconds.assert_called_once_with(120.0, 480.0)
        fake_self.dataRangeSelector.force_apply_canvas_range_ns.assert_not_called()

    def test_set_time_window_pulse_mode_noop_when_no_visible_range(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self(is_date=False)
        fake_self.dataRangeSelector.is_x_axis_pulse_relative.return_value = True
        with unittest.mock.patch.object(mw_mod, "read_x_range_pulse_seconds",
                                        return_value=None):
            mw_mod.MTMainWindow.on_set_time_window(fake_self)
        fake_self.dataRangeSelector.apply_canvas_range_pulse_seconds.assert_not_called()


if __name__ == "__main__":
    unittest.main()
