from qtpy.QtWidgets import QStatusBar

class MTStatusBar(QStatusBar):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.showMessage("Ready.")
