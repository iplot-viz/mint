from PySide6.QtCore import QMetaObject, Signal
from PySide6.QtWidgets import *


class UiExportConfig(QWidget):
    browseExport = Signal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        if not parent.objectName():
            parent.setObjectName("ExportConfig")
        parent.resize(700, 300)
        self.verticalLayout = QVBoxLayout(parent)
        self.verticalLayout.setObjectName("verticalLayout")
        self.titleLabel = QLabel(parent)
        self.titleLabel.setObjectName("titleLabel")

        self.verticalLayout.addWidget(self.titleLabel)

        # Main widget
        self.exportWindowWidget = QWidget(parent)
        self.exportWindowWidget.setObjectName("exportWindowWidget")
        self.formLayout = QFormLayout(self.exportWindowWidget)
        self.formLayout.setObjectName("formLayout")
        self.chunksLabel = QLabel(self.exportWindowWidget)
        self.chunksLabel.setObjectName("chunksLabel")
        self.outputPathLabel = QLabel(self.exportWindowWidget)
        self.outputPathLabel.setObjectName("outputPathLabel")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.chunksLabel)
        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.outputPathLabel)

        # Add widgets
        self.exportWidget = QWidget(self.exportWindowWidget)
        self.exportWidget.setObjectName("exportWidget")

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
        self.pathButton.clicked.connect(self.browseExport.emit)
        self.horizontalLayout.addWidget(self.pathButton)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.chunksSpinBox)
        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.pathWidget)

        self.verticalLayout.addWidget(self.exportWindowWidget)

        # Buttons
        self.buttonBox = QWidget(parent)
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

        self.translate_ui(parent)

        QMetaObject.connectSlotsByName(parent)

    # setupUi

    def translate_ui(self, parent):
        parent.setWindowTitle("Export Configuration")
        self.titleLabel.setText("Export settings")
        self.chunksLabel.setText("Chunks")
        self.outputPathLabel.setText("Output Path")
        self.pathButton.setText("Browse")
        self.exportButton.setText("Export")
        self.cancelButton.setText("Cancel")
