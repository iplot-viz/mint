from typing import Any, List, Dict, Union
from PySide6 import QtGui
from PySide6.QtCore import QAbstractItemModel, QModelIndex, QObject, Qt, QSize, QPersistentModelIndex


class JsonModel(QAbstractItemModel):
    """ An editable model of Json data """

    def __init__(self, parent: QObject = None, name=''):
        super().__init__(parent)

        self._root_item = TreeItem()
        self.name = name

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled

        if index.internalPointer().has_child():
            return Qt.ItemIsEnabled
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled

    def mimeTypes(self):
        return ['text/xml']

    def clear(self):
        """ Clear data from the model """
        self.load({})

        return None

    def load(self, document: dict):
        """Load model from a nested dictionary returned by json.loads()

        Arguments:
            document (dict): JSON-compatible dictionary
        """

        assert isinstance(
            document, (dict, list, tuple)
        ), f"`document` must be of dict, list or tuple, not {type(document)}"

        self.beginResetModel()

        self._root_item = TreeItem.load(document)

        self.endResetModel()

        return True

    @staticmethod
    def add_children(parent: "TreeItem", document: dict):
        TreeItem.load(document, parent, consulted=True)

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int = ...) -> Any:
        """Override from QAbstractItemModel

        Return data from a json item according index and role

        """
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.DisplayRole:
            if item.is_folder():
                return item.key
            else:
                return f'{item.key} ({item.unit}) {item.data_type}{item.get_dimension_str()}'
        elif role == Qt.EditRole:
            if index.column() == 1:
                return item.key
        elif role == Qt.SizeHintRole:
            "giving size hint"
            return QSize(1000, 20)
        elif role == Qt.DecorationRole:
            if item.value_type == "folder":
                return QtGui.QIcon(QtGui.QPixmap("mint/mint/gui/icons/folder.svg"))
            elif item.value_type == "variable":
                return QtGui.QIcon(QtGui.QPixmap("mint/mint/gui/icons/variable.svg"))

    def index(self, row: int, column: int, parent=QModelIndex()) -> QModelIndex:
        """Override from QAbstractItemModel

        Return index according row, column and parent

        """
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        """Override from QAbstractItemModel

        Return parent index of index

        """

        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent()

        if parent_item == self._root_item:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def children(self, index: QModelIndex) -> List[QModelIndex]:
        if not index.isValid():
            return [QModelIndex()]

        parent_item = index.internalPointer()
        child_item = parent_item.children
        child_list = []
        if not child_item:
            return []
        for item in child_item:
            child_list.append(self.createIndex(item.row(), 0, item))

        return child_list

    def hasChildren(self, parent: Union[QModelIndex, QPersistentModelIndex] = ...) -> bool:
        if parent.column() > 0:
            return False

        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()

        return parent_item.is_folder()

    def rowCount(self, parent=QModelIndex()):
        """Override from QAbstractItemModel

        Return row count from parent index
        """
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()

        return parent_item.child_count()

    def columnCount(self, parent=QModelIndex()):
        """Override from QAbstractItemModel

        Return column number. For the model, it always returns 1 column
        """
        return 1


class TreeItem:
    """A Json item corresponding to a line in QTreeView"""

    def __init__(self, parent: 'TreeItem' = None, key='', consulted=False, unit='', description='',
                 data_type='', dimension='', value_type='folder'):
        self._parent = parent
        self._key = key
        self._path = ''
        self._consulted = consulted
        self._unit = unit
        self._description = description
        self._dimension = dimension
        self._data_type = data_type
        self._value_type = value_type
        self._children = []
        self.SizeHintRole = 100

    def is_folder(self):
        return self.value_type == "folder"

    def append_child(self, item: "TreeItem"):
        """Add item as a child"""
        self._children.append(item)

    def child(self, row: int) -> "TreeItem":
        """Return the child of the current item from the given row"""
        return self._children[row]

    def has_child(self) -> bool:
        """Return if the current item has children or not"""
        return bool(self._children)

    def parent(self) -> "TreeItem":
        """Return the parent of the current item"""
        return self._parent

    def child_count(self) -> int:
        """Return the number of children of the current item"""
        return len(self._children)

    def row(self) -> int:
        """Return the row where the current item occupies in the parent"""
        return self._parent._children.index(self) if self._parent else 0

    @property
    def key(self) -> str:
        """Return the key name"""
        return self._key

    @key.setter
    def key(self, key: str):
        """Set key name of the current item"""
        self._key = key

    @property
    def data_type(self) -> str:
        return self._data_type

    @data_type.setter
    def data_type(self, data_type: str):
        self._data_type = data_type

    @property
    def path(self) -> str:
        """Return the path"""
        return self._path

    @path.setter
    def path(self, path: str):
        """Set path of the current item"""
        self._path = path

    @property
    def children(self) -> list:
        """Return the children"""
        return self._children

    @property
    def unit(self) -> str:
        """Return the unit of the current item"""
        return self._unit

    @unit.setter
    def unit(self, unit: str):
        """Set unit of the current item"""
        self._unit = unit

    # @property
    # def value(self) -> str:
    #     """Return the value name of the current item"""
    #     return self._value
    #
    # @value.setter
    # def value(self, value: str):
    #     """Set value name of the current item"""
    #     self._value = value

    @property
    def value_type(self):
        return self._value_type

    @value_type.setter
    def value_type(self, value_type):
        self._value_type = value_type

    @property
    def consulted(self):
        """Return if the item is consulted."""
        return self._consulted

    @consulted.setter
    def consulted(self, consulted):
        """Set if item is consulted or not"""
        self._consulted = consulted

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, description):
        self._description = description

    @property
    def dimension(self):
        return self._dimension

    @dimension.setter
    def dimension(self, dimension):
        self._dimension = dimension

    def get_dimension_str(self):
        if self.dimension == [1]:
            return ''
        else:
            return '[' + ']['.join(str(v) for v in self.dimension) + ']'

    def get_dimension_str_0(self):
        if self.dimension == [1]:
            return ''
        else:
            return '[' + ']['.join('0' for _ in self.dimension) + ']'

    @classmethod
    def load(cls, value: Union[List, Dict], parent: "TreeItem" = None, path: object = None,
             consulted: object = False) -> "TreeItem":
        if path is None:
            path = []
        if consulted:
            root_item = parent
            root_item._consulted = consulted
        else:
            root_item = TreeItem(parent)

        if not isinstance(value, dict):
            return root_item
        items = sorted(value.items())

        for key, val in items:
            path.append(key)
            child = cls.load(val, root_item, path)
            if val == '':
                child.key = key[:-2]
                child.value_type = "variable"
            else:
                child.key = key
                child.value_type = "folder"
            child.path = '-'.join(path).replace('?V', '')
            root_item.append_child(child)
            path.pop()

        return root_item
