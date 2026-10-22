"""Moving and resizing plots on the canvas moves their rows in the table: the Stack of each row follows its plot and
Row span and Col span follow its size. Undo takes the rows back with the plots, a Draw draws the plots where they
went with the preferences each had, and moving a plot reads no data."""

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
from mint.gui.mtMainWindow import MTMainWindow
from mint.models.accessModes.mtGeneric import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp

try:
    from iplotlib.core import layout
except ImportError:
    layout = None

PULSE_ID = 'ITER:MCTB-TEST/111'
VARS = ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2', 'MAG-MCTB-F1:VAR3', 'MAG-MCTB-F1:VAR4', 'MAG-MCTB-F1:VAR5']


def _table(win) -> list:
    df = win.sigCfgWidget.model.get_dataframe()
    return [(variable, stack, row_span, col_span) for variable, stack, row_span, col_span
            in zip(df['Variable'], df['Stack'], df['Row span'], df['Col span']) if variable]


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

    def _window(self, stacks: list, impl: str = 'matplotlib', spans: dict = None) -> MTMainWindow:
        """A window that drew one row of the table for each Stack given, VAR1 for the first one and so on."""
        win = MTMainWindow(Canvas(), AccessHelper.da, {"range": {}}, app_version='test',
                           data_sources=AccessHelper.da.get_connected_data_source_names(),
                           blueprint=mtBlueprintParser.DEFAULT_BLUEPRINT, impl=impl)
        self.addCleanup(win.close)
        win.dataRangeSelector.import_dict({'mode': MTGenericAccessMode.PULSE_NUMBER, 'pulse_nb': [PULSE_ID],
                                           'base': 'Second(s)', 't_start': '-5', 't_end': '4'})
        rows = {'DS': ['csv'] * len(stacks), 'Variable': VARS[:len(stacks)], 'Stack': stacks,
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
        win = self._window(['1', '2', '3'])
        df = win.sigCfgWidget.model.get_dataframe()
        win.sigCfgWidget.model.setData(win.sigCfgWidget.model.createIndex(1, df.columns.get_loc('Variable')),
                                       'MAG-MCTB-F1:NONE', Qt.ItemDataRole.EditRole)
        win.draw_clicked()
        self.assertIsNone(win.canvas.plots[0][1])

        self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[2]), 1, 0))

        self.assertEqual([stack for _, stack, _, _ in _table(win)], ['1', '3', '2'])

    def test_moving_a_plot_reads_no_data(self):
        win = self._window(['1', '2', '3'])
        drawn = {name: np.asarray(signal.y_data).copy()
                 for name, signal in ((s.name, s) for s in win.canvasStack.currentWidget().get_signals(win.canvas))}

        with patch.object(AccessHelper, '_request_data', side_effect=AssertionError("read again")):
            self._arrange(win, layout.moved(win.canvas, _plot_with(win, VARS[2]), 0, 0))

        for signal in win.canvasStack.currentWidget().get_signals(win.canvas):
            np.testing.assert_array_equal(np.asarray(signal.y_data), drawn[signal.name])


if __name__ == '__main__':
    unittest.main()
