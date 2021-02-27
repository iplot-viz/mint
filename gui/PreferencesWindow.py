import typing
from textwrap import dedent
from typing import Collection

from PyQt5 import QtCore
from PyQt5.QtCore import QAbstractItemModel, QByteArray, QEvent, QItemSelectionModel, QMargins, QModelIndex, QVariant, Qt, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QAbstractItemDelegate, QApplication, QCheckBox, QColorDialog, QComboBox, QDataWidgetMapper, QFormLayout, QItemDelegate, QLabel, QLineEdit, QMainWindow, QPushButton, \
    QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QTreeView, QVBoxLayout, QWidget
from iplotlib.Canvas import Canvas
from iplotlib.Axis import LinearAxis
from iplotlib.Plot import Plot2D
from iplotlib.Signal import ArraySignal, UDAPulse


class PreferencesWindow(QMainWindow):

    apply = pyqtSignal()

    def __init__(self, canvas=None):
        super().__init__()
        self.resize(800, 400)
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.forms = {Canvas: CanvasForm(), Plot2D: PlotForm(), LinearAxis: AxisForm(), UDAPulse: SignalForm(), type(None): QPushButton("Select item")}

        self.right_column = QStackedWidget()

        for form in self.forms.values():
            self.right_column.addWidget(form)
            if isinstance(form, PreferencesForm):
                form.applySignal.connect(self.apply.emit)

        central_widget = QSplitter()
        central_widget.addWidget(self.tree_view)
        central_widget.addWidget(self.right_column)
        central_widget.setSizes([30, 70])

        self.setCentralWidget(central_widget)

    def item_selected(self, item):
        if len(item.indexes()) > 0:
            for i in item.indexes():
                print("\tITEM", i.row(), i.column(), "All types:" , type(i.data(Qt.UserRole)).__mro__,i.data(Qt.UserRole))
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

    # def save(self):
    #     PreferencesWindow.apply.emit()

    def closeEvent(self, event):
        if QApplication.focusWidget():
            QApplication.focusWidget().clearFocus()
        self.apply.emit()


class CanvasItemModel(QStandardItemModel):

    def __init__(self, canvas=None, autoNames=False):
        super().__init__()
        self.autoNames = autoNames
        self.canvas = canvas
        self.createTree()

    def createTree(self):
        canvasItem = QStandardItem("Canvas")
        canvasItem.setEditable(False)
        canvasItem.setData(self.canvas, Qt.UserRole)
        if self.autoNames and self.canvas.title:
            canvasItem.setText(self.canvas.title)
        self.setItem(0, 0, canvasItem)

        def addAxis(label, axis, plotItem):
            axisItem = QStandardItem(label)
            axisItem.setEditable(False)
            axisItem.setData(axis, Qt.UserRole)
            if self.autoNames and axis.label:
                axisItem.setText(axis.label)
            plotItem.appendRow(axisItem)

        for column_idx in range(len(self.canvas.plots)):
            columnItem = QStandardItem("Column " + str(column_idx))

            canvasItem.appendRow(columnItem)

            for plot_idx, plot in enumerate(self.canvas.plots[column_idx]):
                plotItem = QStandardItem("Plot " + str(plot_idx))
                plotItem.setEditable(False)
                plotItem.setData(plot, Qt.UserRole)
                if self.autoNames and plot.title:
                    plotItem.setText(plot.title)

                columnItem.appendRow(plotItem)

                if plot:
                    for stack_idx, stack in enumerate(plot.signals.values()):
                        for signal_idx, signal in enumerate(stack):
                            signalItem = QStandardItem("Signal {} stack {}".format(signal_idx, stack_idx))
                            signalItem.setEditable(False)
                            signalItem.setData(signal, Qt.UserRole)
                            if self.autoNames and signal.title:
                                signalItem.setText(signal.title)
                            plotItem.appendRow(signalItem)

                    for axis_idx, axis in enumerate(plot.axes):
                        if isinstance(axis, Collection):
                            for subaxis_idx, subaxis in enumerate(axis):
                                addAxis("Axis {} stack {}".format(axis_idx, subaxis_idx), subaxis, plotItem)
                        else:
                            addAxis("Axis {}".format(axis_idx), axis, plotItem)


