# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'streamerConfig.ui'
##
## Created by: Qt User Interface Compiler version 5.14.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import (QCoreApplication, QDate, QDateTime, QMetaObject,
    QObject, QPoint, QRect, QSize, QTime, QUrl, Qt)
from PySide2.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont,
    QFontDatabase, QIcon, QKeySequence, QLinearGradient, QPalette, QPainter,
    QPixmap, QRadialGradient)
from PySide2.QtWidgets import *


class Ui_StreamerConfig(object):
    def setupUi(self, StreamerConfig):
        if not StreamerConfig.objectName():
            StreamerConfig.setObjectName(u"StreamerConfig")
        StreamerConfig.resize(400, 300)
        self.verticalLayout = QVBoxLayout(StreamerConfig)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.titleLabel = QLabel(StreamerConfig)
        self.titleLabel.setObjectName(u"titleLabel")

        self.verticalLayout.addWidget(self.titleLabel)

        self.streamWindowWidget = QWidget(StreamerConfig)
        self.streamWindowWidget.setObjectName(u"streamWindowWidget")
        self.formLayout = QFormLayout(self.streamWindowWidget)
        self.formLayout.setObjectName(u"formLayout")
        self.windowLabel = QLabel(self.streamWindowWidget)
        self.windowLabel.setObjectName(u"windowLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.windowLabel)

        self.windowWidget = QWidget(self.streamWindowWidget)
        self.windowWidget.setObjectName(u"windowWidget")
        self.horizontalLayout = QHBoxLayout(self.windowWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.windowSpinBox = QSpinBox(self.windowWidget)
        self.windowSpinBox.setObjectName(u"windowSpinBox")
        self.windowSpinBox.setMinimum(1)
        self.windowSpinBox.setMaximum(100000)

        self.horizontalLayout.addWidget(self.windowSpinBox)

        self.windowComboBox = QComboBox(self.windowWidget)
        self.windowComboBox.setObjectName(u"windowComboBox")

        self.horizontalLayout.addWidget(self.windowComboBox)


        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.windowWidget)


        self.verticalLayout.addWidget(self.streamWindowWidget)

        self.buttonBox = QWidget(StreamerConfig)
        self.buttonBox.setObjectName(u"buttonBox")
        self.horizontalLayout_2 = QHBoxLayout(self.buttonBox)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.startButton = QPushButton(self.buttonBox)
        self.startButton.setObjectName(u"startButton")

        self.horizontalLayout_2.addWidget(self.startButton)

        self.cancelButton = QPushButton(self.buttonBox)
        self.cancelButton.setObjectName(u"cancelButton")
        self.cancelButton.setFlat(False)

        self.horizontalLayout_2.addWidget(self.cancelButton)


        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(StreamerConfig)

        QMetaObject.connectSlotsByName(StreamerConfig)
    # setupUi

    def retranslateUi(self, StreamerConfig):
        StreamerConfig.setWindowTitle(QCoreApplication.translate("StreamerConfig", u"Streamer Configuration", None))
        self.titleLabel.setText(QCoreApplication.translate("StreamerConfig", u"Stream settings", None))
        self.windowLabel.setText(QCoreApplication.translate("StreamerConfig", u"Window", None))
        self.startButton.setText(QCoreApplication.translate("StreamerConfig", u"Start", None))
        self.cancelButton.setText(QCoreApplication.translate("StreamerConfig", u"Cancel", None))
    # retranslateUi

