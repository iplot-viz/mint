# Description: A widget that shows a short description of MINT and 
#               all mint components/environment variables along with their versions where applicable.
# Author: Jaswant Sai Panchumarti

from collections import defaultdict
from importlib import metadata
import json
import pkgutil
import typing

from PySide2.QtCore import QCoreApplication, Qt
from PySide2.QtGui import QShowEvent, QStandardItem, QStandardItemModel
from PySide2.QtWidgets import QAbstractItemView, QGridLayout, QLabel, QPushButton, QTableView, QDialog

packages = [
    'cachetools',
    'matplotlib',
    'numpy',
    'iplotDataAccess',
    'iplotlib',
    'iplotLogging',
    'iplotProcessing',
    'mint',
    'pandas',
    'psutil',
    'PySide2',
    'requests',
    'scipy',
    'sseclient-py',
    'vtk'
]
aliases = {'sseclient-py': 'sseclient'}

class MTAbout(QDialog):
    def __init__(self, parent: typing.Optional[QDialog] = None):
        super().__init__(parent=parent)
        self._environmentWidget = QTableView(self)
        self._layout = QGridLayout()
        self._copyBtn = QPushButton("Copy to clipboard", self)
        self._copyBtn.clicked.connect(
            lambda: QCoreApplication.instance().clipboard().setText(self.getContentsAsString())
        )
        heading = QLabel("About MINT")
        heading.setStyleSheet("font-weight: bold; color: black")
        self._layout.addWidget(heading, 0, 0)
        self._layout.addWidget(QLabel("""
        A Python Qt application for ITER Data Visualtization using the iplotlib framework."""), 1, 0)
        self._layout.addWidget(self._environmentWidget, 2, 0)
        self._layout.addWidget(self._copyBtn, 3, 0)

        self._model = QStandardItemModel()
        self._environmentWidget.setModel(self._model)

        self.setLayout(self._layout)
        self.setWindowTitle("About MINT")
        self.resize(500, 400)
        self._environmentWidget.verticalHeader().hide()
        self._environmentWidget.setShowGrid(False)
        self._environmentWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._environmentWidget.setAlternatingRowColors(True)
    
    def showEvent(self, ev: QShowEvent):
        self.catalogEnvironment()
        self._environmentWidget.resizeColumnsToContents()
        self._environmentWidget.resizeRowsToContents()
        return super().showEvent(ev)

    def catalogEnvironment(self):
        self._model.setColumnCount(3)
        self._model.setHeaderData(0, Qt.Horizontal, 'Package', Qt.DisplayRole)
        self._model.setHeaderData(1, Qt.Horizontal, 'Version', Qt.DisplayRole)
        self._model.setHeaderData(2, Qt.Horizontal, 'Path', Qt.DisplayRole)

        for i, pkg in enumerate(packages):
            name_item = QStandardItem(pkg)
            try:
                version_item = QStandardItem(f"{metadata.version(pkg)}")
            except Exception:
                version_item = QStandardItem('---')
            try:
                path_item = QStandardItem(f"{pkgutil.get_loader(pkg).path}")
            except Exception:
                try:
                    import_name = pkg if not pkg in aliases else aliases[pkg]
                    path_item = QStandardItem(f"{metadata.import_module(import_name).__path__}")
                except Exception:
                    path_item = QStandardItem(f"---")
            self._model.setItem(i, 0, name_item)
            self._model.setItem(i, 1, version_item)
            self._model.setItem(i, 2, path_item)
            
    def getContentsAsString(self) -> str:
        root_idx = self._model.invisibleRootItem().index()

        ncols = self._model.columnCount(root_idx)
        output = defaultdict(dict)
        for row, pkg in enumerate(packages):
            for col in range(1, ncols):
                col_name = self._model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
                output[pkg].update({
                    col_name: self._model.data(self._model.index(row, col, root_idx))
                })
        
        return json.dumps(output, indent=4)
