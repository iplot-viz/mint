# Description: The entry point to MINT application.
#              All modules are imported only if runApp is actually called. This removes spurious import warnings
#              when all you run is mint -h to display the usage.
# Author: Jaswant Sai Panchumarti


from datetime import datetime, timedelta
import json
import os
import sys

from PySide6.QtWidgets import QApplication

def runApp(qApp: QApplication, args=None):
    if args is None:
        return

    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QLabel

    from iplotlib.core import Canvas
    from iplotlib.interface.iplotSignalAdapter import AccessHelper, IplotSignalAdapter
    from iplotDataAccess.dataAccess import DataAccess
    from iplotDataAccess.appDataAccess import AppDataAccess
    import iplotLogging.setupLogger as ls

    from mint.app.dirs import DEFAULT_DATA_DIR, DEFAULT_DATA_SOURCES_CFG
    from mint.models import MTGenericAccessMode
    from mint.models.utils import mtBlueprintParser as mtbp
    from mint.gui.mtMainWindow import MTMainWindow
    from mint.tools.icon_loader import create_pxmap

    from importlib import metadata

    #iplotlib_version = metadata.version('iplotlib')
    iplotlib_version = '0.9.0'

    logger = ls.get_logger(__name__)

    def export_to_file(impl: str, canvas: Canvas, canvas_filename, **kwargs):
        try:
            if impl.lower() == "matplotlib":
                import matplotlib
                matplotlib.rcParams["figure.dpi"] = kwargs.get('dpi')
                from iplotlib.impl.matplotlib.matplotlibCanvas import MatplotlibParser

                mpl_canvas = MatplotlibParser()
                mpl_canvas.export_image(
                    canvas_filename, canvas=canvas, **kwargs)
        except FileNotFoundError:
            logger.error(f"Unable to open file: {canvas_filename}")

    logger.info("Running version {} iplotlib version {}".format(
        qApp.applicationVersion(), iplotlib_version))

    if not AppDataAccess.loadConfiguration():
        logger.error("no data sources found, exiting")
        sys.exit(-1)

    AccessHelper.da = AppDataAccess.getDataAccess()
    # da.udahost = os.environ.get('UDA_HOST') or "io-ls-udafe01.iter.org"
    canvasImpl = args.impl

    workspace_file = args.json_file

    #########################################################################
    # 2. Plot canvas
    canvas = Canvas(grid=True)

    #########################################################################
    # 3. Prepare model for data range
    tNow = datetime.utcnow().isoformat(timespec='seconds')
    tNowDeltaSevenD = datetime.utcnow() - timedelta(days=7)

    time_model = {
        "range": {
            "mode": MTGenericAccessMode.TIME_RANGE,
            "value": [tNowDeltaSevenD.isoformat(timespec='seconds'), tNow]}
    }

    if args.blueprint_file:
        try:
            blueprint = json.load(args.blueprint_file)
        except Exception as e:
            logger.warning(
                f"Exception {e} occurred for blueprint file: {args.blueprint_file}")
            blueprint = mtbp.DEFAULT_BLUEPRINT
    else:
        blueprint = mtbp.DEFAULT_BLUEPRINT

    logger.debug(f"Detected {len(QGuiApplication.screens())} screen (s)")
    max_width = 0
    for screen in QGuiApplication.screens():
        max_width = max(screen.geometry().width(), max_width)
    logger.debug(f"Detected max screen width: {max_width}")
    AccessHelper.num_samples = max_width
    AccessHelper.num_samples_override = args.use_fallback_samples
    logger.info(f"Fallback dec_samples : {AccessHelper.num_samples}")

    data_sources = [AccessHelper.da.getDefaultDSName()]
    for ds_name in AccessHelper.da.dslist.keys():
        if ds_name not in data_sources:
            data_sources.append(ds_name)

    mainWin = MTMainWindow(canvas,
                           AccessHelper.da,
                           time_model,
                           appVersion=qApp.applicationVersion(),
                           data_dir=DEFAULT_DATA_DIR,
                           data_sources=data_sources,
                           blueprint=blueprint,
                           impl=canvasImpl,
                           signal_class=IplotSignalAdapter)

    mainWin.setWindowTitle(
        f"{qApp.applicationName()}: {qApp.applicationPid()}")
    mainWin.statusBar().addPermanentWidget(
        QLabel("MINT version {} iplotlib {} |".format(qApp.applicationVersion(), iplotlib_version)))

    # Preload the table from a CSV file, if provided
    if args.csv_file:
        mainWin.sigCfgWidget.import_csv(args.csv_file)

    if workspace_file:
        mainWin.import_json(workspace_file)

        if args.image_file:
            export_to_file(canvasImpl, mainWin.canvas, args.image_file, dpi=args.export_dpi,
                           width=args.export_width, height=args.export_height)
            exit(0)

    mainWin.show()
    appIcon = QIcon()
    for i in range(4, 9):
        sz = 1 << i
        appIcon.addPixmap(create_pxmap(f"mint{sz}x{sz}"))
    qApp.setWindowIcon(appIcon)

    return qApp.exec_()
