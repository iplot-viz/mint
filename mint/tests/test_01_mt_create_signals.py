# Description: Small code snippets to test the code that creates signals from the table.
# Author: Jaswant Sai Panchumarti

from mint.gui.mtSignalConfigurator import MTSignalConfigurator
from mint.tests.QAppOffscreenTestAdapter import QAppOffscreenTestAdapter


test_table = {
    "table": [
        ["codacuda", "Signal:A", "1.1", "", "", "", "", "", "", "", "", "", "", "", "Success|1920 points"],
        ["codacuda", "Signal:B", "1.2", "", "", "", "", "", "", "", "", "", "", "", "Success|1920 points"],
        ["codacuda", "Signal:C", "2.1", "", "", "", "", "", "", "", "", "", "", "", "Success|1920 points"],
        ["codacuda", "Signal:D", "2.2", "", "", "", "", "", "", "", "", "", "", "", "Success|1920 points"]
    ]
}


class TestMTCreateSignalsFromTable(QAppOffscreenTestAdapter):
    def setUp(self) -> None:
        super().setUp()
        self.sigCfgWidget = MTSignalConfigurator()

    def test_create_simple(self) -> None:
        self.sigCfgWidget.import_dict(test_table)
        path = list(self.sigCfgWidget.build())
        self.assertEqual(len(path), 4)
