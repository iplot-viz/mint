from PyQt5.QtCore import QAbstractItemModel, QModelIndex, QVariant, Qt
from PyQt5.QtWidgets import QMainWindow, QPushButton, QSplitter, QTreeView, QWidget


class PreferencesWindow(QMainWindow):

    def __init__(self, canvas=None):
        super().__init__()
        self.tree_view = QTreeView()

        right_column = QPushButton("right")

        central_widget = QSplitter()
        central_widget.addWidget(self.tree_view)
        central_widget.addWidget(right_column)

        self.setCentralWidget(central_widget)

    def set_canvas(self, canvas):
        self.tree_view.setModel(CanvasItemModel(canvas))

class CanvasItemModel(QAbstractItemModel):

    def __init__(self, canvas=None):
        super().__init__()
        print("Model init")
        self.canva = canvas

    def columnCount(self, parent):
        return 1

    def rowCount(self, parent):
        return 5

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        print("Create index:",row,column,parent)
        return self.createIndex(row, column, "Zosia")
        # return QModelIndex()

    def data(self, index, role):
        print("DATA",index.row(),index.column(),"role:",role)
        if role == Qt.DisplayRole or role == Qt.EditRole:
            # return self.model[index.row()][index.column()]
            return "Zosia"+str(index.row())
        return QVariant()

class PlotForm(QWidget):
    pass

class SignalForm(QWidget):
    pass

class CanvasForm(QWidget):
    pass