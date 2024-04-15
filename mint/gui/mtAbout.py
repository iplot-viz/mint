# Description: A widget that shows a short description of MINT and 
#               all mint components/environment variables along with their versions where applicable.
# Author: Jaswant Sai Panchumarti
import logging
from collections import defaultdict
from importlib import metadata, import_module
import json
import pkgutil
import typing

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QShowEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QGridLayout, QLabel, QPushButton, QTableView, QDialog, QVBoxLayout, \
    QWidget, QMainWindow

from mint.tools.icon_loader import create_pxmap

# TODO Change packages to not be hardcoded
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
    'PySide6',
    'requests',
    'scipy',
    'sseclient-py',
    'vtk'
]
aliases = {'sseclient-py': 'sseclient'}
bug_link = ("https://jira.iter.org/secure/CreateIssueDetails!init.jspa?pid=17100&issuetype=1"
            "&assignee=martinp6&summary=<Type your bug summary>")
feature_req_link = ("https://jira.iter.org/secure/CreateIssueDetails!init.jspa?pid=17100&issuetype=2"
                    "&assignee=martinp6&summary=<Type your feature request summary>")


class MTAbout(QDialog):
    def __init__(self, parent: typing.Optional[QMainWindow] = None):
        super().__init__(parent=parent)
        self._model = QStandardItemModel()
        self._layout = QGridLayout()

        self._prepare_icon()
        self._layout.addWidget(self.iconLabel, 0, 0)
        self._prepare_description()
        self._layout.addWidget(self._descriptionWidget, 0, 1)
        self._prepare_environment_widget()
        self._layout.addWidget(self._environmentWidget, 1, 1)
        self._prepare_buttons()
        self._layout.addWidget(self._copyBtn, 2, 1)

        self.setLayout(self._layout)
        self.setWindowTitle("About MINT")
        self.resize(1100, 420)

    def _prepare_buttons(self):
        self._copyBtn = QPushButton("Copy to clipboard", self)
        self._copyBtn.clicked.connect(
            lambda: QCoreApplication.instance().clipboard().setText(self.get_contents_as_string())
        )

    def _prepare_environment_widget(self):
        self._environmentWidget = QTableView(self)
        self._environmentWidget.setModel(self._model)
        self._environmentWidget.verticalHeader().hide()
        self._environmentWidget.setShowGrid(False)
        self._environmentWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._environmentWidget.setAlternatingRowColors(True)

    def _prepare_description(self):
        self._descriptionWidget = QWidget(self)
        self._descriptionWidget.setLayout(QVBoxLayout())
        heading = QLabel("About MINT")
        heading.setStyleSheet("font-weight: bold; color: black")
        description = QLabel()
        description.setText("A Python Qt application for ITER Data Visualtization using the iplotlib framework.")
        jira = QLabel()
        jira.setOpenExternalLinks(True)
        jira.setText(
            f"Report a <a href=\"{bug_link}\"> bug</a> or request a <a href=\"{feature_req_link}\"> feature</a>")
        jira.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        authors = QLabel()
        authors.setText("Authors: Jaswant Panchumarti, Lana Abadie, Piotr Mazur")
        self._descriptionWidget.layout().addWidget(heading)
        self._descriptionWidget.layout().addWidget(description)
        self._descriptionWidget.layout().addWidget(jira)
        self._descriptionWidget.layout().addWidget(authors)

    def _prepare_icon(self):
        self.iconLabel = QLabel("")
        self.iconLabel.setPixmap(create_pxmap('mint64x64'))

    def showEvent(self, ev: QShowEvent):
        self.catalog_environment()
        self._environmentWidget.resizeColumnsToContents()
        self._environmentWidget.resizeRowsToContents()
        return super().showEvent(ev)

    def catalog_environment(self):
        self._model.setColumnCount(3)
        self._model.setHeaderData(0, Qt.Horizontal, 'Package', Qt.DisplayRole)
        self._model.setHeaderData(1, Qt.Horizontal, 'Version', Qt.DisplayRole)
        self._model.setHeaderData(2, Qt.Horizontal, 'Path', Qt.DisplayRole)

        for i, pkg in enumerate(packages):
            name_item = QStandardItem(pkg)
            try:
                version_item = QStandardItem(f"{metadata.version(pkg)}")
            except Exception as ex:
                logging.warning(ex)
                version_item = QStandardItem('---')
            try:
                path_item = QStandardItem(f"{pkgutil.get_loader(pkg).path}")
            except Exception as ex:
                logging.warning(ex)
                try:
                    import_name = pkg if pkg not in aliases else aliases[pkg]
                    path_item = QStandardItem(f"{import_module(import_name).__path__}")
                except Exception as ex:
                    logging.warning(ex)
                    path_item = QStandardItem(f"---")
            self._model.setItem(i, 0, name_item)
            self._model.setItem(i, 1, version_item)
            self._model.setItem(i, 2, path_item)

    def get_contents_as_string(self) -> str:
        root_idx = self._model.invisibleRootItem().index()

        ncols = self._model.columnCount(root_idx)
        output = defaultdict(dict)
        for row, pkg in enumerate(packages):
            for col in range(1, ncols):
                col_name = self._model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
                output[pkg].update({col_name: self._model.data(self._model.index(row, col, root_idx))})

        return json.dumps(output, indent=4)
