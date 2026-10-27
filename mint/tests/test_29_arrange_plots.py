"""Moving and resizing plots on the canvas moves their rows in the table: the Stack of each row follows its plot and
Row span and Col span follow its size. Undo takes the rows back with the plots, a Draw draws the plots where they
went with the preferences each had, and moving a plot reads no data. The place of rows that drew no plot is kept for
them: it moves as a plot does, and no plot moves or grows over it.

Laying the plots out on a grid moves the rows the same way, the rows of the plots joined in the last cell taking its
stacks, and the grid keeps its empty cells through a Draw and in the workspace. Variables dragged from the variable
search and dropped on the canvas go to the table in the plot, the stack or the empty cell they were dropped on."""

import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from iplotDataAccess.appDataAccess import AppDataAccess
from iplotlib.core.canvas import Canvas
from iplotlib.core.drop_info import DropInfo
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


@contextmanager
def _dragging(win, variables: list):
    """The variable search with these variables of the CSV data source selected, as a drag from it takes them."""
    browser = win.sigCfgWidget.selectVarDialog
    items = [SimpleNamespace(has_child=lambda: False, get_table_variable_str=lambda name=name: name)
             for name in variables]
    indexes = [SimpleNamespace(internalPointer=lambda item=item: item) for item in items]
    with patch.object(browser.tree, 'selectedIndexes', return_value=indexes), \
            patch.object(browser, 'get_current_source', return_value=SimpleNamespace(name='csv')):
        yield


