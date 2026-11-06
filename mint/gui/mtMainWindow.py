# Description: A main window embedding a table of signals' description on the right
#               and a Qt iplotlib canvas on the left.
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import weakref
from collections import defaultdict, deque
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
import contextlib
import functools
import getpass
import inspect
import json
import os
import socket
import typing
import pandas as pd

from PySide6.QtCore import QCoreApplication, QEventLoop, QMargins, QModelIndex, QTimer, Qt, QItemSelectionModel, \
    Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QAction
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, \
    QSplitter, QVBoxLayout, QWidget

from iplotDataAccess.dataAccess import DataAccess
from iplotlib.core.axis import LinearAxis
from iplotlib.core.canvas import Canvas
from iplotlib.core.plot import Plot, PlotXY, PlotContour, PlotXYWithSlider, PlotContourWithSlider, PlotImage
from iplotlib.core.signal import SignalXY
from iplotlib.data_access import CanvasStreamer
from iplotlib.interface.iplotSignalAdapter import AccessHelper, ParserHelper
from iplotlib.qt.gui.iplotQtMainWindow import IplotQtMainWindow
from iplotWidgets.sizing import clamp_to_screen

from mint.gui.contextHelp import HELP_ANCHOR_PROPERTY, trigger_context_help
from mint.gui.mtAbout import MTAbout
from mint.gui.mtAppearance import MTAppearanceMenu, register_scale_listener
from mint.tools.icon_loader import create_icon
from mint.gui.mtCreatePulseDialog import MTCreatePulseDialog
from mint.gui.mtDataRangeSelector import MTDataRangeSelector
from mint.gui.mtErrorCatalog import ErrorCatalog
from mint.gui.mtMemoryMonitor import MTMemoryMonitor
from mint.gui.plotRange import read_x_range_ns, read_x_range_pulse_seconds
from mint.gui.mtStatusBar import MTStatusBar
from mint.gui.mtStreamConfigurator import MTStreamConfigurator
from mint.gui.mtSignalConfigurator import MTSignalConfigurator
from mint.gui.mtExportConfigurator import MTExportConfigurator
from mint.models.utils import mtBlueprintParser
from mint.tools.map_tricks import delete_keys_from_dict
from mint.tools.sanity_checks import check_data_range
from mint.gui.shift_handlers import ShiftHandlerMixin

from iplotLogging import setupLogger as setupLog

logger = setupLog.get_logger(__name__)


def _accepts_kwarg(func, name: str) -> bool:
    # Guards the progress-bar wiring against sibling releases (iplotlib, iplotDataAccess)
    # that predate the progress_callback parameter.
    try:
        return name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _ready_at_the_end(method):
    """Let the status bar say Ready only once `method` has done all it does: the steps of a Draw or an import, such as
    reading the table, say it before the canvas is drawn. It is said at the end if the last of them said it."""

    @functools.wraps(method)
    def run(self, *args, **kwargs):
        if self._ready_held:
            return method(self, *args, **kwargs)
        self._ready_held, self._ready_due = True, False
        try:
            return method(self, *args, **kwargs)
        finally:
            self._ready_held = False
            if self._ready_due:
                self.indicate_ready()

    return run


@dataclass
class _TableRows:
    """Where the table row of each waypoint is, for a build that reads while the table can change (see
    MTMainWindow._read_and_draw)."""
    # The uid of the row of each waypoint, by id(waypoint), and the index of each row now, by its uid.
    uids: dict = field(default_factory=dict)
    now: dict = field(default_factory=dict)

    def index(self, waypt) -> typing.Optional[int]:
        """The index of the row of the waypoint now, None if the row is gone."""
        return self.now.get(self.uids.get(id(waypt)))


def _row_index(rows: typing.Optional[_TableRows], waypt) -> typing.Optional[int]:
    """The index of the table row of the waypoint, where it is now if the table can change (see _TableRows)."""
    return waypt.idx if rows is None else rows.index(waypt)


@dataclass
class _Build:
    """A build of the canvas from the variables table (see MTMainWindow.build)."""
    stream: bool
    valid: bool
    ts: typing.Any
    te: typing.Any
    da_params: dict
    x_axis_date: bool
    x_axis_follow: bool
    x_axis_window: typing.Optional[int]
    # The signals of the canvas built before, by uid: the new ones keep their markers.
    previous_signals: dict
    # What build_canvas() draws, by column and row of the plots.
    plan: dict = field(default_factory=dict)
    rows: typing.Optional[_TableRows] = None


@dataclass
class _Import:
    """An import of a workspace (see MTMainWindow.import_dict)."""
    # The waypoints of the table, and the signal of each, which checks that its row reads.
    path: list
    signals: list
    rows: typing.Optional[_TableRows] = None
    # Whether a signal of the workspace can be drawn.
    valid: bool = False
    # The file of the workspace, if it comes from one.
    file: typing.Optional[str] = None
    # The places of the plots of the canvas drawn, or left empty, from (column, row) from 0.
    done: set = field(default_factory=set)


@dataclass
class _Drawing:
    """The rows of a Draw or of an import, built in their order as their data arrive in the background, and their
    plots, each drawn once its rows are built (see MTMainWindow._read_and_draw)."""
    # The rows still to build, as (row, read, place), in their order: the status a row shows can depend on the rows
    # built before it. `read` is the key of the read that brings the data of the row: the place of its plot, or of
    # the next plot for a row of no plot, None after the last plot; `place` is that of its plot, None for a row of
    # no plot.
    rows: deque
    table: _TableRows
    # Builds a row once its data are read, draws the plot of a place once its rows are built, and ends once all are.
    build_row: typing.Callable[[typing.Any], None]
    draw_plot: typing.Callable[[tuple], None]
    finish: typing.Callable[[], None]
    # The reads in the background, by their key; the results of those that arrived and the number of their rows not
    # built yet, until they are; the rows of each plot not built yet, by its place.
    pending: dict = field(default_factory=dict)
    arrived: dict = field(default_factory=dict)
    unread: dict = field(default_factory=dict)
    unbuilt: dict = field(default_factory=dict)
    reads: int = 0
    total: int = 0
    # The plots of the canvas that the places still pending replaced, by place: a Draw that replaces this one takes
    # their properties from them (see MTMainWindow._drop_drawing).
    previous: dict = field(default_factory=dict)
    # Tells why building a row failed, which ends the drawing.
    failed: typing.Optional[typing.Callable[[Exception], None]] = None


