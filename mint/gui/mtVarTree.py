from PySide6.QtGui import QCursor
from PySide6.QtCore import QFileInfo
from PySide6.QtWidgets import QTreeView, QToolTip, QAbstractItemView
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.models.mtJsonModel import JsonModel
from mint.tools.converters import parse_groups_to_dict, parse_vars_to_dict

DEFAULT_SOURCE = 'codacuda'


class MTVarTree(QTreeView):
    def __init__(self):
        QTreeView.__init__(self)
        self.models = {'SEARCH': JsonModel()}
        self.setSelectionMode(self.selectionMode().ExtendedSelection)
        self.setHeaderHidden(True)
        self.setColumnWidth(0, 205)
        self.setMouseTracking(True)
        self.entered.connect(self.handle_item_entered)
        self.setAlternatingRowColors(True)

        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)

        self.expanded.connect(self.expand)
        self.load_model(DEFAULT_SOURCE)

    def expand(self, index):

        data_source_name = self.parent().get_current_source()
        if index.internalPointer().consulted:
            return
        path = index.internalPointer().path
        pattern = f'{path}:.*'
        data = AccessHelper.da.get_var_list(data_source_name=data_source_name, pattern=pattern)
        if not data:
            return

        data_parsed = parse_vars_to_dict(data, path)

        self.models[data_source_name].layoutAboutToBeChanged.emit()
        self.models[data_source_name].add_children(index.internalPointer(), data_parsed)
        self.models[data_source_name].layoutChanged.emit()

    def load_model(self, data_source_name):
        if data_source_name not in self.models:
            self.models[data_source_name] = JsonModel()
            file_path = QFileInfo(__file__).absoluteDir().filePath(f"{data_source_name}.txt")
            with open(file_path, encoding='utf-8') as file:
                lines = file.read().split('\n')
                document = parse_groups_to_dict(lines)
                self.models[data_source_name].load(document)

        self.setModel(self.models[data_source_name])

    def set_model(self, data_source_name):
        if data_source_name in self.models:
            self.setModel(self.models[data_source_name])

    def clear_model(self):
        self.setModel(None)

    def handle_item_entered(self, index):
        data_source_name = self.parent().get_current_source()
        if not index.isValid():
            return
        ix = index.internalPointer()
        if ix.has_child():
            return
        if ix.unit:
            unit = ix.unit
        else:
            unit = AccessHelper.da.dslist[data_source_name].daHandler.getUnit(ix.key)
            ix.unit = unit

        QToolTip.showText(
            QCursor.pos(),
            f'{ix.key}: {unit}',
            self.viewport(),
            self.visualRect(index)
        )

    def dragMoveEvent(self, event):
        if not self.currentIndex().internalPointer().has_child():
            super(MTVarTree, self).dragMoveEvent(event)
            return

        event.ignore()
