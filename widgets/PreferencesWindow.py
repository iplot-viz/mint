import typing
from textwrap import dedent

from PyQt5 import QtCore
from PyQt5.QtCore import QAbstractItemModel, QItemSelectionModel, QModelIndex, QVariant, Qt, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QApplication, QCheckBox, QColorDialog, QComboBox, QDataWidgetMapper, QFormLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QSizePolicy, QSpinBox, QSplitter, \
    QStackedWidget, QTreeView, QVBoxLayout, QWidget
from iplotlib.Canvas import Canvas
from iplotlib.Axis import LinearAxis
from iplotlib.Plot import Plot2D
from iplotlib.Signal import ArraySignal, UDAPulse


class PreferencesWindow(QMainWindow):

    preferencesClosed = pyqtSignal()

    def __init__(self, canvas=None):
        super().__init__()
        self.resize(800, 400)
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.forms = {Canvas: CanvasForm(), Plot2D: PlotForm(), LinearAxis: AxisForm(), UDAPulse: SignalForm(), type(None): QPushButton("Select item")}

        self.right_column = QStackedWidget()

        for form in self.forms.values():
            self.right_column.addWidget(form)

        central_widget = QSplitter()
        central_widget.addWidget(self.tree_view)
        central_widget.addWidget(self.right_column)
        central_widget.setSizes([30, 70])

        self.setCentralWidget(central_widget)

    def item_selected(self, item):
        if len(item.indexes()) > 0:
            for i in item.indexes():
                print("\tITEM", i.row(), i.column(), i.data(Qt.UserRole))
                data = i.data(Qt.UserRole)
                index = list(self.forms.keys()).index(type(data))
                self.right_column.setCurrentIndex(index)
                if isinstance(self.right_column.currentWidget(), PreferencesForm):
                    self.right_column.currentWidget().set_model(data)

    def set_canvas(self, canvas):
        self.tree_view.setModel(CanvasItemModel(canvas))
        self.tree_view.selectionModel().selectionChanged.connect(self.item_selected)
        index = list(self.forms.keys()).index(Canvas)
        self.right_column.setCurrentIndex(index)
        if isinstance(self.right_column.currentWidget(), PreferencesForm):
            self.right_column.currentWidget().set_model(canvas)
        self.tree_view.expandAll()

    def closeEvent(self, event):
        QApplication.focusWidget().clearFocus()
        self.preferencesClosed.emit()


class CanvasItemModel(QStandardItemModel):

    def __init__(self, canvas=None):
        super().__init__()

        self.canvas = canvas
        self.createTree()
        self.itemChanged.connect(self.aaa)

    def aaa(self,e):
        print("ZOSIA")

    def createTree(self):
        canvasItem = QStandardItem("Canvas")
        canvasItem.setEditable(False)
        canvasItem.setData(self.canvas, Qt.UserRole)
        self.setItem(0, 0, canvasItem)

        #TODO: Implement stackpanel as a single plot with multiple axes
        for column_idx in range(len(self.canvas.plots)):
            columnItem = QStandardItem("Column " + str(column_idx))

            canvasItem.appendRow(columnItem)

            for plot_idx, plot in enumerate(self.canvas.plots[column_idx]):
                plotItem = QStandardItem("Plot " + str(plot_idx))
                plotItem.setEditable(False)
                plotItem.setData(plot, Qt.UserRole)
                columnItem.appendRow(plotItem)

                for stack_idx, stack in enumerate(plot.signals.values()):
                    for signal_idx, signal in enumerate(stack):
                        signalItem = QStandardItem("Signal " + str(signal_idx))
                        signalItem.setEditable(False)
                        signalItem.setData(signal, Qt.UserRole)
                        plotItem.appendRow(signalItem)

                for axis_idx, axis in enumerate(plot.axes):
                    axisItem = QStandardItem("Axis " + str(axis_idx))
                    axisItem.setEditable(False)
                    axisItem.setData(axis, Qt.UserRole)
                    plotItem.appendRow(axisItem)

    # def item(self, row: int, column: int = ...) -> 'QStandardItem':
    #     print("ITEM", row, column)
    #     return super().item(row, column)