def _drop(widget, point):
    """A drag from elsewhere that comes over the widget and drops at the point, in its coordinates."""
    mime = QMimeData()
    mime.setText('variable')
    args = (Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    for event in (QDragEnterEvent(point, *args), QDragMoveEvent(point, *args), QDropEvent(QPointF(point), *args)):
        QApplication.sendEvent(widget, event)


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

    def test_a_row_that_comes_with_a_span_or_an_edit_that_leaves_it_as_it_was_moves_no_plot(self):
        win = self._window(['1', '1', '3'], spans={'Row span': ['2', '', ''], 'Col span': ['', '', '']})
        uid = win.sigCfgWidget.model.get_dataframe()['uid'].iloc[1]
        signal, _ = win._find_signal_in_canvas(uid)

        # The Distance tool duplicates the signal of VAR2 into a new row, which takes the empty span of its row.
        win._on_signal_shift_requested(uid, signal.name, 'csv', getattr(signal, 'pulse_nb', None), 1.0, 0.5, True)
        self.app.processEvents()
        _set_cell(win, 1, 'Row span', '')

        rows = {variable: (stack, row_span) for variable, stack, row_span, _ in _table(win)}
        self.assertEqual((rows[VARS[0]], rows[VARS[2]]), (('1', '2'), ('3', '')))
        win.draw_clicked()
        self.assertEqual(layout.grid_size(win.canvas), (3, 1))

    def test_a_draw_remembers_the_places_of_the_table_once_and_not_for_each_row(self):
        win = self._window([str(row) for row in range(1, 31)], variables=[VARS[row % 3] for row in range(30)])

        with patch.object(MTMainWindow, '_remember_places', autospec=True,
                          side_effect=MTMainWindow._remember_places) as remember:
            win.draw_clicked()

        # A few times, whatever the size of the table: not once for each of its 30 rows.
        self.assertLess(remember.call_count, 10)

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

    def test_a_plot_resized_by_its_left_corner_takes_the_empty_cell_on_its_left_with_its_rows(self):
        for impl in ('matplotlib', 'pyqt'):
            with self.subTest(impl):
                win = self._window(['1.2', '2.1', '2.2'], impl=impl)
                before = _table(win)
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
                # From the bottom left resize handle of the plot of VAR1 to the empty cell on its left.
                start = at(cols[1] + HANDLE.px() / 2, rows[1] - HANDLE.px() / 2)
                end = at(cols[0] + (cols[1] - cols[0]) * 0.3, rows[1] - HANDLE.px() / 2)
                QTest.mouseMove(widget, start)
                QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
                for step in range(1, 9):
                    QTest.mouseMove(widget, start + (end - start) * (step / 8))
                    self.app.processEvents()
                QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
                self.app.processEvents()

                self.assertEqual(_table(win), [(VARS[0], '1.1', '', '2'), (VARS[1], '2.1', '', ''),
                                               (VARS[2], '2.2', '', '')])
                win.undo()
                self.app.processEvents()
                self.assertEqual(_table(win), before)

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

    def test_a_layout_gives_each_row_the_place_its_plot_takes_on_the_grid_picked(self):
        win = self._window(['1', '2', '3', '4'])

        win.canvasStack.currentWidget().lay_out(2, 2)
        self.app.processEvents()

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1', '2', '1.2', '2.2'])

    def test_the_rows_of_the_plots_that_do_not_fit_take_stacks_of_the_last_cell_and_undo_takes_them_back(self):
        win = self._window(['1.1', '2.1', '2.1.2', '3.1'])
        before = _table(win)

        win.canvasStack.currentWidget().lay_out(1, 2)
        self.app.processEvents()

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1.1', '1.2', '1.2.2', '1.2.3'])
        win.undo()
        self.app.processEvents()
        self.assertEqual(_table(win), before)
        win.redo()
        self.app.processEvents()
        win.draw_clicked()
        self.assertEqual(_overlapping(win.canvas), [])
        self.assertEqual(sorted(_plot_with(win, VARS[3]).signals), [1, 2, 3])
        self.assertIs(_plot_with(win, VARS[1]), _plot_with(win, VARS[3]))

    def test_rows_that_drew_nothing_keep_their_stack_when_their_plot_is_joined_and_after_undo(self):
        win = self._window(['1.1', '2.1', '2.1.2', '3.1'], variables=[VARS[0], VARS[1], UNREAD, VARS[2]])
        before = _table(win)

        win.canvasStack.currentWidget().lay_out(1, 2)
        self.app.processEvents()

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1.1', '1.2', '1.2.2', '1.2.3'])
        win.undo()
        self.app.processEvents()
        self.assertEqual(_table(win), before)

    def test_undo_and_redo_give_each_row_the_very_text_it_had(self):
        win = self._window(['1', '3', '3.1.2', '4'],
                           spans={'Row span': ['2', '', '', ''], 'Col span': ['1', '', '', '']})
        before = _table(win)

        win.canvasStack.currentWidget().lay_out(1, 2)
        self.app.processEvents()
        laid_out = _table(win)
        win.undo()
        self.app.processEvents()

        self.assertEqual(_table(win), before)
        self.assertEqual(laid_out, [(VARS[0], '1', '', '1'), (VARS[1], '1.2', '', ''), (VARS[2], '1.2.2', '', ''),
                                    (VARS[3], '1.2.3', '', '')])
        win.redo()
        self.app.processEvents()
        self.assertEqual(_table(win), laid_out)

    def test_a_draw_keeps_the_empty_cells_of_the_grid_picked_and_a_workspace_saves_them(self):
        win = self._window(['1', '2'])
        win.canvasStack.currentWidget().lay_out(2, 2)
        self.app.processEvents()

        win.draw_clicked()
        self.assertEqual((win.canvas.rows, win.canvas.cols), (2, 2))

        win.import_dict(json.loads(json.dumps(win.export_dict())))
        win.draw_clicked()
        self.assertEqual((win.canvas.rows, win.canvas.cols, win.canvas.layout_rows, win.canvas.layout_cols),
                         (2, 2, 2, 2))

    def test_the_canvas_takes_what_is_dragged_from_the_variable_search_only(self):
        win = self._window(['1'])

        self.assertTrue(win.accepts_drop(win.sigCfgWidget.selectVarDialog.tree, None))
        self.assertFalse(win.accepts_drop(None, None))
        self.assertFalse(win.accepts_drop(win.sigCfgWidget, None))

    def test_variables_dropped_from_the_variable_search_are_drawn_where_they_were_dropped(self):
        for impl in ('matplotlib', 'pyqt'):
            with self.subTest(impl):
                win = self._window(['1'], impl=impl)
                win.resize(1200, 900)
                win.show()
                self.app.processEvents()
                qt_canvas = win.canvasStack.currentWidget()
                qt_canvas.lay_out(2, 2)
                self.app.processEvents()
                widget = qt_canvas._arranger._widget
                rows, cols = qt_canvas._grid_bounds()
                # What a drag from the variable search takes: its source cannot be given to a drag made up here.
                qt_canvas.accepts_drop = lambda source, mime: True

                with _dragging(win, [VARS[1], VARS[2]]):
                    _drop(widget, widget.mapFrom(qt_canvas, QPoint(round((cols[1] + cols[2]) / 2),
                                                                   round((rows[1] + rows[2]) / 2))))
                    self.app.processEvents()

                self.assertEqual(_table(win), [(VARS[0], '1', '', ''), (VARS[1], '2.2', '', ''),
                                               (VARS[2], '2.2', '', '')])
                self.assertEqual((_plot_with(win, VARS[1]).row, _plot_with(win, VARS[1]).col), (2, 2))
                self.assertIs(_plot_with(win, VARS[1]), _plot_with(win, VARS[2]))
                self.assertEqual((win.canvas.rows, win.canvas.cols), (2, 2))

    def test_a_variable_dropped_on_a_plot_goes_to_the_stack_dropped_on(self):
        win = self._window(['1', '1.1.2'])

        with _dragging(win, [VARS[2]]):
            win.on_drop_plot(DropInfo(1, 1, 2, win.sigCfgWidget.selectVarDialog.tree))

        self.assertEqual(_table(win)[-1], (VARS[2], '1.1.2', '', ''))
        self.assertIs(_plot_with(win, VARS[2]), _plot_with(win, VARS[0]))

    def test_a_drop_from_an_iplotlib_that_does_not_tell_the_stack_goes_to_the_first_one(self):
        win = self._window(['1'])

        with _dragging(win, [VARS[2]]):
            win.on_drop_plot(SimpleNamespace(row=1, col=2, dragged_item=None))

        self.assertEqual(_table(win)[-1], (VARS[2], '1.2', '', ''))

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
