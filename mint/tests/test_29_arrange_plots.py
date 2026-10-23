"""Moving and resizing plots on the canvas moves their rows in the table: the Stack of each row follows its plot and
Row span and Col span follow its size. Undo takes the rows back with the plots, a Draw draws the plots where they
went with the preferences each had, and moving a plot reads no data. The place of rows that drew no plot is kept for
them: it moves as a plot does, and no plot moves or grows over it."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from iplotlib.qt.gui.iplotQtCanvas import IplotQtCanvas
from mint.gui.mtMainWindow import MTMainWindow, _stack_place
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.mtSignalsModel import MAX_SPAN
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

try:
    from iplotlib.core import layout
    from iplotlib.qt.gui.iplotQtArrangement import HANDLE
except ImportError:
    layout = HANDLE = None

PULSE_ID = 'ITER:MCTB-TEST/111'
VARS = ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2', 'MAG-MCTB-F1:VAR3', 'MAG-MCTB-F1:VAR4', 'MAG-MCTB-F1:VAR5']
# A variable the data source does not have: its row draws no plot.
UNREAD = 'MAG-MCTB-F1:NONE'


def _table(win) -> list:
    df = win.sigCfgWidget.model.get_dataframe()
    return [(variable, stack, row_span, col_span) for variable, stack, row_span, col_span
            in zip(df['Variable'], df['Stack'], df['Row span'], df['Col span']) if variable]


def _set_variable(win, row: int, variable: str):
    df = win.sigCfgWidget.model.get_dataframe()
    win.sigCfgWidget.model.setData(win.sigCfgWidget.model.createIndex(row, df.columns.get_loc('Variable')), variable,
                                   Qt.ItemDataRole.EditRole)


def _set_cell(win, row: int, column: str, value: str):
    model = win.sigCfgWidget.model
    model.setData(model.createIndex(row, model.get_dataframe().columns.get_loc(column)), value,
                  Qt.ItemDataRole.EditRole)


def _overlapping(canvas) -> list:
    slots = [slot for _, slot in layout.slots_of(canvas)]
    return [(a, b) for i, a in enumerate(slots) for b in slots[i + 1:] if a.overlaps(b)]


def _plot_with(win, variable):
    signal, plot = win._find_signal_in_canvas(next(
        uid for uid, name in zip(win.sigCfgWidget.model.get_dataframe()['uid'],
                                 win.sigCfgWidget.model.get_dataframe()['Variable']) if name == variable))
    return plot


@unittest.skipUnless(layout is not None and hasattr(IplotQtCanvas, 'plotsArranged'),
                     "the installed iplotlib does not move plots")
class ArrangePlotsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        write_csv_datasource_config()
        AppDataAccess.initialize()
        AccessHelper.da = AppDataAccess.get_data_access()

    def setUp(self):
        self._pool = AccessHelper.pool
        self.addCleanup(setattr, AccessHelper, 'pool', self._pool)
        AccessHelper.pool = None

    def _window(self, stacks: list, impl: str = 'matplotlib', spans: dict = None, variables: list = None) \
            -> MTMainWindow:
        """A window that drew one row of the table for each Stack given, of VAR1 for the first one and so on, or of
        the variables given."""
        win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version='test',
                           data_sources=AccessHelper.da.get_connected_data_source_names(),
                           blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl=impl)
        self.addCleanup(win.close)
        win.dataRangeSelector.import_dict({'mode': MTGenericAccessMode.PULSE_NUMBER, 'pulse_nb': [PULSE_ID],
                                           'base': 'Second(s)', 't_start': '-5', 't_end': '4'})
        rows = {'DS': ['csv'] * len(stacks), 'Variable': variables or VARS[:len(stacks)], 'Stack': stacks,
                'Plot type': ['PlotXY'] * len(stacks)}
        rows.update(spans or {})
        win.sigCfgWidget.model.set_dataframe(pd.DataFrame(rows))
        win.draw_clicked()
        return win

    def _arrange(self, win, arrangement, name='Move plot'):
        win.canvasStack.currentWidget()._apply_arrangement(name, arrangement)
        self.app.processEvents()

    def test_the_rows_of_a_plot_moved_up_its_column_take_its_new_place(self):
        win = self._window(['1', '2', '3', '3.1.2'])

        self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[2]), 0, 0))

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['2', '3', '1', '1.1.2'])

    def test_a_plot_moved_with_the_mouse_moves_its_rows(self):
        for impl in ('matplotlib', 'pyqt'):
            with self.subTest(impl):
                win = self._window(['1.1', '2.1', '3.1'], impl=impl)
                win.resize(1200, 900)
                win.show()
                self.app.processEvents()
                qt_canvas = win.canvasStack.currentWidget()
                qt_canvas.set_mouse_mode(Canvas.MOUSE_MODE_SELECT)
                self.app.processEvents()
                widget = qt_canvas._arranger._widget
                rows, cols = qt_canvas._grid_bounds()
                x = cols[0] + (cols[1] - cols[0]) * 0.15

                def at(y):
                    return widget.mapFrom(qt_canvas, QPoint(round(x), round(y)))
                start, end = at(rows[2] + (rows[3] - rows[2]) * 0.2), at(rows[0] + (rows[1] - rows[0]) * 0.2)
                QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
                for step in range(1, 9):
                    QTest.mouseMove(widget, start + (end - start) * (step / 8))
                    self.app.processEvents()
                QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
                self.app.processEvents()

                self.assertEqual([stack for _, stack, _, _ in _table(win)], ['2.1', '3.1', '1.1'])

    def test_the_rows_of_a_resized_plot_take_its_span_and_those_below_move_down(self):
        win = self._window(['1', '2', '2.1.2', '3'])

        self._arrange(win, layout.resized(win.canvas, _plot_with(win, VARS[1]), 2, 1), 'Resize plot')

        self.assertEqual(_table(win), [(VARS[0], '1', '', ''), (VARS[1], '2', '2', ''), (VARS[2], '2.1.2', '2', ''),
                                       (VARS[3], '4', '', '')])

    def test_taking_the_row_span_off_a_plot_the_mouse_made_taller_brings_the_plots_below_back_up(self):
        win = self._window(['1', '2', '3', '4'])
        self._arrange(win, layout.resized(win.canvas, _plot_with(win, VARS[1]), 3, 1), 'Resize plot')
        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1', '2', '5', '6'])

        _set_cell(win, 1, 'Row span', '')
        win.draw_clicked()

        self.assertEqual(_table(win), [(VARS[0], '1', '', ''), (VARS[1], '2', '', ''), (VARS[2], '3', '', ''),
                                       (VARS[3], '4', '', '')])
        self.assertEqual(layout.grid_size(win.canvas), (4, 1))

    def test_a_lower_row_span_in_the_table_moves_the_plots_below_up_by_the_rows_it_frees(self):
        win = self._window(['1', '2', '6'], spans={'Row span': ['', '4', ''], 'Col span': ['', '', '']})

        _set_cell(win, 1, 'Row span', '2')

        self.assertEqual(_table(win), [(VARS[0], '1', '', ''), (VARS[1], '2', '2', ''), (VARS[2], '4', '', '')])

    def test_a_higher_row_span_in_the_table_moves_the_plots_below_down_rather_than_under_it(self):
        win = self._window(['1', '2', '3'])

        _set_cell(win, 0, 'Row span', '2')
        win.draw_clicked()

        self.assertEqual(_table(win), [(VARS[0], '1', '2', ''), (VARS[1], '3', '', ''), (VARS[2], '4', '', '')])
        self.assertEqual(_overlapping(win.canvas), [])

    def test_the_span_written_in_one_row_of_a_plot_is_that_of_all_its_rows(self):
        win = self._window(['1', '1.1.2', '4'], spans={'Row span': ['3', '3', ''], 'Col span': ['', '', '']})

        _set_cell(win, 0, 'Row span', '')

        self.assertEqual(_table(win), [(VARS[0], '1', '', ''), (VARS[1], '1.1.2', '', ''), (VARS[2], '2', '', '')])

    def test_a_wider_col_span_in_the_table_takes_the_empty_cells_beside_its_plot(self):
        win = self._window(['1.1', '2.1', '1.2'])

        _set_cell(win, 1, 'Col span', '2')
        win.draw_clicked()

        self.assertEqual(_table(win), [(VARS[0], '1.1', '', ''), (VARS[1], '2.1', '', '2'), (VARS[2], '1.2', '', '')])
        self.assertEqual(_overlapping(win.canvas), [])

    def test_a_span_the_table_refuses_moves_no_other_row(self):
        win = self._window(['1', '2', '3'])

        for value in (str(MAX_SPAN + 1), 'two', ''):
            _set_cell(win, 0, 'Row span', value)

            self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1', '2', '3'])

    def test_the_canvas_makes_no_plot_bigger_than_the_table_accepts(self):
        win = self._window(['1', '2'])

        self.assertEqual(win.canvasStack.currentWidget().max_span(), MAX_SPAN)

    def test_plots_that_trade_places_trade_their_spans(self):
        win = self._window(['1.1', '1.2', '2.2'], spans={'Row span': ['2', '', ''], 'Col span': ['', '', '']})

        self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[0]), 0, 1))

        self.assertEqual(_table(win), [(VARS[0], '1.2', '', ''), (VARS[1], '1.1', '2', ''), (VARS[2], '2.2', '', '')])

    def test_undo_takes_the_rows_back(self):
        win = self._window(['1', '2', '3'])
        before = _table(win)
        self._arrange(win, layout.resized(win.canvas, _plot_with(win, VARS[0]), 2, 1), 'Resize plot')

        win.undo()
        self.app.processEvents()

        self.assertEqual(_table(win), before)

    def test_a_draw_draws_the_plots_where_they_went_with_the_preferences_each_had(self):
        win = self._window(['1', '2', '3'])
        _plot_with(win, VARS[2]).plot_title = 'third'
        self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[2]), 0, 0))

        win.draw_clicked()

        self.assertEqual([plot.plot_title for plot in win.canvas.plots[0]], ['third', None, None])
        self.assertIs(win.canvas.plots[0][0], _plot_with(win, VARS[2]))

    def test_the_rows_of_a_cell_drawn_empty_move_with_it(self):
        win = self._window(['1', '2', '3'], variables=[VARS[0], UNREAD, VARS[2]])
        self.assertIsNone(win.canvas.plots[0][1])

        self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[2]), 1, 0, reserved=win.reserved_slots()))

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1', '3', '2'])

    def test_a_plot_dropped_on_the_place_of_rows_that_drew_nothing_trades_places_with_them(self):
        win = self._window(['1.1', '2.1', '1.2', '2.2'], variables=VARS[:3] + [UNREAD])

        self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[0]), 1, 1, reserved=win.reserved_slots()))

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['2.2', '2.1', '1.2', '1.1'])
        _set_variable(win, 3, VARS[3])
        win.draw_clicked()
        self.assertEqual(_overlapping(win.canvas), [])
        self.assertIs(win.canvas.plots[0][0], _plot_with(win, VARS[3]))

    def test_a_plot_does_not_grow_over_the_place_of_rows_that_drew_nothing(self):
        for impl in ('matplotlib', 'pyqt'):
            with self.subTest(impl):
                win = self._window(['1.1', '2.1', '1.2', '2.2'], impl=impl, variables=VARS[:3] + [UNREAD])
                win.resize(1200, 900)
                win.show()
                self.app.processEvents()
                qt_canvas = win.canvasStack.currentWidget()
                qt_canvas.set_mouse_mode(Canvas.MOUSE_MODE_SELECT)
                self.app.processEvents()
                widget = qt_canvas._arranger._widget
                rows, cols = qt_canvas._grid_bounds()

                def at(x, y):
                    return widget.mapFrom(qt_canvas, QPoint(round(x), round(y)))
                # From the resize handle of the plot of VAR2 to the empty cell on its right.
                start = at(cols[1] - HANDLE.px() / 2, rows[2] - HANDLE.px() / 2)
                end = at(cols[1] + (cols[2] - cols[1]) * 0.6, rows[1] + (rows[2] - rows[1]) * 0.6)
                QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
                for step in range(1, 9):
                    QTest.mouseMove(widget, start + (end - start) * (step / 8))
                    self.app.processEvents()
                QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
                self.app.processEvents()

                self.assertEqual(_table(win), [(VARS[0], '1.1', '', ''), (VARS[1], '2.1', '', ''),
                                               (VARS[2], '1.2', '', ''), (UNREAD, '2.2', '', '')])
                _set_variable(win, 3, VARS[3])
                win.draw_clicked()
                self.assertEqual(_overlapping(win.canvas), [])

    def test_rows_not_drawn_yet_keep_their_place(self):
        win = self._window(['1', '2'])
        win.sigCfgWidget.model.append_dataframe(pd.DataFrame({'DS': ['csv'], 'Variable': [VARS[2]], 'Stack': ['3'],
                                                              'Plot type': ['PlotXY']}))

        self._arrange(win, layout.resized(win.canvas, _plot_with(win, VARS[1]), 2, 1, reserved=win.reserved_slots()),
                      'Resize plot')

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1', '2', '4'])
        win.draw_clicked()
        self.assertEqual(_overlapping(win.canvas), [])

    def test_moving_a_plot_reads_no_data(self):
        win = self._window(['1', '2', '3'])
        drawn = {name: np.asarray(signal.y_data).copy()
                 for name, signal in ((s.name, s) for s in win.canvasStack.currentWidget().get_signals(win.canvas))}

        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read again")):
            self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[2]), 0, 0))

        for signal in win.canvasStack.currentWidget().get_signals(win.canvas):
            np.testing.assert_array_equal(np.asarray(signal.y_data), drawn[signal.name])


class StackPlaceTest(unittest.TestCase):

    def test_the_place_of_a_stack_is_that_of_the_plot_a_draw_puts_it_in(self):
        self.assertEqual([_stack_place(stack) for stack in ('2', '2.3', ' 2.3.4 ', 2)], [(2, 1), (2, 3), (2, 3), (2, 1)])

    def test_a_stack_a_draw_leaves_out_has_no_place(self):
        self.assertEqual([_stack_place(stack) for stack in ('', 'x', '0', '1.0', '1.1.0', '1.2.3.4')], [None] * 6)


if __name__ == '__main__':
    unittest.main()
