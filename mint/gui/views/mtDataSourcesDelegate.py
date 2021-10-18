# Description: Delegates editing for data source column
# Author: Jaswant Sai Panchumarti

import typing

from PySide2.QtCore import QAbstractItemModel, QCoreApplication, QLocale, QModelIndex, QObject, QSize, Qt
from PySide2.QtWidgets import QComboBox, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget


class MTDataSourcesDelegate(QStyledItemDelegate):
    def __init__(self, data_sources: list, parent: typing.Optional[QObject] = None):
        super().__init__(parent=parent)
        self._data_sources = data_sources
    
    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        combobox = QComboBox(parent)
        combobox.addItems(self._data_sources)
        combobox.addItem('')
        if combobox.count():
            combobox.setCurrentIndex(0)
        return combobox

    
    def setEditorData(self, editor: QWidget, index: QModelIndex):
        value = index.data(Qt.EditRole)
        loc = editor.findText(value)
        if loc >= 0:
            editor.setCurrentIndex(loc)
        else:
            editor.setCurrentIndex(0)

    
    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex):
        model.setData(index, editor.currentText(), Qt.EditRole)

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex):
        editor.setGeometry(option.rect)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        maxWidth = 0
        for value in self._data_sources:
            itemWidth = option.fontMetrics.width(self.displayText(value, QLocale()))
            maxWidth = max(itemWidth, maxWidth)

        return QCoreApplication.instance().style().sizeFromContents(
            QStyle.CT_ComboBox,
            option,
            QSize(maxWidth * 1.5, option.fontMetrics.height())
        )