class BeanItemModel(QAbstractItemModel):
    """An implementation of QAbstractItemModel that binds indexes to object properties"""

    def __init__(self, form):
        super().__init__()
        self.form = form

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:
        # print("Get data",self.form)
        if self.form and self.form.model is not None and self.form.fields is not None:
            desc = self.form.fields[index.column()]
            # print("\tDESC",desc,"Model:",self.form.model)
            return getattr(self.form.model, desc[1])
        return ""

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if self.form and self.form.model is not None and self.form.fields is not None:
            desc = self.form.fields[index.column()]
            setattr(self.form.model, desc[1], value)
            print("*** SETATTR",desc[1],value)
            self.dataChanged.emit(self.createIndex(0,0), self.createIndex(100,100))
            self.layoutChanged.emit()
        return True

    def columnCount(self, parent: QModelIndex = ...) -> int:
        if self.form.fields is not None:
            return len(self.form.fields)
        return 1

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return 1

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        return self.createIndex(row, column)

    # def parent(self, child: QModelIndex) -> QModelIndex:
    #     print("PARENT",child)
    #     pass




#TODO: change detach icon to "DETACH" text
#TODO: Make color picker work, make signal style work, add different marker styles
#TODO: Make preferences window bigger
#TODO: Range changes should be included as canvas property: for entire canvas or for plots
class PreferencesForm(QWidget):

    closeForm: pyqtSignal()

    def __init__(self, label: str = None, fields=None):
        super().__init__()
        self.setLayout(QVBoxLayout())
        if label is not None:
            top_label = QLabel(label)
            top_label.setSizePolicy(QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum))
            self.layout().addWidget(top_label)

        self.form = QWidget()
        self.form.setLayout(QFormLayout())
        self.layout().addWidget(self.form)

        close_button = QPushButton("Close")
        # close_button.clicked.connect(self.closeForm.emit)
        # self.layout().addWidget(close_button)

        self.mapper = QDataWidgetMapper()
        self.model = None
        self.mapper.setModel(BeanItemModel(self))

        self.fields = fields
        if self.fields is not None:
            for index, (label, prop, widget) in enumerate(self.fields):
                self.form.layout().addRow(label, widget)
                self.mapper.addMapping(widget, index)

    def set_model(self, obj):
        self.model = obj
        self.mapper.toFirst()




class CanvasForm(PreferencesForm):
    def __init__(self):
        canvas_fields = [
            ("Title", "title", QLineEdit()),
            ("Font size", "font_size", QSpinBox()),
            ("Font color", "font_color", QLineEdit())
        ]
        super().__init__("Canvas", canvas_fields)


class PlotForm(PreferencesForm):
    def __init__(self):
        plot_fields = [
            ("Title", "title", QLineEdit()),
            ("Grid", "grid", QCheckBox()),
            ("Font size", "font_size", QSpinBox()),
            ("Font color", "font_color", QLineEdit())
        ]
        super().__init__("A plot", plot_fields)


class AxisForm(PreferencesForm):
    def __init__(self):
        axis_fields = [
            ("Label", "label", QLineEdit()),
            ("Font size", "font_size", QSpinBox()),
            ("Font color", "font_color", QLineEdit())
        ]
        super().__init__("An axis", axis_fields)


class SignalForm(PreferencesForm):
    def __init__(self):
        signal_fields = [
            ("Label", "title", QLineEdit()),
            ("Color", "color", ColorPicker()),
            ("Thickness", "linesize", QSpinBox()),
            ("Varname", "varname", QLineEdit()),
            ("Style", "style", createComboBox({"solid": "Solid", "dotted": "Dotted", "dashed": "Dashed", "None": "None"})),
        ]
        super().__init__("A signal", signal_fields)


class ColorPicker(QPushButton):

    zosia = pyqtProperty(str, user=True)

    def __init__(self):
        super().__init__()
        self.dialog = QColorDialog(self)
        self.dialog.colorSelected.connect(self.select_color)
        self.setText("Choose color")
        self.clicked.connect(self.open_picker)
        self.selectedColor = ""
        self.metaObject().userProperty().write(self, self.selectedColor)

    def open_picker(self):
        print("Opening picker with property names: " ,self.dynamicPropertyNames())

        self.dialog.show()

    def select_color(self, color):
        rgba = "rgba({},{},{},1)".format(color.red(), color.green(), color.blue())
        self.setStyleSheet("background-color: {}".format(rgba))
        self.selectedColor = '#{:02X}{:02X}{:02X}'.format(color.red(), color.green(), color.blue())

        print("Setting color to: ", self.selectedColor)
        print("\tUSERPROP: ", self.metaObject().userProperty().read(self))
        res = self.setProperty("rgbValue", self.selectedColor)
        # self.metaObject().userProperty().write(self, self.selectedColor)
        print("SET PROPERTY RESULT: ",self.dynamicPropertyNames())


    @pyqtProperty(str, user=True)
    def rgbValue(self):
        return self.selectedColor


def createComboBox(items):
    widget = QComboBox()
    if isinstance(items, dict):
        for k, v in items.items():
            widget.addItem(v, k)
    elif isinstance(items, list):
        for i in items:
            widget.addItem(i)
        pass
    return widget

