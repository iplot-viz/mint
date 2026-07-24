"""Insert/remove row operations on MTSignalsModel.

The signals table is the central data structure in MINT: every signal
the user plots starts life as a row here. Inserting a row must create
one with a fresh uid and the blueprint defaults, and removing a row
must drop it without off-by-one errors. The context menu in
MTSignalConfigurator wires directly to these model methods, so the
interesting invariants are at the model level — driving the menu in a
test would just hang on QMenu.exec().

These tests verify that behaviour without touching the UI.
"""

import unittest

import pandas as pd
from iplotDataAccess.appDataAccess import AppDataAccess

from mint.models.mtSignalsModel import MTSignalsModel
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _ensure_data_access() -> None:
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class InsertRowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def test_insert_single_row_into_empty_model(self):
        model = MTSignalsModel()
        # Brand-new model has zero rows.
        self.assertEqual(model.rowCount(), 0)

        model.insertRows(0, 1)
        self.assertEqual(model.rowCount(), 1)

    def test_inserted_row_has_generated_uid(self):
        """Every new row must carry a uid (used by the shift tracker)."""
        model = MTSignalsModel()
        model.insertRows(0, 1)

        df = model._table
        uid = df.at[0, MTSignalsModel.ROWUID_COLNAME]
        self.assertTrue(uid, "inserted row must have a non-empty uid")

    def test_insert_multiple_rows(self):
        model = MTSignalsModel()
        model.insertRows(0, 3)
        self.assertEqual(model.rowCount(), 3)

        # Each inserted row gets its own uid, not a duplicate.
        df = model._table
        uids = set(df[MTSignalsModel.ROWUID_COLNAME])
        self.assertEqual(len(uids), 3)

    def test_insert_fires_rows_inserted_signal(self):
        """The table view relies on rowsInserted to repaint. A regression
        in insertRows that forgets begin/endInsertRows would silently
        break the UI even if the data model is correct."""
        model = MTSignalsModel()
        seen = []
        model.rowsInserted.connect(
            lambda parent, first, last: seen.append((first, last)))
        model.insertRows(0, 1)
        self.assertEqual(len(seen), 1)


class RemoveRowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()

    def _seeded_model(self) -> MTSignalsModel:
        model = MTSignalsModel()
        df = pd.DataFrame({
            'DS': ['csv', 'csv', 'csv'],
            'Variable': ['MAG-MCTB-F1:VAR1', 'MAG-MCTB-F1:VAR2', 'MAG-MCTB-F1:VAR3'],
            'Stack': ['1.1', '1.2', '1.3'],
            'Plot type': ['PlotXY', 'PlotXY', 'PlotXY'],
        })
        model.set_dataframe(df)
        return model

    def test_remove_first_row_leaves_the_rest(self):
        model = self._seeded_model()
        self.assertEqual(model.rowCount(), 3)
        model.removeRows(0, 1)
        self.assertEqual(model.rowCount(), 2)

        df = model.get_dataframe()
        # After removal, the remaining rows must be the ones at rows 1 and 2
        # in the original table — VAR2 and VAR3.
        self.assertEqual(df.iloc[0]['Variable'], 'MAG-MCTB-F1:VAR2')
        self.assertEqual(df.iloc[1]['Variable'], 'MAG-MCTB-F1:VAR3')

    def test_remove_middle_row(self):
        model = self._seeded_model()
        model.removeRows(1, 1)
        df = model.get_dataframe()

        # Dropping the middle row collapses VAR1 and VAR3 into positions 0 and 1.
        self.assertEqual(df.iloc[0]['Variable'], 'MAG-MCTB-F1:VAR1')
        self.assertEqual(df.iloc[1]['Variable'], 'MAG-MCTB-F1:VAR3')

    def test_remove_fires_rows_removed_signal(self):
        model = self._seeded_model()
        seen = []
        model.rowsRemoved.connect(
            lambda parent, first, last: seen.append((first, last)))
        model.removeRows(0, 1)
        self.assertEqual(len(seen), 1)


class CopyToClipboardGuardTest(unittest.TestCase):
    """Copy with no cells selected must be a no-op instead of raising."""

    def test_copy_with_empty_selection_is_a_noop(self):
        from unittest.mock import MagicMock
        from mint.gui.mtSignalConfigurator import MTSignalConfigurator

        fake = MagicMock()
        fake._tabs.currentIndex.return_value = 0
        view = fake._signal_item_widgets.__getitem__.return_value.view.return_value
        view.selectionModel.return_value.selectedIndexes.return_value = []
        MTSignalConfigurator.copy_contents_to_clipboard(fake)  # must not raise


if __name__ == '__main__':
    unittest.main()
