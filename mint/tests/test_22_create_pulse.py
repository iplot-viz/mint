"""Tests for the Create Pulse feature: dialog validation, plot-range
helper conversion, and MTMainWindow feature gating against UDA
write capability."""
import unittest
import unittest.mock
from unittest.mock import MagicMock

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.gui.mtCreatePulseDialog import (
    DESCRIPTION_MAX_CHARS, MTCategoryPicker, MTCreatePulseDialog,
    PULSE_STATUS_OPTIONS, TIME_FORMAT, format_ns_range_for_humans, join_ns,
    split_ns,
)
from mint.gui import plotRange
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    # MTPulseId (built unconditionally by MTDataRangeSelector) eventually
    # touches AppDataAccess.da.default_ds via PulseTable. Same idempotent
    # CSV bootstrap used by the rest of the suite.
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class FormatRangeTests(unittest.TestCase):
    def test_zero_duration_reports_seconds(self):
        text = format_ns_range_for_humans(0, 0)
        self.assertIn("0s", text)

    def test_known_range_includes_hour_marker(self):
        # 2026-05-15 10:00:00 UTC → 11:15:00 UTC
        start = 1_778_961_600_000_000_000
        end = start + (75 * 60 * 1_000_000_000)
        text = format_ns_range_for_humans(start, end)
        self.assertIn("1h", text)
        self.assertIn("15m", text)

    def test_inverted_range_is_flagged(self):
        text = format_ns_range_for_humans(2, 1)
        self.assertIn("invalid", text.lower())

    def test_summary_stays_on_whole_seconds(self):
        # Dividing the epoch as a float used to round the sub-second digits
        # into the summary, contradicting the exact value in its own field.
        text = format_ns_range_for_humans(1_641_760_133_123_456_789,
                                          1_641_760_193_987_654_321)
        self.assertIn("2022-01-09 20:28:53 UTC", text)
        self.assertNotIn(".", text)
        self.assertIn("1m", text)


class TimeEntryTests(unittest.TestCase):
    """The range is entered as a wall-clock UTC date-time plus a nanosecond
    remainder, mirroring the From/To fields of the data range selector."""

    # 2022-01-09T20:28:53.123456789 UTC
    SAMPLE_NS = 1_641_760_133_123_456_789

    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()

    def test_split_reads_utc_regardless_of_the_local_zone(self):
        shown, fraction = split_ns(self.SAMPLE_NS)
        self.assertEqual(shown.toString(TIME_FORMAT), "2022-01-09T20:28:53")
        self.assertEqual(fraction, "123456789")

    def test_sub_second_digits_survive_the_round_trip(self):
        shown, fraction = split_ns(self.SAMPLE_NS)
        self.assertEqual(join_ns(shown, fraction), self.SAMPLE_NS)

    def test_fraction_is_zero_padded_to_nine_digits(self):
        _, fraction = split_ns(1_000_000_000 + 42)
        self.assertEqual(fraction, "000000042")

    def test_editors_show_the_range_and_report_it_back(self):
        d = MTCreatePulseDialog()
        try:
            d.populate([], self.SAMPLE_NS, self.SAMPLE_NS + 60 * 1_000_000_000)
            self.assertEqual(d.startTime.dateTime().toString(TIME_FORMAT),
                             "2022-01-09T20:28:53")
            self.assertEqual(d.startTimeNs.text(), "123456789")
            self.assertEqual(d.range_ns()[0], self.SAMPLE_NS)
        finally:
            d.close()

    def test_editing_the_date_time_moves_the_reported_range(self):
        d = MTCreatePulseDialog()
        try:
            d.populate([], self.SAMPLE_NS, self.SAMPLE_NS + 1_000_000_000)
            d.startTime.setDateTime(d.startTime.dateTime().addSecs(3600))
            self.assertEqual(d.range_ns()[0], self.SAMPLE_NS + 3600 * 1_000_000_000)
        finally:
            d.close()

    def test_range_preview_follows_the_editors(self):
        d = MTCreatePulseDialog()
        try:
            d.populate([], self.SAMPLE_NS, self.SAMPLE_NS + 1_000_000_000)
            d.endTime.setDateTime(d.endTime.dateTime().addSecs(15 * 60))
            self.assertIn("15m", d.rangePreview.text())
        finally:
            d.close()


