from PySide6.QtCore import QMetaObject
from PySide6.QtWidgets import *


class UiExportConfig(object):
    def __init__(self, export_config=None):
        if not export_config.objectName():
            export_config.setObjectName("ExportConfig")
        export_config.resize(700, 300)
        self.verticalLayout = QVBoxLayout(export_config)
        self.verticalLayout.setObjectName("verticalLayout")
        self.titleLabel = QLabel(export_config)
        self.titleLabel.setObjectName("titleLabel")

        self.verticalLayout.addWidget(self.titleLabel)

        # Main widget
        self.exportWindowWidget = QWidget(export_config)
        self.exportWindowWidget.setObjectName("exportWindowWidget")
        self.formLayout = QFormLayout(self.exportWindowWidget)
        self.formLayout.setObjectName("formLayout")
        self.formatLabel = QLabel(self.exportWindowWidget)
        self.formatLabel.setObjectName("formatLabel")
        self.chunksLabel = QLabel(self.exportWindowWidget)
        self.chunksLabel.setObjectName("chunksLabel")
        self.outputPathLabel = QLabel(self.exportWindowWidget)
        self.outputPathLabel.setObjectName("outputPathLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.formatLabel)
        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.chunksLabel)
        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.outputPathLabel)

        # Add widgets
        self.exportWidget = QWidget(self.exportWindowWidget)
        self.exportWidget.setObjectName("exportWidget")
        # self.horizontalLayout = QHBoxLayout(self.windowWidget)
        # self.horizontalLayout.setObjectName("horizontalLayout")
        # self.horizontalLayout.setContentsMargins(0, 0, 0, 0)

        # Format combo box
        self.formatComboBox = QComboBox(self.exportWidget)
        self.formatComboBox.setObjectName("formatComboBox")
        # self.horizontalLayout.addWidget(self.formatComboBox)

        # Chunks spin box
        self.chunksSpinBox = QSpinBox(self.exportWidget)
        self.chunksSpinBox.setObjectName("chunksSpinBox")
        self.chunksSpinBox.setMinimum(50000)
        self.chunksSpinBox.setMaximum(200000)
        self.chunksSpinBox.setSingleStep(10)

        # Output path
        self.pathWidget = QWidget(self.exportWindowWidget)
        self.pathWidget.setObjectName("pathWidget")
        self.horizontalLayout = QHBoxLayout(self.pathWidget)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)

        self.pathLineEdit = QLineEdit(self.pathWidget)
        self.pathLineEdit.setObjectName("pathLineEdit")
        self.horizontalLayout.addWidget(self.pathLineEdit)

        self.pathButton = QPushButton(self.pathWidget)
        self.pathButton.setObjectName("pathButton")
        self.pathButton.clicked.connect(lambda: self.select_folder(export_config))
        self.horizontalLayout.addWidget(self.pathButton)

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.formatComboBox)
        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.chunksSpinBox)
        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.pathWidget)

        self.verticalLayout.addWidget(self.exportWindowWidget)

        # Buttons
        self.buttonBox = QWidget(export_config)
        self.buttonBox.setObjectName("buttonBox")
        self.horizontalLayout_2 = QHBoxLayout(self.buttonBox)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.exportButton = QPushButton(self.buttonBox)
        self.exportButton.setObjectName("exportButton")

        self.horizontalLayout_2.addWidget(self.exportButton)

        self.cancelButton = QPushButton(self.buttonBox)
        self.cancelButton.setObjectName("cancelButton")
        self.cancelButton.setFlat(False)

        self.horizontalLayout_2.addWidget(self.cancelButton)

        self.verticalLayout.addWidget(self.buttonBox)

        self.translate_ui(export_config)

        QMetaObject.connectSlotsByName(export_config)

    # setupUi

    def translate_ui(self, export_config):
        export_config.setWindowTitle("Export Configuration")
        self.titleLabel.setText("Export settings")
        self.formatLabel.setText("Export Format")
        self.chunksLabel.setText("Chunks")
        self.outputPathLabel.setText("Output Path")
        self.pathButton.setText("Browse")
        self.exportButton.setText("Export")
        self.cancelButton.setText("Cancel")

    def select_folder(self, export_config):
        folder = QFileDialog.getExistingDirectory(export_config, "Select Output Folder", "",
                                                  QFileDialog.Option.ShowDirsOnly)
        if folder:
            self.pathLineEdit.setText(folder)