class BeanItemModel(QAbstractItemModel):
    """An implementation of QAbstractItemModel that binds indexes to object properties"""

    def __init__(self, form):
        super().__init__()
        self.form = form

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:

        if self.form and self.form.model is not None and self.form.fields is not None:
            desc = self.form.fields[index.column()]

            if desc[2] is not None and hasattr(desc[2],'_items'):
                key = getattr(self.form.model, desc[1])
                keys = list(desc[2]._items.keys())
                if key in keys:
                    return keys.index(key)
                else:
                    return 0
            else:
                return getattr(self.form.model, desc[1])
        return ""

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:

        if self.form and self.form.model is not None and self.form.fields is not None:
            desc = self.form.fields[index.column()]

            if desc[2] is not None and hasattr(desc[2], '_items'):
                keys = list(desc[2]._items.keys())
                print("SETTING VALUE: ", keys[value], "field ", desc[1], "model",self.form.model)
                setattr(self.form.model, desc[1], keys[value])
                print("VAL", self.form.model)
            else:
                print("MODEL SET DATA", role, value, desc)
                setattr(self.form.model, desc[1], value)

            self.dataChanged.emit(self.createIndex(0, 0), self.createIndex(100, 100)) #FIXME: correct this
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


#TODO: Range changes should be included as canvas property: for entire canvas or for plots
class PreferencesForm(QWidget):

    applySignal = pyqtSignal()

    def __init__(self, label: str = None):
        super().__init__()
        self.setLayout(QVBoxLayout())
        if label is not None:
            top_label = QLabel(label)
            top_label.setSizePolicy(QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum))
            self.layout().addWidget(top_label)

        self.form = QWidget()
        self.form.setLayout(QFormLayout())
        self.layout().addWidget(self.form)

        apply_button = QPushButton("Apply")
        apply_button.pressed.connect(self.applySignal.emit)
        self.layout().addWidget(apply_button)

        self.mapper = QDataWidgetMapper()
        self.model = None
        self.mapper.setModel(BeanItemModel(self))

    def add_fields(self, fields):
        self.fields = fields
        if self.fields is not None:

            for index, row in enumerate(self.fields):
                if isinstance(row, tuple):
                    label, prop, widget = row
                    self.form.layout().addRow(label, widget)
                    if isinstance(widget, QComboBox):
                        self.mapper.addMapping(widget, index, b"currentIndex")
                    else:
                        self.mapper.addMapping(widget, index)
                elif isinstance(row, list):
                    for field in row:
                        label, prop, widget = field
                        self.form.layout().addRow(label, widget)
                        self.mapper.addMapping(widget, index)

    def set_model(self, obj):
        self.model = obj
        self.mapper.toFirst()

    def createSpinbox(self, **params):
        widget = QSpinBox()
        if params.get("min"):
            widget.setMinimum(params.get("min"))
        if params.get("max"):
            widget.setMaximum(params.get("max"))

        return widget

    def createComboBox(self, items):
        widget = QComboBox()
        widget._items = items
        if isinstance(items, dict):
            for k, v in items.items():
                widget.addItem(v, k)
        elif isinstance(items, list):
            for i in items:
                widget.addItem(i)
            pass
        return widget

    def createLineEdit(self, **params):
        widget = QLineEdit()
        if params.get("readonly"):
            widget.setReadOnly(params.get("readonly"))
        return widget

    def defaultFontSizeWidget(self):
        return self.createSpinbox(min=0, max=20)

    def defaultLineSizeWidget(self):
        return self.createSpinbox(min=0, max=20)

    def defaultMarkerSizeWidget(self):
        return self.createSpinbox(min=0, max=20)

    def defaultLineStyleWidget(self):
        return self.createComboBox({"Solid": "Solid", "Dotted": "Dotted", "Dashed": "Dashed", "None": "None"})

    def defaultMarkerWidget(self):
        return self.createComboBox({"None": "None", "o": "o", "x": "x"})

    def defaultLinePathWidget(self):
        return self.createComboBox({"None": "Linear", "post": "Last Value"})