class CategorySearchTests(unittest.TestCase):
    """Free-text category with a search button over the catalog, so a long
    server list stays usable."""

    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()

    def test_search_is_offered_when_the_catalog_has_entries(self):
        d = MTCreatePulseDialog()
        try:
            d.populate(["ITER:MCTB-SIMU", "ITER:local"], 1, 2)
            self.assertTrue(d.categorySearchButton.isEnabled())
        finally:
            d.close()

    def test_search_is_disabled_when_the_catalog_is_empty(self):
        d = MTCreatePulseDialog()
        try:
            d.populate([], 1, 2)
            self.assertFalse(d.categorySearchButton.isEnabled())
        finally:
            d.close()

    def test_search_is_disabled_in_update_mode(self):
        d = MTCreatePulseDialog()
        try:
            d.populate(["ITER:MCTB-SIMU"], 1, 2, pulse_id="ITER:MCTB-SIMU/1")
            self.assertFalse(d.categorySearchButton.isEnabled())
        finally:
            d.close()

    def test_picker_filters_on_any_part_of_the_name(self):
        picker = MTCategoryPicker(["MCTB-SIMU", "CREATE-SIMULATION", "local"])
        try:
            picker.filterEdit.setText("simu")
            visible = [picker.listWidget.item(r).text()
                       for r in range(picker.listWidget.count())
                       if not picker.listWidget.item(r).isHidden()]
            self.assertEqual(visible, ["MCTB-SIMU", "CREATE-SIMULATION"])
            self.assertEqual(picker.selected_category(), "MCTB-SIMU")
        finally:
            picker.close()

    def test_picker_stays_bounded_and_scrolls_with_hundreds_of_categories(self):
        # Production serves hundreds of categories; the window must not grow
        # with them — the list scrolls.
        picker = MTCategoryPicker([f"CAT-{i:03d}" for i in range(300)])
        try:
            picker.show()
            self.app.processEvents()
            self.assertLessEqual(picker.height(), 600)
            self.assertGreater(picker.listWidget.verticalScrollBar().maximum(), 0)
        finally:
            picker.close()

    def test_picker_returns_nothing_when_the_filter_matches_nothing(self):
        picker = MTCategoryPicker(["MCTB-SIMU", "local"])
        try:
            picker.filterEdit.setText("zzz")
            self.assertIsNone(picker.selected_category())
        finally:
            picker.close()

    def test_chosen_category_lands_in_the_field(self):
        d = MTCreatePulseDialog()
        try:
            d.populate(["ITER:MCTB-SIMU", "ITER:local"], 1, 2)
            picker = MTCategoryPicker(d._categories, d)
            picker.filterEdit.setText("local")
            d.categoryCombo.setCurrentText(picker.selected_category())
            self.assertEqual(d.result_dict()["category"], "local")
            picker.close()
        finally:
            d.close()


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()

    def _new_dialog(self):
        d = MTCreatePulseDialog()
        d.populate(["ITER:local", "ITER:test"], 1_000_000_000, 2_000_000_000)
        d.descriptionEdit.setPlainText("test pulse")
        return d

    def test_populate_fills_fields(self):
        d = self._new_dialog()
        self.assertEqual(d.categoryCombo.count(), 2)
        self.assertEqual(d.range_ns(), (1_000_000_000, 2_000_000_000))
        d.close()

    def test_status_options_match_contract(self):
        d = self._new_dialog()
        labels = [d.statusCombo.itemText(i) for i in range(d.statusCombo.count())]
        self.assertEqual(labels, PULSE_STATUS_OPTIONS)
        d.close()

    def test_result_dict_round_trips(self):
        d = self._new_dialog()
        d.categoryCombo.setCurrentText("local")
        d.statusCombo.setCurrentText("aborted")
        d.descriptionEdit.setPlainText("foo bar")
        result = d.result_dict()
        self.assertEqual(result["location"], "ITER")
        self.assertEqual(result["category"], "local")
        self.assertIsNone(result["pulse_number"])
        self.assertEqual(result["status"], "aborted")
        self.assertEqual(result["start_ns"], 1_000_000_000)
        self.assertEqual(result["end_ns"], 2_000_000_000)
        self.assertEqual(result["description"], "foo bar")
        d.close()

    def test_validate_rejects_inverted_range(self):
        problem = MTCreatePulseDialog._validate({
            "location": "ITER", "category": "x", "status": "completed",
            "start_ns": 2, "end_ns": 1, "description": "x",
        })
        self.assertIn("End time", problem)

    def test_validate_rejects_empty_description(self):
        problem = MTCreatePulseDialog._validate({
            "location": "ITER", "category": "x", "status": "completed",
            "start_ns": 1, "end_ns": 2, "description": "  ",
        })
        # populate() sets empty description; user must add text
        self.assertIn("description", problem.lower())

    def test_validate_rejects_overlong_description(self):
        problem = MTCreatePulseDialog._validate({
            "location": "ITER", "category": "x", "status": "completed",
            "start_ns": 1, "end_ns": 2, "description": "x" * (DESCRIPTION_MAX_CHARS + 1),
        })
        self.assertIn(str(DESCRIPTION_MAX_CHARS), problem)

    def test_validate_accepts_valid_payload(self):
        problem = MTCreatePulseDialog._validate({
            "location": "ITER", "category": "local", "status": "completed",
            "start_ns": 1, "end_ns": 2, "description": "ok",
        })
        self.assertIsNone(problem)

    def test_validate_rejects_separators_in_location_and_category(self):
        base = {"status": "completed", "start_ns": 1, "end_ns": 2,
                "description": "ok"}
        problem = MTCreatePulseDialog._validate(
            {**base, "location": "ITER:x", "category": "local"})
        self.assertIn("location", problem.lower())
        problem = MTCreatePulseDialog._validate(
            {**base, "location": "ITER", "category": "a/b"})
        self.assertIn("category", problem.lower())

    def test_validate_rejects_empty_location(self):
        problem = MTCreatePulseDialog._validate({
            "location": "", "category": "local", "status": "completed",
            "start_ns": 1, "end_ns": 2, "description": "ok",
        })
        self.assertIn("location", problem.lower())

    def test_category_is_free_text_even_with_empty_catalog(self):
        d = MTCreatePulseDialog()
        d.populate([], 1, 2)
        try:
            self.assertTrue(d.categoryCombo.isEditable())
            d.categoryCombo.setCurrentText("MY-NEW-CATEGORY")
            self.assertEqual(d.result_dict()["category"], "MY-NEW-CATEGORY")
        finally:
            d.close()

    def test_pulse_number_round_trips_as_int(self):
        d = self._new_dialog()
        d.pulseNumberEdit.setText("20260526")
        try:
            self.assertEqual(d.result_dict()["pulse_number"], 20260526)
        finally:
            d.close()

    def test_location_prefilled_with_iter_and_editable(self):
        d = self._new_dialog()
        try:
            self.assertEqual(d.locationEdit.text(), "ITER")
            self.assertTrue(d.locationEdit.isEnabled())
            d.locationEdit.setText("W7X")
            self.assertEqual(d.result_dict()["location"], "W7X")
        finally:
            d.close()


