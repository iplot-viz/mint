from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QLabel, QDialog, QLineEdit, QHBoxLayout


class FindReplaceDialog(QDialog):
    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        self.setWindowTitle("Find & Replace")

        self.find_label = QLabel("Text to find:")
        self.find_input = QLineEdit()

        self.replace_label = QLabel("Replace with:")
        self.replace_input = QLineEdit()

        self.find_button = QPushButton("Find")
        self.find_button.clicked.connect(lambda: self.find_text(find_one=True))
        self.replace_button = QPushButton("Replace selection")
        self.replace_button.clicked.connect(self.replace_text)
        self.find_all_button = QPushButton("Find All")
        self.find_all_button.clicked.connect(lambda: self.find_text(find_one=False))

        layout = QVBoxLayout()
        layout.addWidget(self.find_label)
        layout.addWidget(self.find_input)
        layout.addWidget(self.replace_label)
        layout.addWidget(self.replace_input)

        button_layout = QVBoxLayout()
        button_layout1 = QHBoxLayout()
        button_layout2 = QHBoxLayout()
        button_layout1.addWidget(self.find_button)
        button_layout1.addWidget(self.find_all_button)
        button_layout2.addWidget(self.replace_button)
        button_layout.addLayout(button_layout1)
        button_layout.addLayout(button_layout2)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.current_index = None

        self.table_view = model

    def set_model(self, model):
        self.table_view = model

    def find_text(self, find_one):
        text_to_find = self.find_input.text()
        self.table_view.selectionModel().clearSelection()
        model = self.table_view.model()
        if self.current_index is None:
            self.current_index = 0
        else:
            self.current_index += 1
        nrows = model.rowCount(None)
        ncols = model.columnCount(None)
        for ix in range(self.current_index, nrows * ncols + self.current_index):
            ix = ix % (nrows * ncols)
            row = ix % nrows
            col = ix // nrows
            index = model.index(row, col)
            item = model.data(index, Qt.ItemDataRole.DisplayRole)
            if item and text_to_find and text_to_find in item:
                self.table_view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select)
                self.current_index = ix
                if find_one:
                    return

    def replace_text(self):
        model = self.table_view.model()
        text_to_find = self.find_input.text()
        text_to_replace = self.replace_input.text()
        all_indexes = self.table_view.selectionModel().selectedIndexes()
        rows = set()
        cols = set()
        for index in all_indexes:
            row = index.row()
            rows.add(row)
            col = index.column()
            cols.add(col)
            new_index = model.index(row, col)
            item_data = model.data(new_index, Qt.ItemDataRole.DisplayRole)
            if item_data and text_to_find in item_data:
                with model.activate_fast_mode():
                    model.setData(new_index, item_data.replace(text_to_find, text_to_replace),
                                  Qt.ItemDataRole.EditRole)

        model.dataChanged.emit(model.index(min(rows), min(cols)), model.index(max(rows), max(cols)))

        self.find_text(find_one=True)
