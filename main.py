import argparse
from datetime import datetime, timedelta
import json
import os
import pandas
import sys

from qtpy.QtWidgets import QApplication, QLabel, QStyle

from iplotlib.core._version import __version__ as __iplotlib_version__
from iplotlib.core.canvas import Canvas
from iplotlib.data_access.dataAccessSignal import AccessHelper
from iplotDataAccess.dataAccess import DataAccess
from iplotProcessing.core import Context

from gui._version import __version__
from gui.dataRanges.dataRange import DataRange
from gui.mainWindow import MainWindow

import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)


def export_to_file(impl: str, canvas: Canvas, output_filename, **kwargs):
    try:
        if impl.lower() == "matplotlib":
            import matplotlib
            matplotlib.rcParams["figure.dpi"] = kwargs.get('dpi')
            from iplotlib.impl.matplotlib.matplotlibCanvas import MatplotlibCanvas
            
            mpl_canvas = MatplotlibCanvas()
            mpl_canvas.export_image(output_filename, canvas=canvas, **kwargs)
        elif impl.lower() == "vtk":
            canvas.export_image(output_filename, **kwargs)
    except FileNotFoundError:
        logger.error(f"Unable to open file: {output_filename}")


if __name__ == '__main__':

    logger.info("Running version {} iplotlib version {}".format(
        __version__, __iplotlib_version__))

    #########################################################################
    # 1. Parse arguments
    parser = argparse.ArgumentParser(description='MINT application')
    parser.add_argument('-IMPL', metavar='CANVAS_IMPL', help='Use canvas implementation (MATPLOTLIB/GNUPOLOT/VTK/...)', default="MATPLOTLIB")
    parser.add_argument('-d', dest='csv_file', metavar='csv_file', help='Load variables table from file')
    parser.add_argument('-w', dest='json_file', metavar='json_file', help='Load a workspace from json file')
    parser.add_argument('-e', dest='image_file', metavar='image_file', help='Load canvas from JSON and save to file (PNG/SVG/PDF...)')
    parser.add_argument('-ew', dest='export_width', metavar='export_width', type=int, default=1920, help='Exported image width')
    parser.add_argument('-eh', dest='export_height', metavar='export_height', type=int, default=1080, help='Exported image height')
    parser.add_argument('-ed', dest='export_dpi', metavar='export_dpi', type=int, default=100, help='Exported image DPI')

    args = parser.parse_args()

    #########################################################################
    # 2. Data access handle
    da = DataAccess()
    AccessHelper.da = da
    if len(da.loadConfig()) < 1:
        logger.error("no data sources found, exiting")
        sys.exit(-1)

    # da.udahost = os.environ.get('UDA_HOST') or "io-ls-udafe01.iter.org"
    canvasImpl = args.IMPL

    var_table_file = args.csv_file
    workspace_file = args.json_file
    #########################################################################
    # 3. Processing context
    ctx = Context()
    AccessHelper.ctx = ctx

    #########################################################################
    # 4. Plot canvas
    canvas = Canvas(grid=True)

    # This is a main reference to canvas that is drawn
    if workspace_file:
        with open(workspace_file) as f:
            payload = json.loads(f.read())
            if payload.get("main_canvas"):
                json_str = json.dumps(payload.get("main_canvas"))
                canvas = Canvas.from_json(json_str)
            else:
                logger.error(f"Failed to load main_canvas from {workspace_file}")
    else:
        canvas = Canvas(grid=True)

    if args.image_file:
        export_to_file(canvasImpl, canvas, args.image_file, dpi=args.export_dpi, width=args.export_width, height=args.export_height)
        exit(0)

    #########################################################################
    # 5. Prepare model and header for variables table
    tNow = datetime.utcnow().isoformat(timespec='seconds')
    tNowDeltaSevenD = datetime.utcnow() - timedelta(days=7)

    model = {
        "range": {
            "mode": DataRange.TIME_RANGE,
            "value": [tNowDeltaSevenD.isoformat(timespec='seconds'), tNow]}
    }

    header = {
        "DataSource": {"label": "DS"},
        "Variable": {},
        "Stack": {},
        "RowSpan": {"label": "Row span"},
        "ColSpan": {"label": "Col span"},
        "Envelope": {},
        "Alias": {},
        "x": {},
        "y": {},
        "z": {},
        "DecSamples": {"label": "Samples"},
        "PulseNumber": {},
        "StartTime": {},
        "EndTime": {}
    }

    # Preload the table from a CSV file, if provided
    if args.csv_file:
        model["table"] = pandas.read_csv(
            args.csv_file, dtype=str, keep_default_na=False).values.tolist()

    app = QApplication(sys.argv)
    mainWin = MainWindow(canvas, ctx, da, header, model, impl=args.IMPL)

    if workspace_file:
        with open(workspace_file) as json_file:
            payload = json.loads(json_file.read())
            if payload.get("variables_table"):
                json_str = json.dumps(payload.get("variables_table"))
                mainWin.variables_table.import_json(json_str)
            if payload.get("range_selector"):
                json_str = json.dumps(payload.get("range_selector"))
                mainWin.range_selector.import_json(json_str)

    mainWin.status_bar.addPermanentWidget(
        QLabel("Tool version {} iplotlib {}".format(__version__, __iplotlib_version__)))

    mainWin.setWindowTitle("MINT: {}".format(os.getpid()))
    mainWin.show()
    app.setWindowIcon(mainWin.style().standardIcon(
        getattr(QStyle, "SP_BrowserReload")))
    sys.exit(app.exec_())