class PlotRangeHelperTests(unittest.TestCase):
    def _fake_canvas_with_plot(self, plot):
        canvas = MagicMock()
        canvas.plots = [[plot]]
        return canvas

    def _fake_parser(self, backend: str, impl_plot, limits):
        parser = MagicMock()
        parser.__class__ = type(f"{backend}Parser", (object,), {})
        parser._plot_impl_plot_lut = {id_key: [impl_plot] for id_key in ()}
        parser.get_impl_x_axis_limits = MagicMock(return_value=limits)
        return parser

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


class WriteableUdaSourceTests(unittest.TestCase):
    def test_returns_capable_source_when_available(self):
        from mint.gui import mtMainWindow as mw_mod

        capable = MagicMock()
        capable.is_write_capable = MagicMock(return_value=True)
        other = MagicMock(spec=[])  # no is_write_capable

        fake_self = MagicMock()
        fake_self.da.get_connected_data_source_names.return_value = ["csv", "uda"]
        fake_self.da.get_data_source = MagicMock(side_effect=lambda n: {"csv": other, "uda": capable}[n])

        result = mw_mod.MTMainWindow._writeable_uda_source(fake_self)
        self.assertIs(result, capable)

    def test_returns_none_when_no_source_is_write_capable(self):
        from mint.gui import mtMainWindow as mw_mod

        not_capable = MagicMock()
        not_capable.is_write_capable = MagicMock(return_value=False)
        fake_self = MagicMock()
        fake_self.da.get_connected_data_source_names.return_value = ["uda"]
        fake_self.da.get_data_source = MagicMock(return_value=not_capable)

        result = mw_mod.MTMainWindow._writeable_uda_source(fake_self)
        self.assertIsNone(result)


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
        fake_self._writeable_uda_source.return_value = None
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
        fake_self._writeable_uda_source.return_value = None
        menu = MagicMock()
        mw_mod.MTMainWindow._extend_plot_context_menu(fake_self, menu)
        menu.addAction.return_value.setEnabled.assert_called_with(True)

    def test_extender_never_adds_create_pulse_even_when_uda_writeable(self):
        # Pulse creation is offered from the toolbar only; the context menu
        # must not grow a second way to do it.
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self.dataRangeSelector.is_x_axis_date.return_value = True
        fake_self.dataRangeSelector.is_x_axis_pulse_relative.return_value = False
        fake_self._writeable_uda_source.return_value = MagicMock()
        menu = MagicMock()
        mw_mod.MTMainWindow._extend_plot_context_menu(fake_self, menu)
        self.assertEqual(menu.addAction.call_count, 1)
        self.assertEqual(menu.addAction.call_args[0][0], "Set as time window")


