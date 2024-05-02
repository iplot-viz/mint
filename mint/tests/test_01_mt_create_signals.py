# # Description: Small code snippets to test the code that creates signals from the table.
# # Author: Jaswant Sai Panchumarti
#
# from mint.gui.mtSignalConfigurator import MTSignalConfigurator
# from mint.tests.QAppOffscreenTestAdapter import QAppOffscreenTestAdapter
# from iplotDataAccess.appDataAccess import AppDataAccess
#
# test_table_1 = {
#     "table": [
#         ["ds", "Signal:A", "1.1", "", "", "",
#          "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:B", "1.2", "", "", "",
#          "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:C", "2.1", "", "", "",
#          "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:D", "2.2", "", "", "",
#          "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:E", "3.1", "", "", "",
#          "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:F", "3.2", "", "", "",
#          "", "", "", "", "", "", "", "", "", ""]]
# }
#
# test_table_2 = {
#     "table": [
#         ["ds", "Signal:A", "1.1.1", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:B", "1.1.2", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:C", "2.1.1", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:D", "2.1.2", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:E", "3.1.1", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:F", "3.1.2", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:G", "4.1", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""],
#         ["ds", "Signal:H", "4.1", "", "",
#          "", "", "", "", "", "", "", "", "", "", ""]]
# }
#
#
# class TestMTCreateSignalsFromTable(QAppOffscreenTestAdapter):
#     def setUp(self) -> None:
#         super().setUp()
#         AppDataAccess.initialize()
#         self.sigCfgWidget = MTSignalConfigurator()
#
#     def test_create_simple(self) -> None:
#         self.sigCfgWidget.import_dict(test_table_1)
#         path = list(self.sigCfgWidget.build())
#
#         self.assertEqual(len(path), 6)
#
#         self.assertEqual(path[0].col_num, 1)
#         self.assertEqual(path[1].col_num, 2)
#         self.assertEqual(path[2].col_num, 1)
#         self.assertEqual(path[3].col_num, 2)
#         self.assertEqual(path[4].col_num, 1)
#         self.assertEqual(path[5].col_num, 2)
#
#         self.assertEqual(path[0].row_num, 1)
#         self.assertEqual(path[1].row_num, 1)
#         self.assertEqual(path[2].row_num, 2)
#         self.assertEqual(path[3].row_num, 2)
#         self.assertEqual(path[4].row_num, 3)
#         self.assertEqual(path[5].row_num, 3)
#
#         self.assertEqual(path[0].col_span, 1)
#         self.assertEqual(path[1].col_span, 1)
#         self.assertEqual(path[2].col_span, 1)
#         self.assertEqual(path[3].col_span, 1)
#         self.assertEqual(path[4].col_span, 1)
#         self.assertEqual(path[5].col_span, 1)
#
#         self.assertEqual(path[0].row_span, 1)
#         self.assertEqual(path[1].row_span, 1)
#         self.assertEqual(path[2].row_span, 1)
#         self.assertEqual(path[3].row_span, 1)
#         self.assertEqual(path[4].row_span, 1)
#         self.assertEqual(path[5].row_span, 1)
#
#         self.assertEqual(path[0].stack_num, 1)
#         self.assertEqual(path[1].stack_num, 1)
#         self.assertEqual(path[2].stack_num, 1)
#         self.assertEqual(path[3].stack_num, 1)
#         self.assertEqual(path[4].stack_num, 1)
#         self.assertEqual(path[5].stack_num, 1)
#
#         # Test re-build with different canvas layout.
#         self.sigCfgWidget.import_dict(test_table_2)
#         path = list(self.sigCfgWidget.build())
#
#         self.assertEqual(len(path), 8)
#
#         self.assertEqual(path[0].col_num, 1)
#         self.assertEqual(path[1].col_num, 1)
#         self.assertEqual(path[2].col_num, 1)
#         self.assertEqual(path[3].col_num, 1)
#         self.assertEqual(path[4].col_num, 1)
#         self.assertEqual(path[5].col_num, 1)
#         self.assertEqual(path[6].col_num, 1)
#         self.assertEqual(path[7].col_num, 1)
#
#         self.assertEqual(path[0].row_num, 1)
#         self.assertEqual(path[1].row_num, 1)
#         self.assertEqual(path[2].row_num, 2)
#         self.assertEqual(path[3].row_num, 2)
#         self.assertEqual(path[4].row_num, 3)
#         self.assertEqual(path[5].row_num, 3)
#         self.assertEqual(path[6].row_num, 4)
#         self.assertEqual(path[7].row_num, 4)
#
#         self.assertEqual(path[0].col_span, 1)
#         self.assertEqual(path[1].col_span, 1)
#         self.assertEqual(path[2].col_span, 1)
#         self.assertEqual(path[3].col_span, 1)
#         self.assertEqual(path[4].col_span, 1)
#         self.assertEqual(path[5].col_span, 1)
#         self.assertEqual(path[6].col_span, 1)
#         self.assertEqual(path[7].col_span, 1)
#
#         self.assertEqual(path[0].row_span, 1)
#         self.assertEqual(path[1].row_span, 1)
#         self.assertEqual(path[2].row_span, 1)
#         self.assertEqual(path[3].row_span, 1)
#         self.assertEqual(path[4].row_span, 1)
#         self.assertEqual(path[5].row_span, 1)
#         self.assertEqual(path[6].row_span, 1)
#         self.assertEqual(path[7].row_span, 1)
#
#         self.assertEqual(path[0].stack_num, 1)
#         self.assertEqual(path[1].stack_num, 2)
#         self.assertEqual(path[2].stack_num, 1)
#         self.assertEqual(path[3].stack_num, 2)
#         self.assertEqual(path[4].stack_num, 1)
#         self.assertEqual(path[5].stack_num, 2)
#         self.assertEqual(path[6].stack_num, 1)
#         self.assertEqual(path[7].stack_num, 1)
