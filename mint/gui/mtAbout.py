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
from PySide2.QtWidgets import QAbstractItemView, QGridLayout, QLabel, QPushButton, QTableView, QDialog, QVBoxLayout, QWidget

from mint.tools.icon_loader import create_pxmap

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
bug_link = "https://jira.iter.org/secure/CreateIssueDetails!init.jspa?pid=17100&issuetype=1&assignee=panchuj&summary=<Type your bug summary>"
feature_req_link = "https://jira.iter.org/secure/CreateIssueDetails!init.jspa?pid=17100&issuetype=2&assignee=panchuj&summary=<Type your feature request summary>"

class MTAbout(QDialog):
    def __init__(self, parent: typing.Optional[QDialog] = None):
        super().__init__(parent=parent)
        self._model = QStandardItemModel()
        self._layout = QGridLayout()

        self._prepareIcon()
        self._layout.addWidget(self.iconLabel, 0, 0)
        self._prepareDescription()
        self._layout.addWidget(self._descriptionWidget, 0, 1)
        self._prepareEnvironmentWidget()
        self._layout.addWidget(self._environmentWidget, 1, 1)
        self._prepareButtons()
        self._layout.addWidget(self._copyBtn, 2, 1)

        self.setLayout(self._layout)
        self.setWindowTitle("About MINT")
        self.resize(1100, 420)
    
    def _prepareButtons(self):
        self._copyBtn = QPushButton("Copy to clipboard", self)
        self._copyBtn.clicked.connect(
            lambda: QCoreApplication.instance().clipboard().setText(self.getContentsAsString())
        )

    def _prepareEnvironmentWidget(self):
        self._environmentWidget = QTableView(self)
        self._environmentWidget.setModel(self._model)
        self._environmentWidget.verticalHeader().hide()
        self._environmentWidget.setShowGrid(False)
        self._environmentWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._environmentWidget.setAlternatingRowColors(True)

    def _prepareDescription(self):
        self._descriptionWidget = QWidget(self)
        self._descriptionWidget.setLayout(QVBoxLayout())
        heading = QLabel("About MINT")
        heading.setStyleSheet("font-weight: bold; color: black")
        description = QLabel()
        description.setText("A Python Qt application for ITER Data Visualtization using the iplotlib framework.")
        jira = QLabel()
        jira.setOpenExternalLinks(True)
        jira.setText(f"Report a <a href=\"{bug_link}\"> bug</a> or a <a href=\"{feature_req_link}\"> feature</a> request")
        jira.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        authors = QLabel()
        authors.setText("Authors: Jaswant Panchumarti, Lana Abadie, Piotr Mazur")
        self._descriptionWidget.layout().addWidget(heading)
        self._descriptionWidget.layout().addWidget(description)
        self._descriptionWidget.layout().addWidget(jira)
        self._descriptionWidget.layout().addWidget(authors)

    def _prepareIcon(self):
        self.iconLabel = QLabel("")
        self.iconLabel.setPixmap(create_pxmap('mint64x64'))

    def resizeEvent(self, arg__1):
        print(arg__1.size())
        return super().resizeEvent(arg__1)

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