class UpdatePulseDialogTests(unittest.TestCase):
    """Dialog covers both Create and Update via the same form."""

    @classmethod
    def setUpClass(cls):
        cls.app = ensure_qapp()

    def test_create_mode_keeps_category_editable_and_pulse_id_none(self):
        d = MTCreatePulseDialog()
        d.populate(["ITER:local"], 1, 2)
        try:
            self.assertTrue(d.categoryCombo.isEnabled())
            self.assertIsNone(d.result_dict()["pulse_id"])
            self.assertIn("Create", d.windowTitle())
        finally:
            d.close()

    def test_update_mode_locks_category_and_surfaces_pulse_id(self):
        d = MTCreatePulseDialog()
        d.populate(["ITER:test"], 100, 200,
                   pulse_id="ITER:test/42",
                   current_status="aborted",
                   current_description="previous run")
        try:
            self.assertFalse(d.categoryCombo.isEnabled())
            self.assertFalse(d.locationEdit.isEnabled())
            self.assertFalse(d.pulseNumberEdit.isEnabled())
            self.assertEqual(d.locationEdit.text(), "ITER")
            self.assertEqual(d.categoryCombo.currentText(), "test")
            self.assertEqual(d.pulseNumberEdit.text(), "42")
            self.assertEqual(d.statusCombo.currentText(), "aborted")
            self.assertEqual(d.descriptionEdit.toPlainText(), "previous run")
            self.assertIn("ITER:test/42", d.windowTitle())
            result = d.result_dict()
            self.assertEqual(result["pulse_id"], "ITER:test/42")
        finally:
            d.close()

    def test_update_mode_injects_scope_when_missing_from_categories(self):
        # If the categories list doesn't contain the pulse's own scope
        # we still want it selected so the user sees what they're editing.
        d = MTCreatePulseDialog()
        d.populate(["ITER:other"], 100, 200, pulse_id="ITER:MCTB-SIMU/7")
        try:
            self.assertEqual(d.categoryCombo.currentText(), "MCTB-SIMU")
            self.assertEqual(d.locationEdit.text(), "ITER")
            self.assertEqual(d.pulseNumberEdit.text(), "7")
        finally:
            d.close()

    def test_switching_back_to_create_mode_re_enables_category(self):
        d = MTCreatePulseDialog()
        d.populate(["ITER:local"], 1, 2, pulse_id="ITER:local/1")
        d.populate(["ITER:local"], 3, 4)  # back to create
        try:
            self.assertTrue(d.categoryCombo.isEnabled())
            self.assertIsNone(d.result_dict()["pulse_id"])
            self.assertIn("Create", d.windowTitle())
        finally:
            d.close()


