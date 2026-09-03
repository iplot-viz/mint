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
        self.timeLabel = QLabel(self.exportWindowWidget)
        self.timeLabel.setObjectName("timeLabel")
        self.samplingLabel = QLabel(self.exportWindowWidget)
        self.samplingLabel.setObjectName("samplingLabel")
        self.outputPathLabel = QLabel(self.exportWindowWidget)
        self.outputPathLabel.setObjectName("outputPathLabel")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.chunksLabel)
        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.timeLabel)
        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.samplingLabel)
        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.outputPathLabel)

        # Add widgets
        self.exportWidget = QWidget(self.exportWindowWidget)
        self.exportWidget.setObjectName("exportWidget")

        # Chunks spin box: any positive integer, the spin box itself enforces integers
        self.chunksSpinBox = QSpinBox(self.exportWidget)
        self.chunksSpinBox.setObjectName("chunksSpinBox")
        self.chunksSpinBox.setMinimum(1)
        self.chunksSpinBox.setMaximum(2147483647)
        self.chunksSpinBox.setSingleStep(10)

        # Time column mode; ignored for pulse exports, which keep absolute time
        self.timeComboBox = QComboBox(self.exportWidget)
        self.timeComboBox.setObjectName("timeComboBox")
        self.timeComboBox.addItems(["Absolute time", "Relative time (s)"])

        # Sampling frequency; Native keeps the original samples and layout
        self.samplingComboBox = QComboBox(self.exportWidget)
        self.samplingComboBox.setObjectName("samplingComboBox")
        for label, freq in [("Native", None), ("1 Hz", 1), ("10 Hz", 10),
                            ("100 Hz", 100), ("1 kHz", 1000), ("10 kHz", 10000)]:
            self.samplingComboBox.addItem(label, freq)

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
        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.timeComboBox)
        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.samplingComboBox)
        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.pathWidget)

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
        self.timeLabel.setText("Time")
        self.samplingLabel.setText("Sampling")
        self.outputPathLabel.setText("Output Path")
        self.pathButton.setText("Browse")
        self.exportButton.setText("Export")
        self.cancelButton.setText("Cancel")
