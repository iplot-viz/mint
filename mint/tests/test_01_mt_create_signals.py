# Description: Small code snippets to test the code that creates signals from the table.
# Author: Jaswant Sai Panchumarti
from iplotDataAccess.dataSource import DataSource
from mint.gui.mtSignalConfigurator import MTSignalConfigurator
from mint.tests.QAppOffscreenTestAdapter import QAppOffscreenTestAdapter
from iplotDataAccess.appDataAccess import AppDataAccess
from unittest.mock import patch

test_table_1 = {
    "table": [
        ["codacuda", "Signal:A", "1.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:B", "1.2", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:C", "2.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:D", "2.2", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:E", "3.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:F", "3.2", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""]]
}

test_table_2 = {
    "table": [
        ["codacuda", "Signal:A", "1.1.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:B", "1.1.2", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:C", "2.1.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:D", "2.1.2", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:E", "3.1.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:F", "3.1.2", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:G", "4.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""],
        ["codacuda", "Signal:H", "4.1", "", "", "", "", "", "", "", "", "", "", "", "PlotXY", "", ""]]
}


class TestMTCreateSignalsFromTable(QAppOffscreenTestAdapter):

    def setUp(self) -> None:
        super().setUp()

    @patch.object(DataSource, "connected", new=True, create=True)
    @patch("iplotDataAccess.dataAccess.DataSource.get_cbs_dict")
    @patch("iplotDataAccess.dataAccess.DataSource.get_var_fields")
    @patch("iplotDataAccess.dataAccess.DataSource.get_pulses_df")
    @patch("iplotDataAccess.dataAccess.DataSource.connect")
    @patch.object(DataSource, 'get_var_dict')
    def test_create_simple(self, mock_get_var_dict, pulse_list, var_fields, cbs_dict,
                           source_connected) -> None:
        source_connected.return_value = True
        var_fields.return_value = {}
        pulse_list.return_value = []
        cbs_dict.return_value = {}

        if not AppDataAccess.initialize():
            return
        self.sigCfgWidget = MTSignalConfigurator()
        self.sigCfgWidget.import_dict(test_table_1)
        mock_get_var_dict.return_value = {"correct_values": ""}
        path = list(self.sigCfgWidget.build())

        self.assertEqual(len(path), 6)

        self.assertEqual(path[0].col_num, 1)
        self.assertEqual(path[1].col_num, 2)
        self.assertEqual(path[2].col_num, 1)
        self.assertEqual(path[3].col_num, 2)
        self.assertEqual(path[4].col_num, 1)
        self.assertEqual(path[5].col_num, 2)

        self.assertEqual(path[0].row_num, 1)
        self.assertEqual(path[1].row_num, 1)
        self.assertEqual(path[2].row_num, 2)
        self.assertEqual(path[3].row_num, 2)
        self.assertEqual(path[4].row_num, 3)
        self.assertEqual(path[5].row_num, 3)

        self.assertEqual(path[0].col_span, 1)
        self.assertEqual(path[1].col_span, 1)
        self.assertEqual(path[2].col_span, 1)
        self.assertEqual(path[3].col_span, 1)
        self.assertEqual(path[4].col_span, 1)
        self.assertEqual(path[5].col_span, 1)

        self.assertEqual(path[0].row_span, 1)
        self.assertEqual(path[1].row_span, 1)
        self.assertEqual(path[2].row_span, 1)
        self.assertEqual(path[3].row_span, 1)
        self.assertEqual(path[4].row_span, 1)
        self.assertEqual(path[5].row_span, 1)

        self.assertEqual(path[0].stack_num, 1)
        self.assertEqual(path[1].stack_num, 1)
        self.assertEqual(path[2].stack_num, 1)
        self.assertEqual(path[3].stack_num, 1)
        self.assertEqual(path[4].stack_num, 1)
        self.assertEqual(path[5].stack_num, 1)

        # Test re-build with different canvas layout.
        self.sigCfgWidget.import_dict(test_table_2)
        path = list(self.sigCfgWidget.build())

        self.assertEqual(len(path), 8)

        self.assertEqual(path[0].col_num, 1)
        self.assertEqual(path[1].col_num, 1)
        self.assertEqual(path[2].col_num, 1)
        self.assertEqual(path[3].col_num, 1)
        self.assertEqual(path[4].col_num, 1)
        self.assertEqual(path[5].col_num, 1)
        self.assertEqual(path[6].col_num, 1)
        self.assertEqual(path[7].col_num, 1)

        self.assertEqual(path[0].row_num, 1)
        self.assertEqual(path[1].row_num, 1)
        self.assertEqual(path[2].row_num, 2)
        self.assertEqual(path[3].row_num, 2)
        self.assertEqual(path[4].row_num, 3)
        self.assertEqual(path[5].row_num, 3)
        self.assertEqual(path[6].row_num, 4)
        self.assertEqual(path[7].row_num, 4)

        self.assertEqual(path[0].col_span, 1)
        self.assertEqual(path[1].col_span, 1)
        self.assertEqual(path[2].col_span, 1)
        self.assertEqual(path[3].col_span, 1)
        self.assertEqual(path[4].col_span, 1)
        self.assertEqual(path[5].col_span, 1)
        self.assertEqual(path[6].col_span, 1)
        self.assertEqual(path[7].col_span, 1)

        self.assertEqual(path[0].row_span, 1)
        self.assertEqual(path[1].row_span, 1)
        self.assertEqual(path[2].row_span, 1)
        self.assertEqual(path[3].row_span, 1)
        self.assertEqual(path[4].row_span, 1)
        self.assertEqual(path[5].row_span, 1)
        self.assertEqual(path[6].row_span, 1)
        self.assertEqual(path[7].row_span, 1)

        self.assertEqual(path[0].stack_num, 1)
        self.assertEqual(path[1].stack_num, 2)
        self.assertEqual(path[2].stack_num, 1)
        self.assertEqual(path[3].stack_num, 2)
        self.assertEqual(path[4].stack_num, 1)
        self.assertEqual(path[5].stack_num, 2)
        self.assertEqual(path[6].stack_num, 1)
        self.assertEqual(path[7].stack_num, 1)