from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget, QStyle, QLineEdit, QPushButton, QComboBox, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Qt
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.gui.mtVarTree import MTVarTree
from mint.gui.mtVarTable import MTVarTable
from mint.tools.converters import parse_groups_to_dict


class MTVarSelector(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.resize(1000, 800)
        self.width = 840
        self.height = 680
        self.setAcceptDrops(True)
        self.setGeometry(
            QStyle.alignedRect(
                Qt.LeftToRight,
                Qt.AlignCenter,
                self.size(),
                QGuiApplication.primaryScreen().availableGeometry(),
            ),
        )
        self.tree = MTVarTree()
        self.tableView = MTVarTable()
        self.searchbar = QLineEdit()
        self.searchbar.textChanged.connect(self.update_display)

        self.path_input = QLineEdit()
        self.add_to_list_btn = QPushButton("Add to list")
        self.add_to_list_btn.clicked.connect(self.add_to_table)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.tableView.clear_table)
        self.finish_btn = QPushButton("Add to table")

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.update_display)
        self.type_search = QComboBox()
        self.type_search.addItems(['contains', 'startsWith', 'endsWith'])
        # self.type_search.currentTextChanged.connect(self.update_display)

        self.data_sources = AccessHelper.da.get_connected_data_sources()
        self.sources_combo = QComboBox()
        self.sources_combo.addItems(self.data_sources)
        self.sources_combo.currentTextChanged.connect(self.change_model)

        top_h_layout = QHBoxLayout()
        top_h_layout.addWidget(self.sources_combo)
        top_h_layout.addWidget(self.searchbar)
        top_h_layout.addWidget(self.type_search)
        top_h_layout.addWidget(self.search_btn)

        bot_v_layout = QVBoxLayout()
        bot_h_layout = QHBoxLayout()
        bot_h_layout.addWidget(self.add_to_list_btn)
        bot_h_layout.addWidget(self.clear_btn)
        bot_v_layout.addLayout(bot_h_layout)
        bot_v_layout.addWidget(self.finish_btn)

        mid_h_layout = QHBoxLayout()
        mid_h_layout.addWidget(self.tree)
        mid_h_layout.addWidget(self.tableView)
        main_v_layout = QVBoxLayout()
        main_v_layout.addLayout(top_h_layout)
        main_v_layout.addLayout(mid_h_layout)
        main_v_layout.addLayout(bot_v_layout)
        self.setLayout(main_v_layout)

    def get_current_source(self):
        return self.sources_combo.currentText()

    def change_model(self):
        new_source = self.get_current_source()
        self.tree.load_model(new_source)

    def update_display(self):
        text = self.searchbar.text()
        if len(text) < 3:
            self.tree.set_model(self.get_current_source())
        else:
            self.tree.set_model("SEARCH")

            type_search = self.type_search.currentText()

            if type_search == 'startsWith':
                pattern = f".*{text}"
            elif type_search == 'contains':
                pattern = f".*{text}.*"
            elif type_search == 'endsWith':
                pattern = f".*{text}"
            else:
                pattern = ""
            data_source_name = self.get_current_source()
            found = AccessHelper.da.get_var_list(data_source_name=data_source_name, pattern=pattern)

            new_dict = parse_groups_to_dict(found)
            self.tree.models["SEARCH"].load(new_dict)

    def add_to_table(self):
        indexes = self.tree.selectedIndexes()
        data_list = self.tableView.get_variables_list()
        indexes = [ix.internalPointer() for ix in indexes]
        for ix in indexes:
            value = ix.key
            if not ix.has_child() and [self.get_current_source(), value] not in data_list:
                self.tableView.model.add_row([self.get_current_source(), value])
        self.tree.clearSelection()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return:
            self.add_to_table()
        elif event.key() == Qt.Key.Key_Delete:
            self.tableView.remove_from_table()
