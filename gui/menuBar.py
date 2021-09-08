import json

from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import QAction, QActionGroup, QApplication, QFileDialog, QMainWindow, QMenuBar, QMessageBox, QSizePolicy, QStatusBar

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)


class MainMenuBar(QMenuBar):

    def __init__(self, parent=None, export_widgets=dict()):
        super().__init__(parent)
        self.export_widgets = export_widgets

        self.setSizePolicy(QSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Maximum))

        file_menu = self.addMenu("File")
        help_menu = self.addMenu("Help")

        exit_action = QAction("Exit", self)
        exit_action.setShortcuts(QKeySequence.Quit)
        exit_action.triggered.connect(QApplication.closeAllWindows)

        export_action = QAction("Export workspace", self)
        export_action.triggered.connect(self.do_export)

        import_action = QAction("Import workspace", self)
        import_action.triggered.connect(self.do_import)

        about_action = QAction("About Qt", self)
        about_action.setShortcuts(QKeySequence.New)
        about_action.setStatusTip("About Qt")
        about_action.triggered.connect(QApplication.aboutQt)

        lr_group = QActionGroup(self)
        lr_group.setExclusive(True)

        left_action = QAction("Left", self)
        left_action.setChecked(False)
        left_action.setCheckable(True)
        left_action.setActionGroup(lr_group)

        right_action = QAction("Right", self)
        right_action.setCheckable(True)
        right_action.setChecked(True)
        right_action.setActionGroup(lr_group)

        help_menu.addAction(left_action)
        help_menu.addAction(right_action)
        help_menu.addSection("Testsection")
        help_menu.addAction(about_action)

        file_menu.addAction(export_action)
        file_menu.addAction(import_action)

        file_menu.addAction(exit_action)

    def do_export(self):
        """Exports widgets from self.export_widget to one big json file"""
        try:
            file = QFileDialog.getSaveFileName(self, "Export workspace file")
            if file and file[0]:
                data = dict()
                if self.export_widgets is not None:
                    for k, v in self.export_widgets.items():
                        if v is not None and hasattr(v, "export_json"):
                            try:
                                chunk = v.export_json()
                                logger.info(F"Exporting {k}:{v} chunk={chunk}")
                                data[k] = json.loads(chunk)
                            except:
                                logger.error(F"Error exporting {k}:{v}")
                        else:
                            logger.error(F"Skipping export widget {k}:{v}")

                with open(file[0], "w") as out_file:
                    out_file.write(json.dumps(data, indent=4, sort_keys=True))
        except:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText("Error exporting file")
            box.exec_()

    def do_import(self):
        try:
            file = QFileDialog.getOpenFileName(self, "Open workspace file")
            if file and file[0]:

                with open(file[0], "r") as in_file:
                    data = json.loads(in_file.read())

                    for k, v in self.export_widgets.items():
                        if v is not None and hasattr(v, "import_json") and data.get(k) is not None:
                            v.import_json(json.dumps(data.get(k)))

        except:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setText("Error parsing file")
            box.exec_()
            raise
