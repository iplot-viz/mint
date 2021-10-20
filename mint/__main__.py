# Description: The MINT application to interact and explore data signals from codac databases and IMAS IDSs
# Author: Piotr Mazur
# Changelog:
#  Sept 2021: Refactored ui design classes [Jaswant Sai Panchumarti]

import argparse
from datetime import datetime, timedelta
from importlib import metadata
import json
import os
import sys

from PySide2.QtGui import QGuiApplication
from PySide2.QtWidgets import QApplication, QLabel, QStyle

from iplotlib.core import Canvas
from iplotlib.interface.iplotSignalAdapter import AccessHelper, IplotSignalAdapter
from iplotDataAccess.dataAccess import DataAccess

from mint._version import __version__
from mint.models import MTGenericAccessMode
from mint.models.utils import mtBlueprintParser as mtbp
from mint.gui.mtMainWindow import MTMainWindow

import iplotLogging.setupLogger as ls


logger = ls.get_logger(__name__)
iplotdataaccess_version = metadata.version('iplotDataAccess')
iplotlib_version = metadata.version('iplotlib')
iplotlogging_version = metadata.version('iplotLogging')
iplotprocessing_version = metadata.version('iplotProcessing')

EXEC_PATH = os.path.dirname(__file__)
DEFAULT_DATA_SOURCES_CFG = os.path.join(EXEC_PATH, 'mydatasources.cfg')
DEFAULT_DATA_PATH = os.path.join(EXEC_PATH, 'data')


def export_to_file(impl: str, canvas: Canvas, canvas_filename, **kwargs):
    try:
        if impl.lower() == "matplotlib":
            import matplotlib
            matplotlib.rcParams["figure.dpi"] = kwargs.get('dpi')
            from iplotlib.impl.matplotlib.matplotlibCanvas import MatplotlibCanvas

            mpl_canvas = MatplotlibCanvas()
            mpl_canvas.export_image(canvas_filename, canvas=canvas, **kwargs)
    except FileNotFoundError:
        logger.error(f"Unable to open file: {canvas_filename}")


def load_data_sources(da: DataAccess):
    try:
        if len(da.loadConfig()) < 1:
            return False
        else:
            return True
    except (OSError, IOError, FileNotFoundError) as e:
        logger.warning(
            f"no data source file, fallback to {DEFAULT_DATA_SOURCES_CFG}")
        os.environ.update({'DATASOURCESCONF': DEFAULT_DATA_SOURCES_CFG})
        return load_data_sources(da)


def main():

    #########################################################################
    # 1. Parse arguments
    parser = argparse.ArgumentParser(description='MINT application')
    parser.add_argument('-impl', metavar='canvas_impl',
                        help='Use canvas implementation (matplotlib/vtk...)', default="matplotlib")
    parser.add_argument('-b', dest='blueprint_file', metavar='blueprint_file',
                        help='Load blueprint from .json file', default=None)
    parser.add_argument('-d', dest='csv_file', metavar='csv_file',
                        help='Load variables table from file')
    parser.add_argument('-w', dest='json_file', metavar='json_file',
                        help='Load a workspace from json file')
    parser.add_argument('-e', dest='image_file', metavar='image_file',
                        help='Load canvas from JSON and save to file (PNG/SVG/PDF...)')
    parser.add_argument('-ew', dest='export_width', metavar='export_width',
                        type=int, default=1920, help='Exported image width')
    parser.add_argument('-eh', dest='export_height', metavar='export_height',
                        type=int, default=1080, help='Exported image height')
    parser.add_argument('-ed', dest='export_dpi', metavar='export_dpi',
                        type=int, default=100, help='Exported image DPI')
    parser.add_argument('--version', action='version',
                        version=f"{parser.prog} - {__version__}")

    args = parser.parse_args()

    logger.info("Running version {} iplotlib version {}".format(
        __version__, iplotlib_version))

    #########################################################################
    # 2. Data access handle
    da = DataAccess()
    if not load_data_sources(da):
        logger.error("no data sources found, exiting")
        sys.exit(-1)

    AccessHelper.da = da
    # da.udahost = os.environ.get('UDA_HOST') or "io-ls-udafe01.iter.org"
    canvasImpl = args.impl

    workspace_file = args.json_file

    #########################################################################
    # 4. Plot canvas
    canvas = Canvas(grid=True)

    #########################################################################
    # 5. Prepare model for data range
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

    app = QApplication(sys.argv)

    logger.debug(f"Detected {len(QGuiApplication.screens())} screen (s)")
    max_width = 0
    for screen in QGuiApplication.screens():
        max_width = max(screen.geometry().width(), max_width)
    logger.debug(f"Detected max screen width: {max_width}")
    AccessHelper.num_samples = max_width
    # AccessHelper.num_samples_override = False
    logger.info(f"Fallback dec_samples : {AccessHelper.num_samples}")

    data_sources = [AccessHelper.da.getDefaultDSName()]
    for ds_name in AccessHelper.da.dslist.keys():
        if ds_name not in data_sources:
            data_sources.append(ds_name)

    mainWin = MTMainWindow(canvas,
                           da,
                           time_model,
                           DEFAULT_DATA_PATH,
                           data_sources=data_sources,
                           blueprint=blueprint,
                           impl=canvasImpl,
                           signal_class=IplotSignalAdapter)

    mainWin.statusBar().addPermanentWidget(
        QLabel("Tool version {} iplotlib {}".format(__version__, iplotlib_version)))

    # Preload the table from a CSV file, if provided
    if args.csv_file:
        mainWin.sigCfgWidget.import_csv(args.csv_file)

    if workspace_file:
        mainWin.import_json(workspace_file)

        if args.image_file:
            export_to_file(canvasImpl, mainWin.canvas, args.image_file, dpi=args.export_dpi,
                        width=args.export_width, height=args.export_height)
            exit(0)

    mainWin.setWindowTitle("MINT: {}".format(os.getpid()))
    mainWin.show()
    app.setWindowIcon(mainWin.style().standardIcon(
        getattr(QStyle, "SP_BrowserReload")))

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
