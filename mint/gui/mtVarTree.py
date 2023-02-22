from PySide6.QtGui import QCursor
from PySide6.QtCore import QFileInfo
from PySide6.QtWidgets import QTreeView, QToolTip, QAbstractItemView
from iplotlib.interface.iplotSignalAdapter import AccessHelper
from mint.models.mtJsonModel import JsonModel, TreeItem
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
        # AccessHelper.da.getData(dataSName="codacuda", varname='IC-ICH-PCF1:9401_0', tsS=0, tsE=1676885937000000000,nbp=100)
        self.expanded.connect(self.expand)
        self.load_model(DEFAULT_SOURCE)
        self.dragged_item = None

    def expand(self, index):
        data_source_name = self.parent().get_current_source()
        if index.internalPointer().consulted:
            return
        path = index.internalPointer().path
        pattern = f'{path}:.*'
        data = AccessHelper.da.get_var_list(data_source_name=data_source_name, pattern=pattern)
        if data:
            data_parsed = parse_vars_to_dict(data, path)

            self.models[data_source_name].layoutAboutToBeChanged.emit()
            self.models[data_source_name].add_children(index.internalPointer(), data_parsed)
            self.models[data_source_name].layoutChanged.emit()

        self.check_folder(index.internalPointer(), data_source_name)

    def check_folder(self, index, data_source_name):
        for child in index.children:
            if child.has_child() or child.consulted:
                continue
            data = AccessHelper.da.get_var_fields(data_source_name=data_source_name, variable=child.key)

            if data:
                if set(data.keys()) == {'status_id', 'val', 'secs', 'severity_id', 'nanosecs'}:
                    child.data_type = data['val']['type']
                    child.unit = data['val']['units']
                    child.description = data['val']['description']
                    if data['val']['dimensionality'] != [1]:
                        child.dimension = '[' + ']['.join(str(v) for v in data['val']['dimensionality']) + ']'
                elif list(data.keys()) == ['value']:
                    child.data_type = data['value']['type']
                    child.unit = data['value']['units']
                    child.description = data['value']['description']
                    if data['value']['dimensionality'] != [1]:
                        child.dimension = '[' + ']['.join(str(v) for v in data['value']['dimensionality']) + ']'
                else:
                    child.value_type = 'folder'
                    for key, val in data.items():
                        dimensionality = '' if val['dimensionality'] == [1] else '[' + ']['.join(
                            str(v) for v in val['dimensionality']) + ']'
                        child.append_child(TreeItem(parent=child,
                                                    key=f'{child.key}/{key}',
                                                    consulted=True,
                                                    unit=val['units'],
                                                    description=val['description'],
                                                    dimension=dimensionality,
                                                    data_type=val['type'],
                                                    value_type='variable'
                                                    ))

    def load_model(self, data_source_name):
        if data_source_name not in self.models:
            self.models[data_source_name] = JsonModel()
            # AccessHelper.da.get_cbs_list(data_source_name=data_source_name)
            file_path = QFileInfo(__file__).absoluteDir().filePath(f"{data_source_name}.txt")
            with open(file_path, encoding='utf-8') as file:
                lines = file.read().split('\n')
                document = parse_groups_to_dict(lines)
            self.models[data_source_name].load(document)
            self.check_folder(self.models[data_source_name]._root_item, data_source_name)

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
        QToolTip.showText(
            QCursor.pos(),
            f'{ix.key}\n'
            f'Unit: {ix.unit}\n'
            f'Description: {ix.description}\n'
            f'DataType: {ix.data_type}',
            self.viewport(),
            self.visualRect(index)
        )

    def dragMoveEvent(self, event):
        if not self.currentIndex().internalPointer().has_child():
            self.dragged_item = self.currentIndex().internalPointer()
            super(MTVarTree, self).dragMoveEvent(event)
            return

        event.ignore()