class CanvasForm(PreferencesForm):

    def __init__(self):
        super().__init__("Canvas")
        canvas_fields = [
            ("Title", "title", QLineEdit()),
            ("Font size", "font_size", self.defaultFontSizeWidget()),
            ("Shared x axis", "shared_x_axis", QCheckBox()),
            ("Grid", "grid", QCheckBox()),
            ("Legend", "legend", QCheckBox()),
            ("Font color", "font_color", ColorPicker()),
            ("Line style", "line_style", self.defaultLineStyleWidget()),
            ("Line size", "line_size", self.defaultLineSizeWidget()),
            ("Marker", "marker", self.defaultMarkerWidget()),
            ("Marker size", "marker_size", self.defaultMarkerSizeWidget()),
            ("Line Path", "step", self.defaultLinePathWidget())
        ]
        self.add_fields(canvas_fields)


class PlotForm(PreferencesForm):
    def __init__(self):
        super().__init__("A plot")
        plot_fields = [
            ("Title", "title", QLineEdit()),
            ("Grid", "grid", QCheckBox()),
            ("Legend", "legend", QCheckBox()),
            ("Font size", "font_size", self.defaultFontSizeWidget()),
            ("Font color", "font_color", ColorPicker()),
            ("Line style", "line_style", self.defaultLineStyleWidget()),
            ("Line size", "line_size", self.defaultLineSizeWidget()),
            ("Marker", "marker", self.defaultMarkerWidget()),
            ("Marker size", "marker_size", self.defaultMarkerSizeWidget()),
            ("Line Path", "step", self.defaultLinePathWidget())

        ]
        self.add_fields(plot_fields)


class AxisForm(PreferencesForm):
    def __init__(self):
        super().__init__("An axis")

        axis_fields = [
            ("Label", "label", QLineEdit()),
            ("Font size", "font_size", self.defaultFontSizeWidget()),
            ("Font color", "font_color", ColorPicker()),
            # ("Min value", "begin", QLineEdit()),
            # ("Max value", "end", QLineEdit())
        ]

        self.add_fields(axis_fields)


class SignalForm(PreferencesForm):
    def __init__(self):
        super().__init__("A signal")
        signal_fields = [
            ("Label", "title", QLineEdit()),
            ("Varname", "varname", self.createLineEdit(readonly=True)),
            ("Color", "color", ColorPicker()),
            ("Line style", "line_style", self.defaultLineStyleWidget()),
            ("Line size", "line_size", self.defaultLineSizeWidget()),
            ("Marker", "marker", self.defaultMarkerWidget()),
            ("Marker size", "marker_size", self.defaultMarkerSizeWidget()),
            ("Line Path", "step", self.defaultLinePathWidget())        ]
        self.add_fields(signal_fields)


class ColorPicker(QWidget):

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(QMargins())
        button = QPushButton("Select color")
        button.clicked.connect(self.open_picker)
        self.layout().addWidget(button)
        self.dialog = QColorDialog(self)
        self.dialog.colorSelected.connect(self.select_color)
        self.selectedColor = None

    def open_picker(self):
        self.dialog.show()

    def select_color(self, color):
        self.setProperty("rgbValue", '#{:02X}{:02X}{:02X}'.format(color.red(), color.green(), color.blue()))
        print("Color set to ", self.selectedColor)
        QApplication.postEvent(self, QKeyEvent(QEvent.KeyPress, Qt.Key_Enter, Qt.NoModifier))

    @pyqtProperty(str, user=True)
    def rgbValue(self):
        return self.selectedColor

    @rgbValue.setter
    def rgbValue(self, color):
        self.setStyleSheet("background-color: {}".format(color))
        self.selectedColor = color
