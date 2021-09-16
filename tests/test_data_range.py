import os
import sys

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication
from gui.dataRangeSelector import DataRangeSelector, DataRange

def quit_app():
    global app
    print('\n')
    app.closeAllWindows()
    sys.exit(0)

dirname = os.path.dirname(os.path.abspath(__file__))

mappings = {"mode": DataRange.TIME_RANGE, "value": ['', '']}
app = QApplication([])
selector = DataRangeSelector(mappings)
selector.importJson(open(os.path.join(dirname, "test.json")).read())

selector.show()
selector.setAttribute(Qt.WA_DeleteOnClose, True)
selector.destroyed.connect(quit_app)

while True:
    try:
        app.processEvents()
        print(f"json dump: {selector.exportJson()}")
    except KeyboardInterrupt:
        quit_app()