class MTMainWindow(ShiftHandlerMixin, IplotQtMainWindow):
    # A Draw or an import whose plots were read in the background ended, drawn or replaced (see _read_and_draw).
    drawn = Signal()

    def __init__(self,
                 canvas: Canvas,
                 da: DataAccess,
                 model: dict,
                 app_version: str,
                 data_dir: os.PathLike = '.',
                 data_sources=None,
                 blueprint: dict = mtBlueprintParser.DEFAULT_BLUEPRINT,
                 impl: str = "matplotlib",
                 parent: typing.Optional[QWidget] = None,
                 flags: Qt.WindowFlags = Qt.WindowFlags()):

        if data_sources is None:
            data_sources = []
        self.canvas = canvas
        self.da = da
        self.plot_classes = {"PlotXY": PlotXY,
                             "PlotContour": PlotContour,
                             "PlotXYWithSlider": PlotXYWithSlider,
                             "PlotContourWithSlider": PlotContourWithSlider,
                             "PlotImage": PlotImage}
        self.appVersion = app_version
        self.dragItem = None
        try:
            blueprint['DataSource']['default'] = data_sources[0]
        except IndexError:
            pass
        except KeyError:
            logger.error('Blueprint does not have a DataSource key!')
            QCoreApplication.exit(-1)

        check_data_range(model)
        self.model = model
        self.sigCfgWidget = MTSignalConfigurator(blueprint=blueprint, scsv_dir=os.path.join(data_dir, 'scsv'),
                                                 data_sources=data_sources)
        self.dataRangeSelector = MTDataRangeSelector(self.model.get("range"), )

        self._data_dir = os.path.join(data_dir, 'workspaces')
        self._data_export_dir = os.path.join(data_dir, 'data_signals')
        self._progressBar = QProgressBar()
        self._statusBar = MTStatusBar()

        super().__init__(parent=parent, flags=flags)

        # Console button and Icon
        self.console_button = QPushButton()
        console_icon = create_icon('terminal')
        self.console_button.setIcon(console_icon)

        self.refreshTimer = QTimer(self)
        self.refreshTimer.setTimerType(Qt.TimerType.CoarseTimer)
        self.refreshTimer.setSingleShot(False)
        self.refreshTimer.timeout.connect(lambda: self.on_timeout())
        self._memoryMonitor = MTMemoryMonitor(parent=self, pid=QCoreApplication.instance().applicationPid())
        self.sigCfgWidget.setParent(self)
        self.dataRangeSelector.setParent(self)
        self._statusBar.setParent(self)
        self._progressBar.setParent(self)
        self._progressBar.setMinimum(0)
        self._progressBar.setMaximum(100)
        self._progressBar.hide()
        self._workspaceLabel = QLabel("No workspace loaded")
        self._import_loaded_data_sources = False
        self._reading_ahead = False
        # A Draw whose plots wait for their data (see _draw_in_background).
        self._drawing = None  # type: typing.Optional[_Drawing]
        # While a Draw or an import runs, the status bar says Ready only at its end (see _ready_at_the_end).
        self._ready_held = False
        self._ready_due = False
        # The views that wait for data read in the background, and whether the status bar says so.
        self._view_reads = 0
        self._view_reads_shown = False
        self._view_reads_check = QTimer(self)
        self._view_reads_check.setSingleShot(True)
        self._view_reads_check.timeout.connect(self._show_view_reads)
        self._statusBar.addPermanentWidget(self._progressBar)
        self._statusBar.addPermanentWidget(QLabel('|'))
        self._statusBar.addPermanentWidget(self.console_button)
        self._statusBar.addPermanentWidget(QLabel('|'))
        self._statusBar.addPermanentWidget(self._memoryMonitor)
        self._statusBar.addPermanentWidget(QLabel('|'))
        self._statusBar.addPermanentWidget(self._workspaceLabel)
        self._statusBar.addPermanentWidget(QLabel('|'))

        self.graphicsArea = QWidget(self)
        self.graphicsArea.setLayout(QVBoxLayout())
        self.graphicsArea.layout().addWidget(self.toolBar)
        self.graphicsArea.layout().addWidget(self.canvasStack)
        self.streamerCfgWidget = MTStreamConfigurator(self)
        self.exportCfgWidget = MTExportConfigurator(self)
        self.createPulseDialog = MTCreatePulseDialog(self)
        self.aboutMINT = MTAbout(self)
        self.setAcceptDrops(True)

        if impl.lower() == "matplotlib":
            from iplotlib.impl.matplotlib.qt.qtMatplotlibCanvas import QtMatplotlibCanvas
            self.qtcanvas = QtMatplotlibCanvas(tight_layout=True, canvas=self.canvas, parent=self.canvasStack)
        elif impl.lower() == "vtk":
            from iplotlib.impl.vtk.qt import QtVTKCanvas
            self.qtcanvas = QtVTKCanvas(canvas=self.canvas, parent=self.canvasStack)
        elif impl.lower() == "pyqt":
            from iplotlib.impl.pyqtgraph.qt import QtPyQtGraphCanvas
            self.qtcanvas = QtPyQtGraphCanvas(canvas=self.canvas, parent=self.canvasStack)
        self.canvasStack.addWidget(self.qtcanvas)
        self.qtcanvas.dropSignal.connect(self.on_drop_plot)
        # Older iplotlib releases read the views in the GUI thread, and tell nothing.
        view_reads = getattr(self.qtcanvas, 'viewReadsChanged', None)
        if view_reads is not None:
            view_reads.connect(self._on_view_reads_changed)
        self._connect_shift_signals()
        self._init_shift_storage()
        self.sigCfgWidget.model.rowsAboutToBeRemoved.connect(
            self._on_rows_about_to_be_removed)
        # The worker threads that read a data source start once the table holds a signal of it, ahead of
        # the Draw. The table is checked once a change is complete: set_dataframe() reports its new rows
        # before it fills their cells.
        self._workers_check = QTimer(self)
        self._workers_check.setSingleShot(True)
        self._workers_check.timeout.connect(self._start_data_access_workers)
        for change in (self.sigCfgWidget.model.dataChanged, self.sigCfgWidget.model.layoutChanged):
            change.connect(lambda *_: self._workers_check.start(0))

        file_menu = self.menuBar().addMenu("&File")
        view_menu = self.menuBar().addMenu("&View")
        help_menu = self.menuBar().addMenu("&Help")
        view_menu.addMenu(MTAppearanceMenu(self.menuBar()))

        exit_action = QAction("Exit", self.menuBar())
        exit_action.setShortcuts(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(QApplication.closeAllWindows)

        about_qt_action = QAction("About Qt", self.menuBar())
        about_qt_action.setStatusTip("About Qt")
        about_qt_action.triggered.connect(QApplication.aboutQt)

        about_action = QAction("About MINT", self.menuBar())
        about_action.setStatusTip("About MINT")
        about_action.triggered.connect(self.aboutMINT.exec_)

        clear_cache_action = QAction("Clear cache", self.menuBar())
        clear_cache_action.setStatusTip("Clear cache")
        clear_cache_action.triggered.connect(self.clear_cache)

        user_manual_action = QAction("User Manual", self.menuBar())
        user_manual_action.setStatusTip("Open the embedded MINT user manual")
        user_manual_action.triggered.connect(lambda: self._open_manual())

        error_ref_action = QAction("Error Reference", self.menuBar())
        error_ref_action.setStatusTip("Browse the catalogue of MINT error messages")
        error_ref_action.triggered.connect(lambda: self._open_manual(anchor="errors"))

        context_help_action = QAction("Context Help", self.menuBar())
        context_help_action.setShortcut(QKeySequence("F1"))
        context_help_action.setShortcutContext(Qt.ApplicationShortcut)
        context_help_action.setStatusTip(
            "Open the user manual at the section relevant to the focused area")
        context_help_action.triggered.connect(
            lambda: trigger_context_help(self._open_manual))

        help_menu.addAction(user_manual_action)
        help_menu.addAction(context_help_action)
        help_menu.addAction(error_ref_action)
        help_menu.addSeparator()
        help_menu.addAction(clear_cache_action)
        help_menu.addAction(about_action)
        help_menu.addAction(about_qt_action)

        # QAction console widget
        show_console_action = QAction(console_icon, "&Show Console", self)
        show_console_action.triggered.connect(self.sigCfgWidget.console.show_console)
        self.console_button.clicked.connect(self.sigCfgWidget.console.show_console)

        # Canvas-centric actions (pulse creation/update, save as image) live in
        # the toolbar, not in the File menu.
        file_menu.addAction(self.sigCfgWidget.tool_bar().openAction)
        file_menu.addAction(self.sigCfgWidget.tool_bar().saveAction)
        file_menu.addAction(self.toolBar.importAction)
        file_menu.addAction(self.toolBar.exportAction)
        file_menu.addAction(show_console_action)
        file_menu.addAction(exit_action)

        self.drawBtn = QPushButton("Draw")
        plot_icon = create_icon('plot')
        self.drawBtn.setIcon(plot_icon)
        self.streamBtn = QPushButton("Stream")
        self.streamBtn.setIcon(plot_icon)
        # Reserve the size hint of the longest label so toggling never shifts neighbouring buttons.
        self.streamBtn.setText("Streamer Settings")
        self.streamBtn.setMinimumWidth(self.streamBtn.sizeHint().width())
        self.streamBtn.setText("Stream")
        self.exportBtn = QPushButton("Export")
        self.exportBtn.setIcon(plot_icon)
        self.daWidgetButtons = QWidget(self)
        self.daWidgetButtons.setLayout(QHBoxLayout())
        self.daWidgetButtons.layout().setContentsMargins(QMargins())
        self.daWidgetButtons.layout().addWidget(self.streamBtn)
        self.daWidgetButtons.layout().addWidget(self.drawBtn)
        self.daWidgetButtons.layout().addWidget(self.exportBtn)

        self.dataAccessWidget = QWidget(self)
        self.dataAccessWidget.setLayout(QVBoxLayout())
        self.dataAccessWidget.layout().setContentsMargins(QMargins())
        self.dataAccessWidget.layout().addWidget(self.dataRangeSelector)
        self.dataAccessWidget.layout().addWidget(self.sigCfgWidget)
        self.dataAccessWidget.layout().addWidget(self.daWidgetButtons)

        self._centralWidget = QSplitter(self)
        self._centralWidget.setOrientation(Qt.Orientation.Horizontal)
        self._centralWidget.addWidget(self.dataAccessWidget)
        self._centralWidget.addWidget(self.graphicsArea)
        self.setCentralWidget(self._centralWidget)
        self.setStatusBar(self._statusBar)

        # Setup connections
        self.drawBtn.clicked.connect(self.draw_clicked)
        self.streamBtn.clicked.connect(self.stream_clicked)
        self.exportBtn.clicked.connect(self.export_clicked)
        self.streamerCfgWidget.streamStarted.connect(self.on_stream_started)
        self.streamerCfgWidget.streamStopped.connect(self.on_stream_stopped)
        self.exportCfgWidget.exportStarted.connect(self.on_export_started)
        self.exportCfgWidget.ui.browseExport.connect(self.export_file)
        self.dataRangeSelector.cancelRefresh.connect(self.stop_auto_refresh)
        self._install_pulse_creation()
        self._install_update_pulse()
        self._install_set_time_window()
        self._install_help_anchors()
        # 1920x1080 is the whole panel on a FullHD screen and the whole logical
        # desktop on a 4K screen at 200%.
        clamp_to_screen(self, 1920, 1080, share=0.95)
        register_scale_listener(self._on_ui_scale_changed)

    def _on_ui_scale_changed(self, factor: float):
        """Rebuild the canvas so plot primitives pick up the new scale.

        The widget font change propagates on its own, but the backends resolve
        font/line/marker sizes while building the figure, so they need a rebuild.
        """
        widget = self.canvasStack.currentWidget()
        if widget is None:
            return
        try:
            widget.set_canvas(self.canvas)
        except Exception as e:
            logger.warning(f"Could not refresh the canvas after a UI scale change: {e}")

    def _install_help_anchors(self):
        # F1 over any of these widgets jumps to the matching manual
        # section. Anchor IDs must exist in mint/data/help/manual.md.
        anchors = {
            self.sigCfgWidget: "table",
            self.dataRangeSelector: "time-configuration",
            self.daWidgetButtons: "draw-stream",
            self.streamerCfgWidget: "draw-stream",
            self.canvasStack: "plotting-area",
        }
        for widget, anchor in anchors.items():
            if widget is not None:
                widget.setProperty(HELP_ANCHOR_PROPERTY, anchor)

    def _install_pulse_creation(self):
        # Toolbar action shown only when the active UDA source can write.
        uda = self._writeable_uda_source()
        if uda is None:
            return
        create_pulse_action = getattr(self.toolBar, 'createPulseAction', None)
        if create_pulse_action is None:
            return
        create_pulse_action.setVisible(True)
        # `triggered` passes `checked` on newer PySide6; *_ keeps it out of `plot`.
        create_pulse_action.triggered.connect(lambda *_: self.on_create_pulse())
        self.createPulseDialog.submitted.connect(self._on_pulse_submitted)

    def _writeable_uda_source(self):
        for name in self.da.get_connected_data_source_names():
            ds = self.da.get_data_source(name)
            if hasattr(ds, "is_write_capable") and ds.is_write_capable():
                return ds
        return None

    def _install_set_time_window(self):
        # Inject Set as Time Window into the backend's native plot context menu.
        parser = self.canvasStack.currentWidget()._parser
        parser.context_menu_extender = self._extend_plot_context_menu

    def _extend_plot_context_menu(self, menu, plot=None):
        # `plot` is the core Plot under the right-click (passed by the backend
        # canvas). Acting on it — not the whole canvas — is what makes this
        # per-plot (#107). Falls back to the first plot when absent.
        x_is_time = self.dataRangeSelector.is_x_axis_date()
        x_is_pulse = self.dataRangeSelector.is_x_axis_pulse_relative()
        menu.addSeparator()
        set_window = menu.addAction("Set as time window")
        set_window.setEnabled(x_is_time or x_is_pulse)
        set_window.triggered.connect(lambda: self.on_set_time_window(plot))

    def on_create_pulse(self):
        uda = self._writeable_uda_source()
        if uda is None:
            return
        if not self.dataRangeSelector.is_x_axis_date():
            QMessageBox.information(
                self, "Create Pulse",
                "Switch to Time Range or Relative mode and draw before "
                "creating a pulse — the canvas x-axis must be absolute time.")
            return
        parser = self.canvasStack.currentWidget()._parser
        x_range = read_x_range_ns(self.canvas, parser)
        if x_range is None:
            QMessageBox.information(self, "Create Pulse",
                                    "No visible time range to create a pulse from. "
                                    "Draw at least one signal first.")
            return
        start_ns, end_ns = x_range
        # The category field is free text, so an empty catalog does not block.
        categories = uda.get_pulse_categories()
        self.createPulseDialog.populate(categories, start_ns, end_ns)
        self.createPulseDialog.show()

    def _on_pulse_submitted(self, data: dict):
        uda = self._writeable_uda_source()
        if uda is None:
            return
        pulse_id = data.get("pulse_id")
        if pulse_id:
            result = uda.update_pulse_info(pulse_id, data["start_ns"],
                                           data["end_ns"], data["status"],
                                           data["description"])
            success_msg = "Pulse {pulse_id} updated."
            error_title = "Update Pulse"
        else:
            scope = f"{data['location']}:{data['category']}"
            try:
                result = uda.add_pulse_info(scope, data["start_ns"],
                                            data["end_ns"], data["status"],
                                            data["description"],
                                            pulse_number=data.get("pulse_number"))
            except TypeError:
                # Older iplotdataaccess without pulse_number support.
                if data.get("pulse_number") is not None:
                    QMessageBox.warning(
                        self, "Create Pulse",
                        "The installed data-access layer cannot create a pulse "
                        "with a chosen number. Leave the number empty to number "
                        "it automatically.")
                    return
                result = uda.add_pulse_info(scope, data["start_ns"],
                                            data["end_ns"], data["status"],
                                            data["description"])
            success_msg = "Pulse {pulse_id} created."
            error_title = "Create Pulse"
        if result.get("ok"):
            saved_id = result.get("pulse_id") or pulse_id
            message = success_msg.format(pulse_id=saved_id)
            logger.info("%s range=[%s, %s] status=%s", message,
                        data["start_ns"], data["end_ns"], data["status"])
            self._statusBar.showMessage(message, 5000)
            self.createPulseDialog.accept()
            QMessageBox.information(self, error_title, message)
        else:
            QMessageBox.warning(self, error_title,
                                f"Could not save pulse: {result.get('error', 'unknown error')}")

    def _install_update_pulse(self):
        # Same gating as _install_pulse_creation; also requires the
        # pulseBrowser to expose update_finish (newer iplotwidgets).
        uda = self._writeable_uda_source()
        if uda is None:
            return
        action = getattr(self.toolBar, 'updatePulseAction', None)
        if action is None:
            return
        browser = self._get_pulse_browser_for_update()
        if browser is None:
            return
        action.setVisible(True)
        action.triggered.connect(lambda *_: self.on_open_update_pulse_browser())

    def _get_pulse_browser_for_update(self):
        # Lazy-init the singleton and connect update_finish exactly once.
        # Returns None when iplotwidgets does not expose Update Pulse yet.
        existing = getattr(self, '_update_pulse_browser', None)
        if existing is not None:
            return existing
        try:
            from iplotWidgets.pulseBrowser.pulseBrowser import PulseBrowser
            browser = PulseBrowser()
        except Exception:
            logger.exception("could not initialise PulseBrowser for update")
            return None
        if not hasattr(browser, 'update_finish') or not hasattr(browser, 'set_update_mode'):
            return None
        browser.update_finish.connect(self._on_update_pulse_selected)
        self._update_pulse_browser = browser
        return browser

    def on_open_update_pulse_browser(self):
        browser = self._get_pulse_browser_for_update()
        if browser is None:
            return
        browser.set_update_mode(True)
        # Freshly created pulses must be listed without a manual Refresh.
        refresh = getattr(browser, 'refresh', None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                logger.exception("pulse browser refresh failed")
        browser.show()
        browser.raise_()

    def _on_update_pulse_selected(self, pulse_id):
        browser = getattr(self, '_update_pulse_browser', None)
        if browser is not None:
            browser.set_update_mode(False)
            browser.hide()
        if not isinstance(pulse_id, str) or not pulse_id:
            return
        uda = self._writeable_uda_source()
        if uda is None:
            return
        pulse_info = uda.get_pulse_info(pulse_id)
        if pulse_info is None:
            QMessageBox.warning(self, "Update Pulse",
                                f"Could not read pulse {pulse_id} from UDA.")
            return
        categories = uda.get_pulse_categories() or [pulse_id.rsplit("/", 1)[0]]
        self.createPulseDialog.populate(
            categories=categories,
            start_ns=int(getattr(pulse_info, 'timeFrom', 0) or 0),
            end_ns=int(getattr(pulse_info, 'timeTo', 0) or 0),
            pulse_id=pulse_id,
            current_status=(getattr(pulse_info, 'status', '') or '').strip(),
            current_description=getattr(pulse_info, 'description', '') or '',
        )
        self.createPulseDialog.show()

    def on_set_time_window(self, plot=None):
        parser = self.canvasStack.currentWidget()._parser
        if self.dataRangeSelector.is_x_axis_pulse_relative():
            x_range = read_x_range_pulse_seconds(self.canvas, parser, plot)
            if x_range is None:
                return
            self.dataRangeSelector.apply_canvas_range_pulse_seconds(*x_range)
            return
        x_range = read_x_range_ns(self.canvas, parser, plot)
        if x_range is None:
            return
        start_ns, end_ns = x_range
        self.dataRangeSelector.force_apply_canvas_range_ns(start_ns, end_ns)

    def wire_connections(self):
        super().wire_connections()
        self.sigCfgWidget.statusChanged.connect(self._statusBar.showMessage)
        self.sigCfgWidget.buildAborted.connect(self.on_table_abort)
        self.sigCfgWidget.showProgress.connect(self._progressBar.show)
        self.sigCfgWidget.hideProgress.connect(self._progressBar.hide)
        self.sigCfgWidget.busy.connect(self.indicate_busy)
        self.sigCfgWidget.ready.connect(self.indicate_ready)
        self.sigCfgWidget.progressChanged.connect(self._progressBar.setValue)
        self.sigCfgWidget.errorCellClicked.connect(self._open_manual)
        self.toolBar.exportAction.triggered.connect(self.on_export)
        self.toolBar.exportDataAction.triggered.connect(self.on_export_data)
        self.toolBar.importAction.triggered.connect(self.on_import)
        self._wire_pulse_browser_selection()

    def pulses_in_use(self):
        """Every pulse the next draw would use: the data range selection plus
        the per-row overrides typed in the signals table."""
        pulses = list(self.dataRangeSelector.get_pulses_in_use())
        pulses.extend(self.sigCfgWidget.model.pulses_in_table())
        return list(dict.fromkeys(pulses))

    def _wire_pulse_browser_selection(self):
        # The pulse browser is a singleton opened from the pulse field, the
        # time range and the table context menu. It asks this window what is
        # in use, so no opener has to know about the others.
        try:
            from iplotWidgets.pulseBrowser.pulseBrowser import PulseBrowser
            browser = PulseBrowser()
        except Exception:
            logger.exception("could not initialise PulseBrowser for the Selected column")
            return
        register = getattr(browser, 'set_selected_pulses_provider', None)
        if register is None:
            return
        register(self.pulses_in_use)
        self._refresh_pulse_selection = browser.refresh_selected_pulses
        self.dataRangeSelector.pulsesChanged.connect(lambda *_: self._refresh_pulse_selection())
        model = self.sigCfgWidget.model
        model.dataChanged.connect(lambda tl, br, *_: self._on_signal_cells_changed(tl, br))
        model.rowsRemoved.connect(lambda *_: self._refresh_pulse_selection())
        model.modelReset.connect(lambda *_: self._refresh_pulse_selection())

    def _on_signal_cells_changed(self, top_left, bottom_right):
        column = self.sigCfgWidget.model.pulse_column()
        if column is not None and top_left.column() <= column <= bottom_right.column():
            self._refresh_pulse_selection()

    @staticmethod
    def on_table_abort(message):
        logger.error(message)
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Table Build Failed")
        box.setText(message)
        box.exec_()

    def detach(self):
        if self.toolBar.detachAction.text() == 'Detach':
            # we detach now.
            self._floatingWindow.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolBar)
            self.graphicsArea.setLayout(QVBoxLayout())
            self.graphicsArea.layout().addWidget(self.canvasStack)
            self._floatingWindow.setCentralWidget(self.graphicsArea)
            self._floatingWindow.setWindowTitle(self.windowTitle())
            self._floatingWindow.show()
            self.toolBar.detachAction.setText('Reattach')
            self.sigCfgWidget.resize_views_to_contents()
        elif self.toolBar.detachAction.text() == 'Reattach':
            # we attach now.
            self.toolBar.detachAction.setText('Detach')
            self.graphicsArea.setLayout(QVBoxLayout())
            self.graphicsArea.layout().addWidget(self.toolBar)
            self.graphicsArea.layout().addWidget(self.canvasStack)
            self._centralWidget.addWidget(self.graphicsArea)
            self.setCentralWidget(self._centralWidget)
            self._floatingWindow.hide()

    def update_canvas_preferences(self):
        self.indicate_busy('Applying preferences...')
        super().update_canvas_preferences()
        self.indicate_ready()

    def reset_prefs(self):
        self.indicate_busy('Resetting preferences...')
        super().reset_prefs()
        self.indicate_ready()

    def re_draw(self):
        self.indicate_busy('Redrawing...')
        super().re_draw()
        self.indicate_ready()

    def save_canvas_image(self):
        w = self.canvasStack.currentWidget()
        if not w:
            return
        file_filter = "PNG Image (*.png);;SVG Image (*.svg);;JPEG Image (*.jpg *.jpeg)"
        filename, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Canvas as Image", dir=self._data_dir, filter=file_filter)
        if filename:
            if not any(filename.lower().endswith(ext) for ext in ('.png', '.svg', '.jpg', '.jpeg')):
                if 'SVG' in selected_filter:
                    filename += '.svg'
                elif 'JPEG' in selected_filter:
                    filename += '.jpg'
                else:
                    filename += '.png'
            self._data_dir = os.path.dirname(filename)
            w.save_canvas_image(filename)

    def on_export(self):
        file = QFileDialog.getSaveFileName(
            self, "Save workspaces as ..", dir=self._data_dir, filter='*.json')
        if file and file[0]:
            if not file[0].endswith('.json'):
                file_name = file[0] + '.json'
            else:
                file_name = file[0]
            self.export_json(file_name)
            self._data_dir = os.path.dirname(file_name)

    def on_export_data(self):
        directory = self._data_export_dir + f"/DataExport_{datetime.now().strftime('%Y%m%d')}.csv"
        file = QFileDialog.getSaveFileName(self, "Save Data as ..", dir=directory, filter='*.csv')
        if file and file[0]:
            if not file[0].endswith('.csv'):
                file_name = file[0] + '.csv'
            else:
                file_name = file[0]
            self._data_export_dir = os.path.dirname(file_name)
            self.export_data_plots(file_name)

    def on_import(self):
        file = QFileDialog.getOpenFileName(self, "Open a workspace ..", dir=self._data_dir)
        if file and file[0]:
            # A running stream is bound to the current workspace's signals;
            # importing replaces them and rebuilds the canvas, so stop it first
            # (as the Stop button does) instead of leaving the streamer redrawing
            # into the new canvas.
            if self.streamerCfgWidget.is_activated():
                self.streamerCfgWidget.stop()
            self._data_dir = os.path.dirname(file[0])
            self.import_json(file[0])

    def on_minimap_toggled(self, checked: bool):
        w = self.canvasStack.currentWidget()
        if not w:
            return
        canvas = w.get_canvas() if hasattr(w, 'get_canvas') else None
        if canvas is None or not checked:
            w.set_minimap(checked)
            return
        target = canvas.get_minimap_target_plot()
        if target is not None and target.axes:
            begin, end = self._requested_x_range_for_axis(target.axes[0])
            canvas.snapshot_minimap_baseline(begin, end)
        canvas.show_minimap = True
        with w.view_retainer():
            w.refresh()

    def _requested_x_range_for_axis(self, axis):
        if not getattr(axis, 'is_date', False):
            return axis.original_begin, axis.original_end
        try:
            ts, te = self.dataRangeSelector.get_time_range()
        except (AttributeError, TypeError, ValueError):
            return axis.original_begin, axis.original_end
        if not isinstance(ts, (int, float)) or not isinstance(te, (int, float)):
            return axis.original_begin, axis.original_end
        if ts >= te:
            return axis.original_begin, axis.original_end
        return int(ts), int(te)

    def _snapshot_minimap_baseline(self):
        get_target = getattr(self.canvas, 'get_minimap_target_plot', None)
        snapshot = getattr(self.canvas, 'snapshot_minimap_baseline', None)
        if get_target is None or snapshot is None:
            return
        target = get_target()
        if target is None or not target.axes:
            snapshot(None, None)
        else:
            begin, end = self._requested_x_range_for_axis(target.axes[0])
            snapshot(begin, end)
        refresh = getattr(self, 'refresh_minimap_availability', None)
        if refresh is not None:
            refresh()
        w = self.canvasStack.currentWidget()
        if w is None:
            return
        eligible = getattr(self.canvas, 'is_minimap_eligible', lambda: False)
        if getattr(self.canvas, 'show_minimap', False) and eligible() and hasattr(w, '_update_minimap'):
            w._update_minimap()

    def indicate_busy(self, msg='Hang on ..', view_reads=False):
        # Before the events run, as the data read for the views can arrive meanwhile (see _show_view_reads).
        self._ready_due, self._view_reads_shown = False, view_reads
        self._progressBar.setMinimum(0)
        self._progressBar.setMaximum(0)
        self._progressBar.show()
        self.statusBar().showMessage(msg)
        QCoreApplication.processEvents()

    def indicate_ready(self):
        self._progressBar.hide()
        self._progressBar.setMinimum(0)
        self._progressBar.setMaximum(100)
        if self._ready_held:
            # The step leaves the progress bar to the next one, and Ready to the end of the task.
            self._ready_due = True
            return
        if self._drawing is not None:
            # Until the plots still read are drawn (see _finish_drawing).
            self._report_drawing(self._drawing)
            return
        if self._view_reads:
            # Until the data read for the views that changed arrive (see _show_view_reads).
            self.indicate_busy('Retrieving data...', view_reads=True)
            return
        self._view_reads_shown = False
        self.statusBar().showMessage('Ready.')
        QCoreApplication.processEvents()

    def _on_view_reads_changed(self, count: int):
        self._view_reads = count
        # Said from the event loop: the canvas tells it while it draws.
        self._view_reads_check.start(0)

    def _show_view_reads(self):
        """The status bar says that data are read for the views that changed until they arrive, when it says nothing else:
        what MINT does meanwhile shows its own progress, and its indicate_ready() says it if they still have not."""
        if self._ready_held:
            return
        message = self.statusBar().currentMessage()
        if self._view_reads:
            if self._progressBar.isHidden() and message in ('', 'Ready.'):
                self.indicate_busy('Retrieving data...', view_reads=True)
        elif self._view_reads_shown and message == 'Retrieving data...':
            self.indicate_ready()

    def clear_cache(self):
        self.da.clear_cache()
        pool = getattr(AccessHelper, 'pool', None)
        if pool is not None:
            pool.clear_cache()

    def _start_data_access_workers(self):
        """Start the worker threads that read the data sources of the table, before a Draw needs them."""
        pool = getattr(AccessHelper, 'pool', None)
        if pool is None:
            return
        try:
            pool.prepare(self.sigCfgWidget.model.data_sources_in_table())
        except Exception:
            logger.exception("Cannot start the data access worker threads ahead of the Draw")

    def _reads_row(self, waypt, signal) -> bool:
        """Whether build() reads the data of the waypoint's signal (see update_signal_data)."""
        if waypt.stack_num and (waypt.col_num or waypt.row_num) and not signal.label:
            return False
        return self.sigCfgWidget.model.fetches_row(waypt.idx)

    def _read_ahead(self, signals: list) -> typing.Optional[dict]:
        """Read the data of the signals all at once, in the background worker threads.

        Returns the results for AccessHelper.prefetched(): empty without worker threads, or None
        if the application quit while waiting.
        """
        # iplotlib releases that predate the pool have none.
        pool = getattr(AccessHelper, 'pool', None)
        if pool is None:
            return {}
        requests = [params for signal in signals for params in AccessHelper.data_requests(signal)]
        if not requests:
            return {}
        self._reading_ahead = True
        self._progressBar.show()
        try:
            return pool.fetch(requests, progress=self._report_read_progress)
        except Exception:
            logger.exception("Reading in the worker threads failed, data are read in the GUI thread from now on")
            AccessHelper.pool = None
            pool.shutdown()
            return {}
        finally:
            self._reading_ahead = False
            self._progressBar.setRange(0, 100)

    @staticmethod
    def _prefetched(results: dict):
        # AccessHelper.prefetched(results), guarded against iplotlib releases that predate it:
        # those read every request in the GUI thread.
        prefetched = getattr(AccessHelper, 'prefetched', None)
        return contextlib.nullcontext() if prefetched is None else prefetched(results)

    def _read_in_batches(self, waypoints: typing.Iterable, stream: bool):
        """Create the signal of each waypoint and yield both, with the data of the signal read ahead.

        The data are read in batches, and a batch ends at a signal whose alias another row uses in x, y or z:
        parsing that row checks whether the row of the alias failed to read, so the alias is read before
        `waypoints` reaches that row. While a pair is handled, its reads are served from what was read ahead.
        Yields (None, None) if the application quit while reading.
        """
        used_in_xyz = self.sigCfgWidget.model.aliases_used_in_xyz()
        read_ahead, batch = {}, []
        for waypt in waypoints:
            if not waypt.func and not waypt.args:
                continue
            signal = waypt.func(*waypt.args, **waypt.kwargs)
            batch.append((waypt, signal))
            if signal.alias in used_in_xyz:
                if not (yield from self._read_batch(batch, stream, read_ahead)):
                    return
                batch = []
        yield from self._read_batch(batch, stream, read_ahead)

    def _read_batch(self, batch: list, stream: bool, read_ahead: dict):
        if not stream:
            results = self._read_ahead([signal for waypt, signal in batch if self._reads_row(waypt, signal)])
            if results is None:
                yield None, None
                return False
            read_ahead.update(results)
        with self._prefetched(read_ahead):
            yield from batch
        return True

    def _old_signals(self, path: list) -> list:
        """The signals of the imported canvas at the places of the waypoints (see import_dict)."""
        return [signal for signal in map(self._old_signal, path) if signal is not None]

    def _old_signal(self, waypt):
        """The signal of the imported canvas at the place of the waypoint, if any (see import_dict)."""
        if not waypt.stack_num or (not waypt.col_num and not waypt.row_num):
            return None
        try:
            plot = self.canvas.plots[waypt.col_num - 1][waypt.row_num - 1]
        except IndexError:
            return None
        stack_signals = plot.signals.get(waypt.stack_num, []) if plot else []
        return stack_signals[waypt.signal_stack_id] if waypt.signal_stack_id < len(stack_signals) else None

    def _report_read_progress(self, done: int, total: int):
        self._progressBar.setRange(0, total)
        self._progressBar.setValue(done)
        self.statusBar().showMessage(f"Retrieving data ({done}/{total}) ..")

    def _begin_export_progress(self):
        self._progressBar.setMinimum(0)
        self._progressBar.setMaximum(100)
        self._progressBar.setValue(0)
        self._progressBar.show()
        QCoreApplication.processEvents()

    def _report_export_progress(self, index, total, name):
        # The bar tracks completed variables; the extra 1% signals that the
        # next variable started. 100% is reserved for the fully finished export.
        if total > 0:
            percent = min(int((index - 1) * 100 / total) + 1, 99)
            self._progressBar.setValue(percent)
        self.statusBar().showMessage(f"Exporting {name} ({index}/{total}) ..")
        QCoreApplication.processEvents()

    def _finish_export_progress(self):
        self._progressBar.setValue(100)
        self.statusBar().showMessage("Export completed")
        QCoreApplication.processEvents()

    def export_dict(self) -> dict:
        self.indicate_busy('Exporting workspace...')
        workspace = {}
        workspace.update({
            '_metadata': {
                'createdAt': datetime.now().isoformat(),
                'createdBy': getpass.getuser(),
                'createdOnHost': socket.gethostname(),
                'appVersion': self.appVersion
            }
        })
        workspace.update({'data_range': self.dataRangeSelector.export_dict()})
        workspace.update({'signal_cfg': self.sigCfgWidget.export_dict()})
        workspace.update({'main_canvas': self.canvasStack.currentWidget().export_dict()})
        self.indicate_ready()
        return workspace

    def validate_imported_canvas(self):
        for i, col in enumerate(self.canvas.plots):
            for j in range(len(col)):
                self._validate_imported_plot(i, j)

    def _validate_imported_plot(self, i: int, j: int):
        """Leave out of a plot of the imported canvas the signals that cannot be drawn, and the plot if none is left."""
        plot = self.canvas.plots[i][j]
        if plot:
            remove_key = []
            for key, values in plot.signals.items():
                plot.signals[key] = [signal for signal in values if
                                     signal is not None and signal.parent is not None]
                if len(plot.signals[key]) == 0:
                    remove_key.append(key)

            for key in remove_key:
                plot.signals.pop(key)

            if not plot.signals.keys() or plot.parent is None:
                self.canvas.plots[i][j] = None

    @_ready_at_the_end
    def import_dict(self, input_dict: dict, file_path: str = None):
        # Close preferences window to prevent stale state
        if self.prefWindow.isVisible():
            self.prefWindow.close()

        self._import_loaded_data_sources = False
        self._drop_drawing()

        # Clear shared parser environment and internal state to prevent memory leaks and ensure a clean rebuild
        ParserHelper.env.clear()
        self.canvasStack.currentWidget()._parser.clear()

        # Clear shift tracking since workspace import replaces the entire signal table.
        self._init_shift_storage()

        self.indicate_busy('Importing workspace...')
        data_range = input_dict.get('data_range')
        self.dataRangeSelector.import_dict(data_range)

        delete_keys_from_dict(input_dict, ['dec_samples'])

        # Remove previous slider references
        self._clean_sliders()

        main_canvas = input_dict.get('main_canvas')
        self.canvas = Canvas.from_dict(main_canvas)

        ts, te = self.dataRangeSelector.get_time_range()
        pulse_number = self.dataRangeSelector.get_pulse_number()
        da_params = dict(ts_start=ts, ts_end=te, pulse_nb=pulse_number)

        signal_cfg = input_dict.get('signal_cfg') or input_dict
        if signal_cfg:
            self.sigCfgWidget.import_dict(signal_cfg)
            self._import_loaded_data_sources = True

        path = list(self.sigCfgWidget.build(**da_params))

        self.indicate_ready()
        self.sigCfgWidget.set_status_message("Update signals ..")
        self.sigCfgWidget.begin_build()
        self.sigCfgWidget.set_progress(0)

        # Clear markers table before importing new signals
        self.qtcanvas._marker_window.clear_info()

        # Clear alias list to check for fetches row
        self.sigCfgWidget.model._alias_list.clear()
        self.sigCfgWidget.model._alias_checked = False

        imported = _Import(path, [waypt.func(*waypt.args, **waypt.kwargs) for waypt in path], file=file_path)
        if self._draws_in_background():
            self._import_in_background(imported)
            return

        # The loop below reads each workspace signal again, with the range it was saved with.
        read_ahead = self._read_ahead(
            [signal for waypt, signal in zip(path, imported.signals) if self.sigCfgWidget.model.fetches_row(waypt.idx)]
            + self._old_signals(path))
        if read_ahead is None:
            return

        # Travel the path and update each signal parameters from workspace and trigger a data access request.
        with self._prefetched(read_ahead):
            for i in range(len(path)):
                self._import_row(imported, i)
        read_ahead.clear()

        if not imported.valid:
            # This means that there are not valid signals to create
            self.canvas.plots = [[]]
        else:
            self.validate_imported_canvas()

        self._signals_updated()

        self.indicate_busy('Drawing...')
        self.canvasStack.currentWidget().set_canvas(self.canvas)
        self._imported_canvas_drawn(imported)
        self.drop_history()  # clean zoom history
        self.indicate_ready()
        self.sigCfgWidget.resize_views_to_contents()

    def _import_row(self, imported: _Import, i: int):
        """Check the row of the i-th waypoint of an import with its data, and put the signal it makes at the place of
        the workspace signal, read again with the range it was saved with (see import_dict())."""
        waypt, signal_valid = imported.path[i], imported.signals[i]
        self.sigCfgWidget.set_status_message(f"Updating {waypt} ..")
        self.sigCfgWidget.set_progress(int(i * 100 / len(imported.path)))
        row_idx = _row_index(imported.rows, waypt)

        if (not waypt.stack_num) or (not waypt.col_num and not waypt.row_num):
            self._update_row(row_idx, signal_valid)
            return

        # Check if signal name is valid (Correct signal name and signal has data)
        self._update_row(row_idx, signal_valid)
        if signal_valid.status_info.result == 'Fail':
            return

        plot = self.canvas.plots[waypt.col_num - 1][waypt.row_num - 1]  # type: Plot
        if not plot:
            return
        plot.parent = weakref.ref(self.canvas)
        # Stored positions can exceed the built canvas when sibling
        # signals failed to load; skip them instead of aborting the import.
        stack_signals = plot.signals.get(waypt.stack_num, [])
        if waypt.signal_stack_id >= len(stack_signals):
            logger.warning(f"Skipping workspace signal at stack {waypt.stack_num}, "
                           f"position {waypt.signal_stack_id}: canvas has {len(stack_signals)} signals there")
            return
        old_signal = stack_signals[waypt.signal_stack_id]

        params = dict()
        for f in fields(old_signal):
            if f.name == 'children':  # Don't copy children.
                continue
            else:
                params.update({f.name: getattr(old_signal, f.name)})

        # Propagate uid from row to signal for workspace without it
        if 'uid' not in params or params['uid'] is None:
            params['uid'] = waypt.kwargs['uid']

        new_signal = waypt.func(*waypt.args, signal_class=waypt.kwargs.get('signal_class'), **params)
        new_signal.parent = weakref.ref(plot)

        self._update_row(row_idx, new_signal)
        # Check if new signal is valid
        if new_signal.status_info.result == 'Fail':
            plot.signals[waypt.stack_num][waypt.signal_stack_id] = None
            return

        # Indicate valid signal
        imported.valid = True

        # Replace signal
        plot.signals[waypt.stack_num][waypt.signal_stack_id] = new_signal

        # Add markers in the markers table when importing, only if the signal is SignalXY and has markers
        if isinstance(new_signal, SignalXY) and new_signal.markers_list:
            self.qtcanvas._marker_window.import_table(new_signal)

    def _signals_updated(self):
        """Show in the table the status of the rows that an import updated."""
        self.sigCfgWidget.set_progress(99)

        self.sigCfgWidget.model.dataChanged.emit(self.sigCfgWidget.model.index(0, 0),
                                                 self.sigCfgWidget.model.index(
                                                     self.sigCfgWidget.model.rowCount(QModelIndex()) - 1,
                                                     self.sigCfgWidget.model.columnCount(QModelIndex()) - 1))

        self.sigCfgWidget.set_progress(100)

    def _imported_canvas_drawn(self, imported: _Import):
        self.canvasStack.refreshLinks()
        # Compute statistics when importing workspace
        if imported.path:
            self.canvasStack.currentWidget().stats(self.canvas)
        self._snapshot_minimap_baseline()

    def _import_in_background(self, imported: _Import):
        """Draw the imported canvas at once, and each of its plots once the data of its rows are read (see
        _read_and_draw). Ends as import_dict() does once all are drawn."""
        uids = self.sigCfgWidget.model.get_dataframe()['uid'].tolist()
        imported.rows = _TableRows({id(waypt): uids[waypt.idx] for waypt in imported.path})
        rows = self._rows_in_reads(list(range(len(imported.path))), lambda i: self._imported_place(imported.path[i]))
        places = {(i, j): (plot.row_span, plot.col_span) for i, column in enumerate(self.canvas.plots)
                  for j, plot in enumerate(column) if plot is not None}

        canvas_widget = self.canvasStack.currentWidget()
        canvas_widget.set_pending_places(self.canvas, places)
        canvas_widget.set_canvas(self.canvas)
        self.canvasStack.refreshLinks()
        self.drop_history()  # clean zoom history

        # Each row reads the data that check it, and those of the workspace signal it takes the place of.
        requests = defaultdict(list)
        for i, read, _ in rows:
            waypt = imported.path[i]
            if self.sigCfgWidget.model.fetches_row(waypt.idx):
                requests[read] += AccessHelper.data_requests(imported.signals[i])
            old_signal = self._old_signal(waypt)
            if old_signal is not None:
                requests[read] += AccessHelper.data_requests(old_signal)
        self._read_and_draw(_Drawing(rows, imported.rows, functools.partial(self._import_row, imported),
                                     lambda place: self._draw_imported_plot(imported, *place),
                                     functools.partial(self._finish_import, imported, places),
                                     failed=functools.partial(self._import_failed, imported)), requests)

    def _imported_place(self, waypt) -> typing.Optional[tuple]:
        """The place, (column, row) from 1, of the plot of the imported canvas the waypoint puts its signal in."""
        if not waypt.stack_num or (not waypt.col_num and not waypt.row_num):
            return None
        try:
            plot = self.canvas.plots[waypt.col_num - 1][waypt.row_num - 1]
        except IndexError:
            return None
        return (waypt.col_num, waypt.row_num) if plot else None

    def _draw_imported_plot(self, imported: _Import, col: int, row: int):
        """Draw a plot of the imported canvas once its rows are checked, or nothing if none of its signals can be."""
        self._validate_imported_plot(col - 1, row - 1)
        plot = self.canvas.plots[col - 1][row - 1]
        canvas_widget = self.canvasStack.currentWidget()
        imported.done.add((col - 1, row - 1))
        if plot is None:
            canvas_widget.drop_pending_place(col - 1, row - 1)
        else:
            canvas_widget.draw_plot(plot)

    def _finish_import(self, imported: _Import, places: dict):
        """End an import whose plots are drawn, as import_dict() ends."""
        canvas_widget = self.canvasStack.currentWidget()
        if not imported.valid:
            # This means that there are not valid signals to create
            self.canvas.plots = [[]]
            canvas_widget.set_pending_places(self.canvas, {})
            canvas_widget.set_canvas(self.canvas)
        else:
            self.validate_imported_canvas()
            # The plots of the workspace that no row of the table checked.
            for i, j in places:
                if (i, j) in imported.done:
                    continue
                plot = self.canvas.plots[i][j]
                if plot is None:
                    canvas_widget.drop_pending_place(i, j)
                else:
                    canvas_widget.draw_plot(plot)
        self._signals_updated()
        self._imported_canvas_drawn(imported)
        self.indicate_ready()
        self.sigCfgWidget.resize_views_to_contents()

    def import_json(self, file_path: str):
        self.statusBar().showMessage(f"Importing {file_path} ..")
        try:
            logger.info(f"Loading workspace: {file_path}")
            with open(file_path, mode='r') as f:
                payload = f.read()
                payload = payload.replace("data_access.dataAccessSignal.DataAccessSignal",
                                          "interface.iplotSignalAdapter.IplotSignalAdapter")
                replacements = {'varname': 'name',
                                'datasource': 'data_source',
                                'pulsenb': 'pulse_nb',
                                'time_model': 'data_range'
                                }
                for old, new in replacements.items():
                    payload = payload.replace(old, new)
                self.import_dict(json.loads(payload, object_hook=lambda d: {int(k) if k.lstrip('-').isdigit() else k: v
                                                                            for k, v in d.items()}), file_path)
                logger.info(f"Finished loading workspace {file_path}")
                # Update the workspace label in the status bar after successful import
                self._workspaceLabel.setText(os.path.basename(file_path))
                self._workspaceLabel.setToolTip(file_path)
        except Exception as e:
            logger.exception(e)
            self._tell_import_failed(e, file_path)
            self.indicate_ready()
            if self._import_loaded_data_sources:
                self._workspaceLabel.setText(os.path.basename(file_path))
                self._workspaceLabel.setToolTip(file_path)
            return

    @staticmethod
    def _tell_import_failed(error: Exception, file_path: typing.Optional[str]):
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText(f"Error {str(error)}: cannot import workspace" + (f" from file: {file_path}" if file_path else ""))
        box.exec_()

    def _import_failed(self, imported: _Import, error: Exception):
        """Tell why an import read in the background could not be imported, as import_json() does."""
        self.indicate_ready()
        self._tell_import_failed(error, imported.file)

    def export_data_plots(self, file_path: str):
        self.statusBar().showMessage(f"Exporting {file_path} ..")
        try:
            kwargs = {}
            if _accepts_kwarg(self.canvas.get_signals_as_csv, 'progress_callback'):
                self._begin_export_progress()
                kwargs['progress_callback'] = self._report_export_progress
            with open(file_path, mode='w') as f:
                f.write(self.canvas.get_signals_as_csv(**kwargs))
            logger.info(f"Finished exporting data {file_path}")
            if kwargs:
                self._finish_export_progress()
            self.indicate_ready()
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText(f"Error {str(e)}: cannot export data plots to file: {file_path}")
            logger.exception(e)
            box.exec_()
            self.indicate_ready()
            return

    def export_json(self, file_path: str):
        self.statusBar().showMessage(f"Exporting {file_path} ..")
        try:
            with open(file_path, mode='w') as f:
                f.write(json.dumps(self.export_dict()))
            logger.info(f"Finished exporting workspace {file_path}")
        except Exception as e:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText(f"Error {str(e)}: cannot export workspace to file: {file_path}")
            logger.exception(e)
            box.exec_()
            self.indicate_ready()
            return

    def start_auto_refresh(self):
        if self.canvas.auto_refresh:
            logger.info(F"Scheduling canvas refresh in {self.canvas.auto_refresh} seconds")
            self.refreshTimer.start(self.canvas.auto_refresh * 1000)
            self.dataRangeSelector.refreshActivate.emit()

    def stop_auto_refresh(self):
        self.dataRangeSelector.refreshDeactivate.emit()
        if self.refreshTimer is not None:
            self.refreshTimer.stop()

    def home(self):
        # A relative-time canvas keeps refreshing on a timer. Stop it before
        # restoring the view (order-independent of the base reset); the refresh
        # resumes only on the next Draw.
        if self.refreshTimer.isActive():
            logger.info("Canvas auto-refresh cancelled (Home button; press Draw to resume)")
            self.stop_auto_refresh()
        super().home()

    @_ready_at_the_end
    def draw_clicked(self, no_build: bool = False):
        """This function creates and draws the canvas getting data from variables table and time/pulse widget"""

        if self.streamerCfgWidget.is_activated():
            return

        # Close preferences window to prevent stale state (same as import_dict)
        if self.prefWindow.isVisible():
            self.prefWindow.close()

        if not no_build:
            # Dumps are done before canvas processing
            dump_dir = os.path.expanduser("~/.local/1Dtool/dumps/")
            Path(dump_dir).mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"signals_table_{os.getpid()}_{timestamp}.scsv"
            self.sigCfgWidget.export_scsv(os.path.join(dump_dir, file_name))

            if self._draws_in_background():
                self._draw_in_background()
                return
            self._drop_drawing()
            if not self.build():
                return
        self._show_built_canvas()

    def _show_built_canvas(self):
        """Draw the canvas that build() built, as Draw does."""
        self.indicate_busy("Drawing...")
        self.stop_auto_refresh()

        self.canvasStack.currentWidget().unfocus_plot()
        self.canvasStack.currentWidget().set_canvas(self.canvas)
        self.canvasStack.refreshLinks()
        self.canvasStack.currentWidget().check_markers(self.canvas)
        self.canvasStack.currentWidget().stats(self.canvas)
        self._snapshot_minimap_baseline()

        self.prefWindow.update()
        if self.prefWindow.isVisible():
            self.prefWindow.treeView.selectionModel().select(self.prefWindow.treeView.model().index(0, 0),
                                                             QItemSelectionModel.Select)

        self.drop_history()  # clean zoom history
        self.start_auto_refresh()
        refresh = getattr(self, '_refresh_pulse_selection', None)
        if refresh is not None:
            refresh()
        self.indicate_ready()

    def _draws_in_background(self) -> bool:
        """Whether Draw reads the data in the background and draws each plot once its data arrive (see
        _draw_in_background): with worker threads, and an iplotlib that draws a canvas plot by plot."""
        return getattr(AccessHelper, 'pool', None) is not None and \
            hasattr(self.canvasStack.currentWidget(), 'set_pending_places')

    def _draw_in_background(self):
        """Draw the canvas at once, and each of its plots once its data are read (see _read_and_draw): until then its
        place says that its data are read, and the window answers meanwhile. Ends as draw_clicked() does once all are
        drawn."""
        self._drop_drawing()
        build = self._begin_build(stream=False)
        created = self._created_rows(build) if build.valid else []
        if created is None:
            return
        rows = self._rows_in_reads(created, lambda row: (row[0].col_num, row[0].row_num) if self._plots_row(*row)
                                   else None)

        places = {(col, row): (entry["row_span"], entry["col_span"])
                  for col, plan_rows in build.plan.items() for row, entry in plan_rows.items()}
        for (waypt, _), _, place in rows:
            if place is not None:
                row_span, col_span = places.get(place, (1, 1))
                places[place] = (max(row_span, waypt.row_span), max(col_span, waypt.col_span))
        pending = {place for _, _, place in rows if place is not None}

        self.indicate_busy("Drawing...")
        self.stop_auto_refresh()
        self._clean_sliders()
        # Keep copy of previous canvas to be able to restore preferences
        old_canvas = self.canvas.to_dict()
        previous = {(col, row): self.canvas.plots[col - 1][row - 1] for col, row in pending
                    if col <= len(self.canvas.plots) and row <= len(self.canvas.plots[col - 1])
                    and self.canvas.plots[col - 1][row - 1] is not None}
        # The plots whose rows were all read with the rows that others use in x, y or z are drawn at once.
        self._lay_out(places, lambda col, row: None if (col, row) in pending else self._plot_of(
            build.plan[col][row], col, row, build.x_axis_date, build.x_axis_follow, build.x_axis_window))
        self.canvas.merge(old_canvas)

        canvas_widget = self.canvasStack.currentWidget()
        canvas_widget.unfocus_plot()
        canvas_widget.set_pending_places(self.canvas, {(col - 1, row - 1): places[(col, row)] for col, row in pending})
        canvas_widget.set_canvas(self.canvas)
        self.canvasStack.refreshLinks()
        self.drop_history()  # clean zoom history

        requests = defaultdict(list)
        for (waypt, signal), read, _ in rows:
            if self._reads_row(waypt, signal):
                requests[read] += AccessHelper.data_requests(signal)
        self._read_and_draw(_Drawing(rows, build.rows, lambda row: self._build_row(build, *row),
                                     lambda place: self._place_plot(build, old_canvas, *place),
                                     functools.partial(self._finish_drawing, build, places), previous=previous),
                            requests)

    @staticmethod
    def _plots_row(waypt, signal) -> bool:
        """Whether build() adds the signal of the waypoint to a plot, once its data are read (see _build_row())."""
        return bool(waypt.stack_num and (waypt.col_num or waypt.row_num) and signal.label)

    @staticmethod
    def _rows_in_reads(rows: list, place_of: typing.Callable) -> deque:
        """The rows as _Drawing keeps them: each with its read, that of its plot, place_of(row), or of the next plot
        for a row of no plot."""
        in_reads, read = deque(), None
        for row in reversed(rows):
            place = place_of(row)
            if place is not None:
                read = place
            in_reads.appendleft((row, read, place))
        return in_reads

    def _read_and_draw(self, drawing: _Drawing, requests: dict):
        """Read in the background the data of the rows of `drawing`, by read, build each row in its order once its data
        and those of the rows before it are there, and draw each plot once its rows are built (see _read_arrived())."""
        drawing.total = len(drawing.rows)
        for _, read, place in drawing.rows:
            drawing.unread[read] = drawing.unread.get(read, 0) + 1
            if place is not None:
                drawing.unbuilt[place] = drawing.unbuilt.get(place, 0) + 1
        self._drawing = drawing
        # Gone already if reading the rows that others use in x, y or z failed in them.
        pool = AccessHelper.pool
        if pool is not None:
            try:
                for read in drawing.unread:
                    # A shutdown of the worker threads meanwhile leaves the rows of the read to read in this thread.
                    drawing.pending[read] = pool.fetch_later(
                        requests.get(read, []), functools.partial(self._read_arrived, drawing, read),
                        on_stopped=functools.partial(self._read_arrived, drawing, read, {}))
                self._report_drawing(drawing)
            except Exception:
                logger.exception("Reading in the worker threads failed, data are read in the GUI thread from now on")
                AccessHelper.pool = None
                pool.shutdown()
                for pending in drawing.pending.values():
                    pending.cancel()
                pool = None
        if pool is None:
            drawing.pending = dict.fromkeys(drawing.unread)
            for read in list(drawing.pending):
                self._read_arrived(drawing, read, {})
        if not drawing.rows and self._drawing is drawing:
            self._end_drawing(drawing)

    def _created_rows(self, build: _Build) -> typing.Optional[list]:
        """The waypoints of the table and their signals, as build() makes them, with the data still to read. The rows
        up to one whose alias another row uses in x, y or z are read and built here, first: parsing that row checks
        whether the row of the alias failed to read (see _read_in_batches). None if the application quit while
        reading."""
        uids = self.sigCfgWidget.model.get_dataframe()['uid'].tolist()
        used_in_xyz = self.sigCfgWidget.model.aliases_used_in_xyz()
        rows = _TableRows()
        read_ahead, batch = {}, []
        for waypt in self.sigCfgWidget.build(**build.da_params):
            if not waypt.func and not waypt.args:
                continue
            signal = waypt.func(*waypt.args, **waypt.kwargs)
            rows.uids[id(waypt)] = uids[waypt.idx]
            batch.append((waypt, signal))
            if signal.alias in used_in_xyz:
                results = self._read_ahead([signal for waypt, signal in batch if self._reads_row(waypt, signal)])
                if results is None:
                    return None
                read_ahead.update(results)
                with self._prefetched(read_ahead):
                    for row in batch:
                        self._build_row(build, *row)
                batch = []
        # From now on, the table can change while the data are read.
        build.rows = rows
        return batch

    def _read_arrived(self, drawing: _Drawing, read, results: dict):
        """Build, with the data that arrived, the rows whose data and those of the rows before them are there, and
        draw each plot whose rows are all built (see _read_and_draw())."""
        if drawing is not self._drawing or read not in drawing.pending:
            return
        del drawing.pending[read]
        drawing.arrived[read] = results
        drawing.reads += 1
        # The table can change while the data are read: each row shows its status where it is now.
        drawing.table.now = self._table_rows()
        try:
            while drawing.rows and drawing.rows[0][1] in drawing.arrived:
                row, row_read, place = drawing.rows.popleft()
                with self._prefetched(drawing.arrived[row_read]):
                    drawing.build_row(row)
                    if place is not None:
                        drawing.unbuilt[place] -= 1
                        if not drawing.unbuilt[place]:
                            drawing.draw_plot(place)
                drawing.unread[row_read] -= 1
                if not drawing.unread[row_read]:
                    # The results of a read go once its rows are built.
                    del drawing.arrived[row_read]
        except Exception as error:
            logger.exception("Cannot draw the data read in the background")
            self._stop_drawing()
            if drawing.failed is not None:
                drawing.failed(error)
            self.indicate_ready()
            return
        if drawing.rows:
            self._report_drawing(drawing)
        else:
            self._end_drawing(drawing)

    def _end_drawing(self, drawing: _Drawing):
        self._drawing = None
        try:
            drawing.finish()
        finally:
            self.drawn.emit()

    def wait_until_drawn(self):
        """Wait until the plots of a Draw or an import read in the background are drawn, running the events meanwhile:
        for what needs the whole canvas without the user, as the export of its image from the command line."""
        if self._drawing is None:
            return
        loop = QEventLoop()
        self.drawn.connect(loop.quit)
        try:
            loop.exec()
        finally:
            self.drawn.disconnect(loop.quit)

    def _place_plot(self, build: _Build, old_canvas: dict, col: int, row: int):
        """Draw the plot of a place of a Draw, or nothing if it has nothing to draw (see _plot_of())."""
        entry = build.plan.get(col, {}).get(row)
        plot = self._plot_of(entry, col, row, build.x_axis_date, build.x_axis_follow,
                             build.x_axis_window) if entry else None
        canvas_widget = self.canvasStack.currentWidget()
        self.canvas.plots[col - 1][row - 1] = plot
        if plot is None:
            canvas_widget.drop_pending_place(col - 1, row - 1)
            return
        plot.parent = weakref.ref(self.canvas)
        self.canvas.merge_plot(plot, col - 1, row - 1, old_canvas)
        canvas_widget.draw_plot(plot)

    def _finish_drawing(self, build: _Build, places: dict):
        """End a Draw whose plots are all drawn, as draw_clicked() ends."""
        final = {(col, row): (entry["row_span"], entry["col_span"])
                 for col, rows in build.plan.items() for row, entry in rows.items()}
        canvas_widget = self.canvasStack.currentWidget()
        if final != places:
            # Plots none of whose rows could be read leave the grid as build() would have laid it out.
            plots = {(col, row): self.canvas.plots[col - 1][row - 1] for col, row in places}
            self._lay_out(final, lambda col, row: plots.get((col, row)))
            canvas_widget.set_canvas(self.canvas)
        # It listed the plots drawn when the Draw began.
        self.canvasStack.refreshLinks()
        canvas_widget.check_markers(self.canvas)
        canvas_widget.stats(self.canvas)
        self._snapshot_minimap_baseline()

        self.prefWindow.update()
        if self.prefWindow.isVisible():
            self.prefWindow.treeView.selectionModel().select(self.prefWindow.treeView.model().index(0, 0),
                                                             QItemSelectionModel.Select)

        self.start_auto_refresh()
        refresh = getattr(self, '_refresh_pulse_selection', None)
        if refresh is not None:
            refresh()
        logger.info("Built canvas")
        self.indicate_ready()

    def _report_drawing(self, drawing: _Drawing):
        # The bar counts the rows built, as an import counts them in the table.
        self._progressBar.setRange(0, 100)
        self._progressBar.setValue(int((drawing.total - len(drawing.rows)) * 100 / max(drawing.total, 1)))
        self._progressBar.show()
        self.statusBar().showMessage(f"Retrieving data ({drawing.reads}/{drawing.reads + len(drawing.pending)}) ..")

    def _drop_drawing(self):
        """Forget a Draw whose plots still wait for their data, as another canvas replaces it: their places get back
        the plots they replaced, which the canvas that replaces it takes their properties from, as from the plots a
        Draw ended would have drawn there."""
        drawing = self._stop_drawing()
        if drawing is None:
            return
        for (col, row), plot in drawing.previous.items():
            if drawing.unbuilt.get((col, row)):
                self.canvas.plots[col - 1][row - 1] = plot

    def _stop_drawing(self) -> typing.Optional[_Drawing]:
        """Wait no more for the data of the plots of a Draw or an import, if one waits: the drawing it was."""
        drawing, self._drawing = self._drawing, None
        if drawing is None:
            return None
        self.drawn.emit()
        for pending in drawing.pending.values():
            if pending is not None:
                pending.cancel()
        self.canvasStack.currentWidget().drop_pending_places()
        return drawing

    def _table_rows(self) -> dict:
        """The index of each row of the table, by its uid."""
        return {uid: idx for idx, uid in enumerate(self.sigCfgWidget.model.get_dataframe()['uid'])}

    def stream_clicked(self):
        """While streaming, stop directly. Otherwise open the streamer dialog."""
        if self.streamerCfgWidget.is_activated():
            self.streamerCfgWidget.stop()
        else:
            self.streamerCfgWidget.show()

    def export_clicked(self):
        """This function shows the export dialog and then creates a file with the correspondence format that contains
        info of the whole canvas"""
        self.exportCfgWidget.show()

    def stream_callback(self, signal):
        # Coalesce bursts on the parser instead of one redraw per sample.
        self.canvasStack.currentWidget()._parser.request_signal_redraw(signal)

    @_ready_at_the_end
    def on_stream_started(self):
        self.streamerCfgWidget.hide()
        self._drop_drawing()
        self.streamBtn.setText("Stop")
        # Draw would rebuild the canvas under the live stream.
        self.drawBtn.setEnabled(False)
        self.stop_auto_refresh()
        logger.info("Canvas auto-refresh cancelled (entered streaming mode)")

        # Freeze canvas repaints across the whole rebuild: build() empties the
        # scene and indicate_busy() spins the event loop, which would paint the
        # emptied canvas (a blank flash) before set_canvas repopulates it.
        canvas_widget = self.canvasStack.currentWidget()
        canvas_widget.setUpdatesEnabled(False)
        try:
            self.build(stream=True)

            self.indicate_busy('Connecting to stream and drawing...')
            canvas_widget.unfocus_plot()
            canvas_widget.set_canvas(self.canvas)
            self.canvasStack.refreshLinks()
        finally:
            canvas_widget.setUpdatesEnabled(True)

        # Streaming makes the mini-map ineligible, and the rebuild above does not
        # go through the paths that keep the toolbar in sync. Do it here, before
        # the stream starts feeding the canvas.
        self.refresh_minimap_availability()

        self.streamerCfgWidget.streamer = CanvasStreamer(self.da)
        window_ns = self.streamerCfgWidget.time_window() * 1_000_000_000
        max_points = self.streamerCfgWidget.max_points()
        self.streamerCfgWidget.streamer.start(self.canvas, self.stream_callback,
                                              window_ns=window_ns, max_points=max_points)
        self.indicate_ready()

    def on_stream_stopped(self):
        self.streamBtn.setText("Stream")
        self.drawBtn.setEnabled(True)

    def export_file(self):
        file, export_filter = QFileDialog.getSaveFileName(self,
                                                          "Export file as ..",
                                                          dir=self._data_export_dir,
                                                          filter="HDF5 (*.hdf5);;Parquet (*.parquet)")
        if not file:
            return

        ext = export_filter.split("*.")[-1].rstrip(")")
        if not file.endswith(f'.{ext}'):
            file += f'.{ext}'

        self._data_export_dir = os.path.dirname(file)
        self.exportCfgWidget.ui.pathLineEdit.setText(file)

    def on_export_started(self, data: dict):
        self.exportCfgWidget.hide()

        ts, te = self.dataRangeSelector.get_time_range()
        pulse_number = self.dataRangeSelector.get_pulse_number()
        export_format = data['format'].split(".")[-1]
        chunks = data['chunks']
        output_path = data['output_path']

        if not output_path or export_format not in ["parquet", "hdf5"]:
            self.show_popup_msg("Invalid export configuration",
                                "Please provide a valid output path and select a supported export format (parquet or hdf5)",
                                QMessageBox.Icon.Critical)
            self.exportCfgWidget.ui.pathLineEdit.clear()
            self.indicate_ready()
            return

        table, errors = self.sigCfgWidget.model.export_information()
        self.indicate_busy('Exporting canvas information...')

        if table.empty:
            error_details = "\n".join(f"- {e}" for e in errors)
            logger.warning("Export failed: no data available to export")
            self.show_popup_msg("Export failed: no data available to export",
                                f"No data could be exported due to:\n{error_details}",
                                QMessageBox.Icon.Critical)
            self.exportCfgWidget.ui.pathLineEdit.clear()
            self.indicate_ready()
            return

        from iplotDataAccess.dataHandling.exportData.exportData import generateData, connectUDA

        gen_kwargs = {}
        if _accepts_kwarg(generateData, 'progressCallback'):
            pulse_factor = len(pulse_number) if pulse_number else 1
            total_vars = sum(len(group) * pulse_factor for ds_name, group in table.groupby('DS')
                             if getattr(self.da.ds_list.get(ds_name), 'source_type', None) == "CODAC_UDA")
            export_index = 0

            def report_progress(name):
                nonlocal export_index
                export_index += 1
                self._report_export_progress(export_index, total_vars, name)

            gen_kwargs['progressCallback'] = report_progress
            self._begin_export_progress()

        # Relative time only applies to time-range exports; pulse exports
        # keep absolute timestamps.
        if data.get('relative_time') and pulse_number is None:
            if _accepts_kwarg(generateData, 'relativeTime'):
                gen_kwargs['relativeTime'] = True
            else:
                logger.warning("Relative time export requires a newer iplotDataAccess; "
                               "exporting absolute timestamps instead")

        # Resampling applies to time-range and pulse exports alike.
        if data.get('resample_freq'):
            if _accepts_kwarg(generateData, 'resampleFreq'):
                gen_kwargs['resampleFreq'] = data['resample_freq']
            else:
                logger.warning("Resampling on export requires a newer iplotDataAccess; "
                               "exporting the original samples instead")

        attempt_count = 0
        success_count = 0
        for ds_name, group in table.groupby('DS'):
            filename = f"{ds_name}.csv"
            export_group = group[['Variable', 'Comment']]
            export_group.to_csv(filename, index=False, sep=',', header=False)
            conn = self.da.ds_list[ds_name]

            if conn.source_type != "CODAC_UDA":
                msg = f"The data source: '{ds_name}' is invalid. Only CODAC UDA data sources can be exported"
                errors.append(msg)
                logger.warning(msg)
                continue

            # When configured, export pulls the data from an alternative UDA server (same port).
            if conn.uda_for_export:
                export_conn = connectUDA(conn.uda_for_export, conn.port)
                if export_conn.errc != 0:
                    reason = (f"Export failed for data source '{ds_name}': "
                              f"could not connect to export server '{conn.uda_for_export}'")
                    logger.warning(reason)
                    errors.append(reason)
                    continue
            else:
                export_conn = conn

            # Pulse mode
            if pulse_number is not None:
                for pulse in pulse_number:
                    result = conn.get_pulse_info(pulse)
                    ts_str = f"{result.timeFrom}"
                    te_str = f"{result.timeTo}"
                    ts_iso = pd.to_datetime(result.timeFrom).isoformat()
                    ts_iso = ts_iso.replace(':', '-')

                    original_path = Path(output_path)
                    valid_name = f"{ds_name}_{ts_iso}_{original_path.stem}{original_path.suffix}"
                    new_path = original_path.with_name(valid_name)

                    # Use of export data script
                    attempt_count += 1
                    valid, err_msg = generateData(logfile=None, conn=export_conn, csvfile=filename, formatType=export_format,
                                                  startTime=ts_str, endTime=te_str, outputFolder=new_path, chunkS=chunks,
                                                  **gen_kwargs)
                    if valid:
                        success_count += 1
                        logger.info(f"Export successful for data source: {ds_name} (format: {export_format} | Path: {new_path}")
                    else:
                        reason = f"Export failed for data source '{ds_name}' (pulse {pulse}): {err_msg}"
                        logger.warning(reason)
                        errors.append(reason)
            else:
                ts_str = f"{ts}"
                te_str = f"{te}"

                original_path = Path(output_path)
                valid_name = f"{ds_name}_{original_path.stem}{original_path.suffix}"
                new_path = original_path.with_name(valid_name)

                # Use of export data script
                attempt_count += 1
                valid, err_msg = generateData(logfile=None, conn=export_conn, csvfile=filename, formatType=export_format,
                                              startTime=ts_str, endTime=te_str, outputFolder=new_path, chunkS=chunks,
                                              **gen_kwargs)
                if valid:
                    success_count += 1
                    logger.info(f"Export successful for data source: {ds_name} (format: {export_format} | Path: {new_path}")
                else:
                    reason = f"Export failed for data source '{ds_name}': {err_msg}"
                    logger.warning(reason)
                    errors.append(reason)

        if gen_kwargs and success_count:
            self._finish_export_progress()

        if attempt_count > 0 and success_count == 0:
            error_details = "\n".join(f"- {e}" for e in errors)
            logger.error("Export failed:\n%s", error_details)
            self.show_popup_msg("Export failed",
                                f"No data was exported. Reasons:\n{error_details}",
                                QMessageBox.Icon.Critical)
        elif errors:
            error_details = "\n".join(f"- {e}" for e in errors)
            logger.warning("Export completed with issues:\n%s", error_details)
            self.show_popup_msg("Export completed with issues",
                                f"{success_count} of {attempt_count} export(s) completed. "
                                f"Some issues were reported:\n{error_details}",
                                QMessageBox.Icon.Warning)
        else:
            self.show_popup_msg("Export completed",
                                "The data export process finished successfully", QMessageBox.Icon.Information)
        self.exportCfgWidget.ui.pathLineEdit.clear()
        self.indicate_ready()

    def closeEvent(self, event: QCloseEvent) -> None:
        # Stop streaming workers before teardown: unlike daemon threads,
        # QThreads must not be destroyed while still running.
        if self.streamerCfgWidget.is_activated():
            self.streamerCfgWidget.streamer.stop()
        QApplication.closeAllWindows()
        super().closeEvent(event)

    def build(self, stream=False) -> bool:
        """Build the canvas from the variables table; False if the application quit while reading data."""
        build = self._begin_build(stream)
        if build.valid:
            for waypt, signal in self._read_in_batches(self.sigCfgWidget.build(**build.da_params), stream):
                if waypt is None:
                    return False
                self._build_row(build, waypt, signal)
        self._end_build(build)
        return True

    def _begin_build(self, stream: bool) -> _Build:
        """Start a build of the canvas from the variables table (see build())."""
        # Data still read in the background for views of the current canvas would be processed in the
        # parser environment of the new one. Older iplotlib releases read the views in the GUI thread.
        if hasattr(self, 'drop_view_reads'):
            self.drop_view_reads()
        # Clear shared parser environment to ensure a clean rebuild. The parser itself
        # is cleared by set_canvas right before drawing: doing it here would blank the
        # plots for as long as the data fetch below takes (visible on every refresh tick).
        ParserHelper.env.clear()

        # Clear shift tracking so stale state from previous canvas does not
        # interfere with future shift operations (UIDs are regenerated on each build).
        self._init_shift_storage()

        self.canvas.streaming = stream
        stream_window = self.streamerCfgWidget.time_window() * 1000000000

        x_axis_date = (self.dataRangeSelector.is_x_axis_date() and not stream) or stream
        x_axis_follow = stream
        x_axis_window = stream_window if stream else None
        refresh_interval = 0 if stream else self.dataRangeSelector.get_auto_refresh()
        pulse_number = None if stream else self.dataRangeSelector.get_pulse_number()

        if stream and stream_window > 0:
            now = self.dataRangeSelector.get_time_now()
            ts, te = now - stream_window, now
        else:
            ts, te = self.dataRangeSelector.get_time_range()

        # Check dates
        mode = self.dataRangeSelector.accessModes[1 if pulse_number else 0]
        valid = True
        if te != '' and ts != '' and te <= ts:
            valid = False
            mode.set_valid_date(False)
            start = pd.to_datetime(ts) if pulse_number is None else ts
            end = pd.to_datetime(te) if pulse_number is None else te
            logger.warning(f"Chronology error. EndTime: {end} must be later than StartTime: {start}")
            # self.on_table_abort()
        else:
            mode.set_valid_date(True)

        self.canvas.auto_refresh = refresh_interval

        # Get signals in order to preserve markers
        previous_signals = {sig.uid: sig for sig in self.canvasStack.currentWidget().get_signals(self.canvas)}

        # Clear alias list to check for fetches row
        self.sigCfgWidget.model._alias_list.clear()
        self.sigCfgWidget.model._alias_checked = False

        return _Build(stream=stream, valid=valid, ts=ts, te=te,
                      da_params=dict(ts_start=ts, ts_end=te, pulse_nb=pulse_number), x_axis_date=x_axis_date,
                      x_axis_follow=x_axis_follow, x_axis_window=x_axis_window, previous_signals=previous_signals)

    def _build_row(self, build: _Build, waypt, signal):
        """Read the data of the signal of a waypoint of the table, show the status of its row and add the signal to
        the plan of the canvas (see build())."""
        row_idx = _row_index(build.rows, waypt)
        if not waypt.stack_num or (not waypt.col_num and not waypt.row_num):
            if not build.stream:
                self._update_row(row_idx, signal)
            return

        if not signal.label:
            return

        signal.data_access_enabled = False if self.canvas.streaming else True
        signal.hi_precision_data = True if self.canvas.streaming else False
        if not build.stream:
            self._update_row(row_idx, signal)
        else:
            # Streaming supports plain variables, y/z expressions and
            # single-child expressions; the time axis must stay native.
            conditions = (
                build.ts != signal.ts_start,
                build.te != signal.ts_end,
                signal.x_expr != '${self}.time',
                len(signal.children) > 1  # Only support one level processing
            )
            if any(conditions):
                signal.stream_valid = False

        if signal.status_info.result == 'Fail':
            return

        # Preserve markers
        prev_signal = build.previous_signals.get(signal.uid)
        if isinstance(signal, SignalXY) and prev_signal and prev_signal.markers_list:
            signal.markers_list = prev_signal.markers_list

        plan = build.plan
        if waypt.col_num not in plan:
            plan[waypt.col_num] = {}

        if waypt.row_num not in plan[waypt.col_num]:
            plan[waypt.col_num][waypt.row_num] = {"row_span": waypt.row_span, "col_span": waypt.col_span,
                                                  "signals": defaultdict(list),
                                                  "ts_start": waypt.ts_start,
                                                  "ts_end": waypt.ts_end,
                                                  "x_axis_date": build.x_axis_date,
                                                  "x_axis_follow": build.x_axis_follow,
                                                  "x_axis_window": build.x_axis_window,
                                                  "streaming": self.canvas.streaming
                                                  }

        else:
            existing = plan[waypt.col_num][waypt.row_num]
            existing["row_span"] = waypt.row_span if waypt.row_span > existing["row_span"] else existing[
                "row_span"]
            existing["col_span"] = waypt.col_span if waypt.col_span > existing["col_span"] else existing[
                "col_span"]
            if waypt.ts_start is not None:
                if existing["ts_start"] is None or waypt.ts_start < existing["ts_start"]:
                    existing["ts_start"] = waypt.ts_start
            if waypt.ts_end is not None:
                if existing["ts_end"] is None or waypt.ts_end > existing["ts_end"]:
                    existing["ts_end"] = waypt.ts_end

        plan[waypt.col_num][waypt.row_num]["signals"][waypt.stack_num].append(signal)
        # Set end time to avoid None values for EndTime in case of pulses
        if plan[waypt.col_num][waypt.row_num]["ts_end"] is None:
            plan[waypt.col_num][waypt.row_num]["ts_end"] = signal.data_xrange[1]

    def _update_row(self, row_idx: typing.Optional[int], signal):
        if row_idx is None:
            # Its row is gone from the table: the signal is read all the same, for its plot.
            signal.get_data()
        else:
            self.sigCfgWidget.model.update_signal_data(row_idx, signal, True)

    def _end_build(self, build: _Build):
        """Build the canvas from the plan of the rows (see build())."""
        self.indicate_busy('Retrieving data...')

        self._clean_sliders()

        # Keep copy of previous canvas to be able to restore preferences
        old_canvas = self.canvas.to_dict()

        self.build_canvas(self.canvas, build.plan, build.x_axis_date, build.x_axis_follow, build.x_axis_window)

        self.indicate_busy('Applying preferences...')
        # Merge with previous preferences
        self.canvas.merge(old_canvas)

        logger.info("Built canvas")
        logger.debug(f"{self.canvas}")
        self.indicate_ready()

    def _clean_sliders(self):
        # For Plots with Slider, slider callback connections are not preserved after deepcopy. Therefore, we must clear
        # the slider references from the old canvas before rebuilding it. This prevents issues related to invalid
        # callback references during redrawing.
        for col in self.canvas.plots:
            for plot in col:
                if isinstance(plot, PlotXYWithSlider) or isinstance(plot, PlotContourWithSlider):
                    plot.clean_slider()

    def build_canvas(self, canvas: Canvas, plan: dict, x_axis_date=False, x_axis_follow=False, x_axis_window=None):
        self._lay_out({(col, row): (entry["row_span"], entry["col_span"])
                       for col, rows in plan.items() for row, entry in rows.items()},
                      lambda col, row: self._plot_of(plan[col][row], col, row, x_axis_date, x_axis_follow,
                                                     x_axis_window))

    def _lay_out(self, places: dict, plot_at: typing.Callable):
        """Lay the canvas out on the places of its plots, by (column, row) from 1 with their (row span, col span), and
        fill each with plot_at(column, row): a plot, or None. No place leaves the canvas with no plot."""
        canvas = self.canvas
        if not places:
            canvas.plots = [[]]
            return
        max_col = 0
        max_row = 0
        for (col, row), (row_span, col_span) in places.items():
            max_col = max(max_col, col + col_span - 1)
            max_row = max(max_row, row + row_span - 1)

        canvas.cols = max_col
        canvas.rows = max_row
        canvas.plots = [[] for _ in range(canvas.cols)]

        rows_of = defaultdict(set)
        for col, row in places:
            rows_of[col].add(row)
        for col, rows in rows_of.items():
            for row in range(1, max(rows) + 1):
                self.canvas.add_plot(plot_at(col, row) if row in rows else None, col=col - 1)

    def _plot_of(self, entry: dict, col: int, row: int, x_axis_date=False, x_axis_follow=False,
                 x_axis_window=None) -> typing.Optional[Plot]:
        """The plot of a place of the plan (see build_canvas()), None if it cannot be drawn."""
        canvas = self.canvas
        plot_types = list(set(signal.plot_type for signals in entry["signals"].values() for signal in signals))
        if len(plot_types) > 1 or any(value not in self.plot_classes.keys() for value in plot_types):
            return None

        x_axis_transformed = False
        for signals in entry["signals"].values():
            for signal in signals:
                if signal.x_expr != '${self}.time':
                    x_axis_transformed = True
                    break

        if not canvas.streaming:
            signal_x_is_date = False
            has_date = False
            has_non_date = False
            for stack, signals in entry["signals"].items():
                for signal in signals:
                    try:
                        x_data = signal.get_data()[0]
                        if len(x_data) > 0:
                            sig_is_date = bool(min(x_data) > (1 << 53) and max(x_data) < (1 << 62))
                            signal_x_is_date |= sig_is_date
                            if sig_is_date:
                                has_date = True
                            else:
                                has_non_date = True
                        elif not x_axis_transformed and entry["ts_start"] is not None:
                            signal_x_is_date |= bool(
                                entry["ts_start"] > (1 << 53) and entry["ts_end"] < (1 << 62))
                    except (IndexError, ValueError) as _:
                        signal_x_is_date = False
            mixed_time_bases = has_date and has_non_date
        else:
            signal_x_is_date = True
            mixed_time_bases = False

        y_axes = [LinearAxis() for _ in range(len(entry["signals"].items()))]

        x_axis = LinearAxis(is_date=x_axis_date and signal_x_is_date, follow=x_axis_follow,
                            window=x_axis_window)

        # In case of processed signals, the limits are not set until the drawn_fn occurs
        # In the other hand, for no processed signals and for pulses the limits are set as follows:
        if not x_axis_transformed:
            x_axis.original_begin = entry["ts_start"]
            x_axis.original_end = entry["ts_end"]
            x_axis.begin = entry["ts_start"]
            x_axis.end = entry["ts_end"]

        if mixed_time_bases:
            logger.warning(f"Plot at row {row}, col {col} contains signals with mixed time bases "
                           f"(absolute and relative timestamps). Signals will not be drawn.")
            return None
        plot = self.plot_classes[plot_types[0]](axes=[x_axis, y_axes], row_span=entry["row_span"],
                                                col_span=entry["col_span"], row=row, col=col)
        for stack, signals in entry["signals"].items():
            for signal in signals:
                if signal.stream_valid:
                    plot.add_signal(signal, stack=stack)

        # In case of streaming, when the plot does not contain any signals that can be streamed, the plot
        # is not added to the Canvas and None is added instead.
        if canvas.streaming and not plot.signals:
            return None
        return plot

    @_ready_at_the_end
    def on_timeout(self):
        # A tick can come while the previous build still waits for its data.
        if self._reading_ahead or self._drawing is not None or not self.build():
            return
        self.indicate_busy("Drawing...")

        self.canvasStack.currentWidget().unfocus_plot()
        self.canvasStack.currentWidget().set_canvas(self.canvas)
        self.canvasStack.refreshLinks()
        self.prefWindow.formsStack.currentWidget().widgetMapper.revert()
        self.prefWindow.update()
        self.canvasStack.currentWidget().stats(self.canvas)
        # The history acts on the canvas just replaced: undoing a shift would draw
        # its old signal again and leave the new one shifted.
        self.drop_history()

        self.indicate_ready()

    def on_drop_plot(self, drop_info):
        dragged_item = drop_info.dragged_item
        row = drop_info.row
        col = drop_info.col
        new_data = pd.DataFrame([['codacuda', f"{dragged_item.key}", f'{col}.{row}']],
                                columns=['DS', 'Variable', 'Stack'])
        self.sigCfgWidget.append_dataframe(new_data)
        self.draw_clicked()

    def show_popup_msg(self, title: str, message: str, icon: QMessageBox.Icon):
        box = QMessageBox()
        box.setIcon(icon)
        box.setWindowTitle(title)

        entry = ErrorCatalog.instance().match(message)
        if entry:
            box.setText(entry['title'])
            box.setInformativeText(ErrorCatalog.format_for_popup(entry))
            box.setDetailedText(message)
            learn_btn = box.addButton("Learn more", QMessageBox.ButtonRole.HelpRole)
            box.addButton(QMessageBox.StandardButton.Ok)
        else:
            box.setText(message)
            learn_btn = None

        box.exec_()

        if learn_btn is not None and box.clickedButton() is learn_btn:
            self._open_manual(anchor=entry.get('manual_anchor'))

    def _open_manual(self, anchor: str = None):
        from mint.gui.mtHelp import MTHelp
        if not hasattr(self, '_helpDialog') or self._helpDialog is None:
            self._helpDialog = MTHelp(self)
        self._helpDialog.show_at(anchor)
