from PySide2.QtWidgets import QVBoxLayout
from qtpy.QtWidgets import QApplication, QWidget, QPushButton
from mint.gui.mtStreamConfigurator import MTStreamConfigurator

app = QApplication([])

win = QWidget()
win.setLayout(QVBoxLayout())

swin = MTStreamConfigurator()
swin.streamStarted.connect(lambda: print("start"))

btn = QPushButton("open streamer dialog now", win)
btn.clicked.connect(swin.show)

win.layout().addWidget(btn)

win.show()
app.exec_()