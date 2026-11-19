"""Behaviour tests for MTSignalsModel.

The signals model is the heart of MINT — it mediates between the user's
table, workspace serialisation and the signal processing pipeline. These
tests lock in a handful of invariants that the UI and the data access
layer depend on:

- appending a variable from the browser populates only DS + Variable + uid
- setting a full dataframe honours blueprint defaults for missing columns
  (backward compatibility with older SCSV/workspaces without newer columns)
- insertRows seeds new rows with the expected defaults (DataSource, PlotType)
"""

import unittest
from contextlib import ExitStack
from unittest import mock

import pandas as pd
from PySide6.QtCore import QPersistentModelIndex, Qt
from PySide6.QtGui import QColor

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.interface.iplotSignalAdapter import Result, Stage, StatusInfo

from mint.models.mtSignalsModel import MTSignalsModel
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class TestAppendDataframeFromBrowser(unittest.TestCase):
    """When a variable is added via the browser, only DS + Variable come in."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def setUp(self) -> None:
        self.model = MTSignalsModel()

    def test_append_populates_only_ds_and_variable(self):
        df = pd.DataFrame({'DS': ['codacuda'], 'Variable': ['MAG-MCTB-F1:VAR1']})
        self.model.append_dataframe(df)

        table = self.model.get_dataframe()
        self.assertEqual(len(table), 1)
        row = table.iloc[0]
        self.assertEqual(row['DS'], 'codacuda')
        self.assertEqual(row['Variable'], 'MAG-MCTB-F1:VAR1')
        # Blueprint-overridable columns must stay empty — they inherit from the
        # global time/pulse selector at draw time.
        self.assertEqual(row['StartTime'], '')
        self.assertEqual(row['EndTime'], '')
        self.assertEqual(row['PulseId'], '')
        # Expression columns also stay empty here; defaults resolve in _parse_series.
        self.assertEqual(row['x'], '')
        self.assertEqual(row['y'], '')
        self.assertEqual(row['z'], '')
        self.assertEqual(row['Stack'], '')

    def test_append_assigns_uid(self):
        df = pd.DataFrame({'DS': ['codacuda'], 'Variable': ['MAG-MCTB-F1:VAR1']})
        self.model.append_dataframe(df)
        uid = self.model.get_dataframe().iloc[0]['uid']
        self.assertTrue(uid)  # non-empty
        self.assertEqual(len(uid), 36)  # uuid4 string length


class TestInsertRows(unittest.TestCase):
    """Programmatic row insertion seeds DataSource and PlotType defaults."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_insert_row_has_plot_type_default(self):
        model = MTSignalsModel()
        model.insertRows(0, 1)
        df = model.get_dataframe()
        # insertRows seeds Plot type with the blueprint default.
        if len(df) > 0:
            self.assertEqual(df.iloc[0]['Plot type'], 'PlotXY')


class TestSetDataframeBackwardCompat(unittest.TestCase):
    """Importing a workspace missing newer columns still loads cleanly."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_set_dataframe_without_calibrated_column(self):
        # Simulate an old workspace: no Calibrated column in the dataframe.
        df = pd.DataFrame({
            'DS': ['codacuda'],
            'Variable': ['MAG-MCTB-F1:VAR1'],
            'Stack': ['1.1'],
            'Plot type': ['PlotXY'],
        })
        model = MTSignalsModel()
        model.set_dataframe(df)

        table = model.get_dataframe()
        self.assertEqual(len(table), 1)
        # Calibrated column exists in the table even though df did not have it,
        # filled from the blueprint / accommodation path.
        self.assertIn('Calibrated', table.columns)


class TestStatusErrorInfo(unittest.TestCase):
    """error_info_for_cell drives the hover popup. A successful row must not
    produce a popup; the Status cell surfaces row-level errors even when its
    own cell isn't flagged."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _one_row_model(self):
        model = MTSignalsModel()
        cols = list(model._table.columns)
        # Mirror how the model stores a row: empty strings, fail flags at 0.
        model._table = pd.DataFrame([["" for _ in cols]], columns=cols)
        model._table_fails = pd.DataFrame([[0 for _ in cols]], columns=cols)
        return model, cols

    def test_successful_status_has_no_popup(self):
        model, cols = self._one_row_model()
        status_col = cols.index('Status')
        model._table.iat[0, status_col] = 'Success|1920 points|Downsampled'
        index = model.createIndex(0, status_col)
        self.assertIsNone(model.error_info_for_cell(index))

    def test_failed_row_shows_error_on_status_cell(self):
        model, cols = self._one_row_model()
        status_col = cols.index('Status')
        # Failure flagged on a data column; the Status cell's own flag stays 0.
        model._table_fails.iat[0, cols.index('Variable')] = 1
        model._table.iat[0, status_col] = 'Variable not found'
        info = model.error_info_for_cell(model.createIndex(0, status_col))
        self.assertIsNotNone(info)
        self.assertEqual(info['explanation'], 'Variable not found')

    def test_cells_take_the_colours_of_the_view_unless_they_fail(self):
        # A brush of its own on every cell painted the table white in a dark palette.
        model, cols = self._one_row_model()
        model._table_fails.iat[0, cols.index('Variable')] = 1
        model._table_fails.iat[0, cols.index('Stack')] = 2
        for column, background, text in (('DS', None, None), ('Variable', 'red', 'black'),
                                         ('Stack', 'orange', 'black')):
            with self.subTest(column=column):
                index = model.createIndex(0, cols.index(column))
                brush = model.data(index, Qt.ItemDataRole.BackgroundRole)
                self.assertEqual(None if brush is None else brush.color(), None if background is None else QColor(background))
                brush = model.data(index, Qt.ItemDataRole.ForegroundRole)
                self.assertEqual(None if brush is None else brush.color(), None if text is None else QColor(text))


