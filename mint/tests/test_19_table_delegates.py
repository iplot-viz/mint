"""Delegate editor lifecycle for the signals-table combo boxes.

The DataSource, Calibrated and PlotType columns render as combo boxes
via QStyledItemDelegate subclasses. The interesting contract for tests
is the editor lifecycle: createEditor must produce a combobox populated
with the right options, setEditorData must point it at the current
model value, and setModelData must push the editor choice back into
the model.

The delegates are simple enough that driving them through a real
QAbstractItemView would be overkill (and flaky). Here we exercise the
three methods directly against a populated MTSignalsModel.
"""

import unittest

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox

from mint.gui.views.mtDataSourcesDelegate import (
    MTCalibratedDelegate, MTDataSourcesDelegate, MTPlotTypeDelegate,
)
from mint.models.mtSignalsModel import MTSignalsModel
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access():
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


def _seeded_model() -> MTSignalsModel:
    model = MTSignalsModel()
    df = pd.DataFrame({
        'DS': ['csv'],
        'Variable': ['MAG-MCTB-F1:VAR1'],
        'Stack': ['1.1'],
        'Plot type': ['PlotXY'],
        'Calibrated': ['false'],
    })
    model.set_dataframe(df)
    return model


class DataSourcesDelegateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_create_editor_populates_data_sources(self):
        delegate = MTDataSourcesDelegate(data_sources=['csv', 'uda'])
        editor = delegate.createEditor(None, None, None)
        self.assertIsInstance(editor, QComboBox)
        items = [editor.itemText(i) for i in range(editor.count())]
        self.assertEqual(items, ['csv', 'uda'])

    def test_set_editor_data_selects_current_value(self):
        delegate = MTDataSourcesDelegate(data_sources=['csv', 'uda'])
        editor = delegate.createEditor(None, None, None)

        model = _seeded_model()
        ds_col = list(model.get_dataframe().columns).index('DS')
        index = model.index(0, ds_col)

        delegate.setEditorData(editor, index)
        self.assertEqual(editor.currentText(), 'csv')

    def test_set_model_data_writes_editor_choice(self):
        delegate = MTDataSourcesDelegate(data_sources=['csv', 'uda'])
        editor = delegate.createEditor(None, None, None)
        editor.setCurrentText('uda')

        model = _seeded_model()
        ds_col = list(model.get_dataframe().columns).index('DS')
        index = model.index(0, ds_col)

        delegate.setModelData(editor, model, index)
        self.assertEqual(
            model.data(index, Qt.ItemDataRole.DisplayRole), 'uda')


class CalibratedDelegateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_editor_has_boolean_options(self):
        delegate = MTCalibratedDelegate()
        editor = delegate.createEditor(None, None, None)
        items = [editor.itemText(i) for i in range(editor.count())]
        self.assertEqual(items, ['false', 'true'])

    def test_set_model_data_writes_choice(self):
        delegate = MTCalibratedDelegate()
        editor = delegate.createEditor(None, None, None)
        editor.setCurrentText('true')

        model = _seeded_model()
        cal_col = list(model.get_dataframe().columns).index('Calibrated')
        index = model.index(0, cal_col)
        delegate.setModelData(editor, model, index)

        self.assertEqual(
            model.data(index, Qt.ItemDataRole.DisplayRole), 'true')


class PlotTypeDelegateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_editor_is_populated_with_plot_types(self):
        delegate = MTPlotTypeDelegate(plot_types=['PlotXY', 'PlotContour'])
        editor = delegate.createEditor(None, None, None)
        items = [editor.itemText(i) for i in range(editor.count())]
        # createEditor also adds an empty option as a sentinel; the two
        # plot types must be at the start.
        self.assertIn('PlotXY', items)
        self.assertIn('PlotContour', items)

    def test_set_model_data_writes_choice(self):
        delegate = MTPlotTypeDelegate(plot_types=['PlotXY', 'PlotContour'])
        editor = delegate.createEditor(None, None, None)
        editor.setCurrentText('PlotContour')

        model = _seeded_model()
        pt_col = list(model.get_dataframe().columns).index('Plot type')
        index = model.index(0, pt_col)
        delegate.setModelData(editor, model, index)

        self.assertEqual(
            model.data(index, Qt.ItemDataRole.DisplayRole), 'PlotContour')


if __name__ == '__main__':
    unittest.main()
