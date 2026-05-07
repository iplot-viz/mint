"""Find & Replace dialog drives the signals model.

FindReplaceDialog is a small helper with a disproportionately large
blast radius: every user that renames a variable or a pulse number
across many rows does it here. The dialog mutates the MTSignalsModel
via ``setData``, and it's the only path in MINT that exercises that
write route at scale.

These tests drive the dialog programmatically (no widget interaction)
and check the model ends up in the expected state.
"""

import unittest

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableView

from mint.gui.mtFindReplace import FindReplaceDialog
from mint.models.mtSignalsModel import MTSignalsModel
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access():
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class FindReplaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _seeded_view(self):
        model = MTSignalsModel()
        df = pd.DataFrame({
            'DS': ['csv', 'csv'],
            'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2'],
            'Stack': ['1.1', '1.2'],
            'Plot type': ['PlotXY', 'PlotXY'],
            'Alias': ['alpha', 'beta'],
        })
        model.set_dataframe(df)
        view = QTableView()
        view.setModel(model)
        view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        return view, model

    def test_find_text_selects_matching_cell(self):
        view, model = self._seeded_view()
        dlg = FindReplaceDialog(model=view)
        try:
            dlg.find_input.setText('alpha')
            dlg.find_text(find_one=True)

            selected = view.selectionModel().selectedIndexes()
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].data(Qt.ItemDataRole.DisplayRole),
                             'alpha')
        finally:
            dlg.close()
            view.close()

    def test_find_all_selects_every_match(self):
        view, model = self._seeded_view()
        dlg = FindReplaceDialog(model=view)
        try:
            # "MAG-MCTB-F1" appears in both Variable rows.
            dlg.find_input.setText('MAG-MCTB-F1')
            dlg.find_text(find_one=False)
            selected = view.selectionModel().selectedIndexes()
            self.assertEqual(len(selected), 2)
        finally:
            dlg.close()
            view.close()

    def test_replace_updates_model(self):
        view, model = self._seeded_view()
        dlg = FindReplaceDialog(model=view)
        try:
            dlg.find_input.setText('alpha')
            dlg.replace_input.setText('ALPHA')
            dlg.find_text(find_one=True)
            dlg.replace_text()

            df = model.get_dataframe()
            self.assertIn('ALPHA', df['Alias'].tolist())
            self.assertNotIn('alpha', df['Alias'].tolist())
        finally:
            dlg.close()
            view.close()

    def test_replace_with_no_match_leaves_model_unchanged(self):
        view, model = self._seeded_view()
        dlg = FindReplaceDialog(model=view)
        try:
            original_aliases = model.get_dataframe()['Alias'].tolist()
            dlg.find_input.setText('nonexistent')
            dlg.replace_input.setText('whatever')
            dlg.find_text(find_one=False)
            dlg.replace_text()
            self.assertEqual(model.get_dataframe()['Alias'].tolist(),
                             original_aliases)
        finally:
            dlg.close()
            view.close()


if __name__ == '__main__':
    unittest.main()