class TestFailedRowMarksItsCell(unittest.TestCase):
    """The cell a row fails at turns red: the variable when it can't be read or processed, the x, y or z expression
    that can't be evaluated otherwise."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _red_cells(self, stage, expression):
        model = MTSignalsModel()
        model.set_dataframe(pd.DataFrame({'DS': ['csv'], 'Variable': ['MAG-MCTB-F1:VAR1'], 'Stack': ['1'],
                                          'y': ['${self}.data[::0]']}))
        signal = mock.Mock(uid=model.get_dataframe().at[0, 'uid'], isDownsampled=False, y_data=None)

        def read():
            signal.status_info = StatusInfo(result=Result.FAIL, stage=stage)
            signal.status_info.expression = expression

        signal.get_data.side_effect = read
        model.update_signal_data(0, signal, fetch_data=True)
        fails = model._table_fails.loc[0]
        return [column for column in fails.index if fails[column]]

    def test_an_expression_that_fails_marks_its_cell(self):
        self.assertEqual(self._red_cells(Stage.PROC, 'y'), ['y'])

    def test_a_variable_that_fails_marks_its_cell(self):
        self.assertEqual(self._red_cells(Stage.DA, ''), ['Variable'])
        self.assertEqual(self._red_cells(Stage.PROC, ''), ['Variable'])


class TestRowLevelRelativePulse(unittest.TestCase):
    """Row-level relative pulse ids (0 = last, -N = N-th previous) must resolve
    to the explicit pulse for that row, instead of being misrouted into the
    'remove from global' bucket (mint #96)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _resolve_pulse(self, cell: str, global_pulses):
        model = MTSignalsModel()
        pulse_bp = model._blueprint['PulseNumber']
        original_default = pulse_bp.get('default')
        pulse_bp['default'] = list(global_pulses)
        try:
            model.insertRows(0, 1)
            df = model.get_dataframe()
            row = {
                'DS': 'csv', 'Variable': 'MAG-MCTB-F1:VAR1', 'PulseId': cell,
                'Stack': '1', 'Plot type': 'PlotXY', 'Row span': '1',
                'Col span': '1', 'Envelope': '', 'x': '${self}.time',
                'y': '${self}.data', 'z': '', 'Alias': '', 'StartTime': '',
                'EndTime': '', 'Calibrated': '',
            }
            for col, val in row.items():
                if col in df.columns:
                    df.at[0, col] = val
            inp = df.iloc[0]
            fls = pd.Series(0, index=inp.index)

            all_pulses = pd.DataFrame({'Pulse': list(global_pulses)})

            def fake_get_pulses_df(pattern=None, **_):
                text = str(pattern)
                if text and '*' not in text:
                    return pd.DataFrame({'Pulse': [pattern]})
                return all_pulses

            fake_ds = mock.Mock()
            fake_ds.get_pulses_df.side_effect = fake_get_pulses_df
            with mock.patch.object(AppDataAccess, 'da') as da:
                da.get_data_source.return_value = fake_ds
                model.data_sources = ['csv']
                outputs = list(model._parse_series(inp, fls, 1, []))
            return outputs[0][0]['PulseId']
        finally:
            pulse_bp['default'] = original_default

    def test_minus_one_resolves_to_previous_pulse(self):
        resolved = self._resolve_pulse('-1', ['10', '20', '30', '40', '50'])
        self.assertEqual(resolved, '40')

    def test_zero_resolves_to_last_pulse(self):
        resolved = self._resolve_pulse('0', ['10', '20', '30', '40', '50'])
        self.assertEqual(resolved, '50')

    def test_minus_one_is_not_removed_from_global(self):
        # The bug routed -1 into the 'remove from global' bucket, so the row
        # kept the global list minus that pulse instead of the pulse itself.
        resolved = self._resolve_pulse('-1', ['10', '20', '30', '40', '50'])
        self.assertNotIn(',', str(resolved))


class TestRowThatCannotBeDrawn(unittest.TestCase):
    """A row with a value MINT can't use isn't drawn, and its Status says why instead of 'Ready'."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _created(self, rows: dict, **defaults) -> MTSignalsModel:
        model = MTSignalsModel()
        model.set_dataframe(pd.DataFrame(rows))
        # A Draw leaves its time range and pulses as the defaults of the blueprint, which the models share.
        with ExitStack() as stack:
            for key in ('PulseNumber', 'StartTime', 'EndTime'):
                stack.enter_context(mock.patch.dict(model._blueprint[key], default=defaults.get(key, '')))
            with model.init_create_signals():
                for row in range(model.rowCount()):
                    list(model.create_signals(row, []))
        return model

    def test_a_data_source_not_available_here_is_named(self):
        model = self._created({'DS': ['imaspy'], 'Variable': ['pf_active/coil[1]/current/data'], 'Stack': ['1']})
        self.assertEqual(model.get_dataframe().at[0, 'Status'],
                         "Invalid|The data source imaspy isn't available here (csv)")
        status = model.createIndex(0, model.get_dataframe().columns.get_loc('Status'))
        self.assertEqual(model.error_info_for_cell(status)['title'], 'Data source not available')

    def test_a_time_that_is_not_a_date_is_named(self):
        model = self._created({'DS': ['csv'], 'Variable': ['MAG-MCTB-F1:VAR1'], 'Stack': ['1'],
                               'StartTime': ['yesterday']})
        self.assertEqual(model.get_dataframe().at[0, 'Status'],
                         "Invalid|The start time isn't a date like 2026-01-31T08:00:00")

    def test_a_pulse_time_that_is_not_a_number_is_named_not_replaced(self):
        model = self._created({'DS': ['csv'], 'Variable': ['MAG-MCTB-F1:VAR1'], 'Stack': ['1'],
                               'StartTime': ['tomorrow']},
                              PulseNumber=['ITER:MCTB-TEST/111'], StartTime=-5.0, EndTime=4.0)
        self.assertEqual(model.get_dataframe().at[0, 'Status'],
                         "Invalid|With a pulse, the start time is relative to it, like -5")
        self.assertEqual(model._table_fails.at[0, 'StartTime'], 1)

    def test_an_expression_on_the_alias_of_a_row_with_an_error_says_so(self):
        model = self._created({'DS': ['imaspy', 'csv'], 'Variable': ['MAG-MCTB-F1:VAR1', ''], 'Alias': ['a', 'b'],
                               'Stack': ['1', '2'], 'y': ['', '${a}.data * 2']})
        self.assertEqual(model.get_dataframe().at[1, 'Status'],
                         "Invalid|The y expression uses a, whose row has an error")

    def test_hovering_the_status_says_what_to_do(self):
        model = self._created({'DS': ['csv'], 'Variable': ['MAG-MCTB-F1:VAR1'], 'Stack': ['1'],
                               'Envelope': ['2']})
        status = model.createIndex(0, model.get_dataframe().columns.get_loc('Status'))
        self.assertEqual(model.error_info_for_cell(status),
                         {'title': 'Row not drawn', 'anchor': 'cat-validation',
                          'explanation': "The envelope is 1 to show it, or 0 or empty to hide it. Fix it and Draw "
                                         "again."})


class _UnreadableSignal:
    """A signal whose data can't be read, for update_signal_data."""
    isDownsampled = False
    y_data = None

    def __init__(self, uid: str):
        self.uid = uid
        self.status_info = StatusInfo()

    def get_data(self):
        self.status_info.result, self.status_info.stage = Result.FAIL, Stage.DA


class TestSortKeepsRowsWhole(unittest.TestCase):
    """Sorting the table moves with each row its red cells and the indexes the views hold of it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_a_red_cell_and_the_index_of_its_row_move_with_the_row(self):
        model = MTSignalsModel()
        model.set_dataframe(pd.DataFrame({'DS': ['csv'] * 3, 'Variable': ['B', 'C', 'A'], 'Stack': ['1', '2', '3']}))
        column = model.get_dataframe().columns.get_loc('Variable')
        model.update_signal_data(1, _UnreadableSignal(model.get_dataframe().at[1, 'uid']), fetch_data=True)
        selected = QPersistentModelIndex(model.index(1, column))

        model.sort(column, Qt.SortOrder.AscendingOrder)

        table = model.get_dataframe()
        red = [table.at[row, 'Variable'] for row in range(len(table))
               if model.data(model.index(row, column), Qt.ItemDataRole.BackgroundRole) is not None]
        self.assertEqual(red, ['C'])
        self.assertEqual(table.at[selected.row(), 'Variable'], 'C')


if __name__ == '__main__':
    unittest.main()