class PulseSubmissionRoutingTests(unittest.TestCase):
    """_on_pulse_submitted routes to add_pulse_info or update_pulse_info
    based on whether the dialog carries a pulse_id."""

    def _fake_self_with_uda(self):
        fake_self = MagicMock()
        fake_self._writeable_uda_source.return_value = fake_self._uda
        fake_self._uda.add_pulse_info.return_value = {"ok": True, "pulse_id": "ITER:test/99"}
        fake_self._uda.update_pulse_info.return_value = {"ok": True}
        return fake_self

    def test_create_path_calls_add_pulse_info(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self_with_uda()
        data = {"pulse_id": None, "location": "ITER", "category": "test",
                "pulse_number": None, "start_ns": 1, "end_ns": 2,
                "status": "completed", "description": "first"}
        with unittest.mock.patch.object(mw_mod, "QMessageBox") as mb:
            mw_mod.MTMainWindow._on_pulse_submitted(fake_self, data)
        fake_self._uda.add_pulse_info.assert_called_once_with(
            "ITER:test", 1, 2, "completed", "first", pulse_number=None)
        fake_self._uda.update_pulse_info.assert_not_called()
        # Success closes the dialog and confirms with the created pulse id.
        fake_self.createPulseDialog.accept.assert_called_once()
        self.assertIn("ITER:test/99", mb.information.call_args[0][2])

    def test_create_path_passes_user_pulse_number(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self_with_uda()
        data = {"pulse_id": None, "location": "ITER", "category": "test",
                "pulse_number": 20260526, "start_ns": 1, "end_ns": 2,
                "status": "completed", "description": "first"}
        with unittest.mock.patch.object(mw_mod, "QMessageBox"):
            mw_mod.MTMainWindow._on_pulse_submitted(fake_self, data)
        fake_self._uda.add_pulse_info.assert_called_once_with(
            "ITER:test", 1, 2, "completed", "first", pulse_number=20260526)

    def test_failed_create_warns_and_keeps_dialog_open(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self_with_uda()
        fake_self._uda.add_pulse_info.return_value = {
            "ok": False, "error": "pulse ITER:test/1 already exists"}
        data = {"pulse_id": None, "location": "ITER", "category": "test",
                "pulse_number": 1, "start_ns": 1, "end_ns": 2,
                "status": "completed", "description": "first"}
        with unittest.mock.patch.object(mw_mod, "QMessageBox") as mb:
            mw_mod.MTMainWindow._on_pulse_submitted(fake_self, data)
        mb.warning.assert_called_once()
        fake_self.createPulseDialog.accept.assert_not_called()

    def test_create_with_number_on_old_data_access_warns_and_aborts(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self_with_uda()
        fake_self._uda.add_pulse_info.side_effect = TypeError(
            "unexpected keyword argument 'pulse_number'")
        data = {"pulse_id": None, "location": "ITER", "category": "test",
                "pulse_number": 20260526, "start_ns": 1, "end_ns": 2,
                "status": "completed", "description": "first"}
        with unittest.mock.patch.object(mw_mod, "QMessageBox") as mb:
            mw_mod.MTMainWindow._on_pulse_submitted(fake_self, data)
        mb.warning.assert_called_once()
        fake_self._uda.update_pulse_info.assert_not_called()

    def test_update_path_calls_update_pulse_info(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self_with_uda()
        data = {"pulse_id": "ITER:test/42", "category": "ITER:test",
                "start_ns": 1, "end_ns": 2,
                "status": "aborted", "description": "fix"}
        with unittest.mock.patch.object(mw_mod, "QMessageBox"):
            mw_mod.MTMainWindow._on_pulse_submitted(fake_self, data)
        fake_self._uda.update_pulse_info.assert_called_once_with(
            "ITER:test/42", 1, 2, "aborted", "fix")
        fake_self._uda.add_pulse_info.assert_not_called()

    def test_no_op_when_uda_unavailable(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self._writeable_uda_source.return_value = None
        mw_mod.MTMainWindow._on_pulse_submitted(fake_self, {"pulse_id": None})


class UpdatePulseInstallTests(unittest.TestCase):
    """_install_update_pulse stays inert when any of its dependencies is
    missing (UDA writer, toolbar action, or pulseBrowser support)."""

    def test_skips_when_uda_not_writeable(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self._writeable_uda_source.return_value = None
        mw_mod.MTMainWindow._install_update_pulse(fake_self)
        fake_self.toolBar.updatePulseAction.setVisible.assert_not_called()

    def test_skips_when_toolbar_lacks_action(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self._writeable_uda_source.return_value = MagicMock()
        fake_self.toolBar = MagicMock(spec=[])  # no updatePulseAction
        mw_mod.MTMainWindow._install_update_pulse(fake_self)
        # Browser init should not be attempted.
        fake_self._get_pulse_browser_for_update.assert_not_called()

    def test_skips_when_pulseBrowser_lacks_update_support(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self._writeable_uda_source.return_value = MagicMock()
        fake_self.toolBar.updatePulseAction = MagicMock()
        fake_self._get_pulse_browser_for_update.return_value = None
        mw_mod.MTMainWindow._install_update_pulse(fake_self)
        fake_self.toolBar.updatePulseAction.setVisible.assert_not_called()

    def test_installs_when_everything_is_available(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = MagicMock()
        fake_self._writeable_uda_source.return_value = MagicMock()
        action = MagicMock()
        fake_self.toolBar.updatePulseAction = action
        fake_self._get_pulse_browser_for_update.return_value = MagicMock()
        mw_mod.MTMainWindow._install_update_pulse(fake_self)
        action.setVisible.assert_called_once_with(True)
        action.triggered.connect.assert_called_once()
        # The slot is a lambda absorbing `checked`; firing it must reach the handler.
        slot = action.triggered.connect.call_args[0][0]
        slot(False)
        fake_self.on_open_update_pulse_browser.assert_called_once_with()


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

    def test_create_pulse_opens_dialog_even_without_categories(self):
        # The category field is free text, so an empty catalog must not block.
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self(is_date=True)
        uda = MagicMock()
        uda.get_pulse_categories.return_value = []
        fake_self._writeable_uda_source.return_value = uda
        with unittest.mock.patch.object(mw_mod, "read_x_range_ns",
                                        return_value=(1, 2)):
            mw_mod.MTMainWindow.on_create_pulse(fake_self)
        fake_self.createPulseDialog.populate.assert_called_once_with([], 1, 2)
        fake_self.createPulseDialog.show.assert_called_once()

    def test_create_pulse_warns_when_axis_not_date(self):
        from mint.gui import mtMainWindow as mw_mod

        fake_self = self._fake_self(is_date=False)
        fake_self._writeable_uda_source.return_value = MagicMock()
        with unittest.mock.patch.object(mw_mod, "QMessageBox") as mb:
            mw_mod.MTMainWindow.on_create_pulse(fake_self)
        mb.information.assert_called_once()
        fake_self.createPulseDialog.populate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
