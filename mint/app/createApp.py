# Description: The MINT application attributes and arguments can be configured here.
# Author: Jaswant Sai Panchumarti

from PySide6.QtWidgets import QApplication

from argparse import ArgumentParser, Namespace
from iplotlib.core.display import apply_hidpi_policy
from mint._version import get_versions


def create_app(argv=None) -> (QApplication, Namespace):
    if argv is None:
        argv = []
    parser = ArgumentParser(description='MINT application')
    parser.add_argument('--impl', metavar='canvas_impl',
                        help='Use canvas implementation (matplotlib/pyqt)', choices=['matplotlib', 'pyqt'],
                        default="matplotlib")
    parser.add_argument('--use-fallback-samples', dest='use_fallback_samples', action='store_true', default=False)
    parser.add_argument('-b', dest='blueprint_file', metavar='blueprint_file',
                        help='Load blueprint from .json file', default=None)
    parser.add_argument('-d', dest='scsv_file', metavar='scsv_file',
                        help='Load variables table from file')
    parser.add_argument('--ld', dest='last_dump', action='store_true', default=False,
                        help='Load variables table from last dump file')
    parser.add_argument('-w', dest='json_file', metavar='json_file',
                        help='Load a workspace from json file')
    parser.add_argument('-e', dest='image_file', metavar='image_file',
                        help='Load canvas from JSON and save to file (PNG/SVG/PDF...)')
    parser.add_argument('--ew', dest='export_width', metavar='export_width',
                        type=int, default=1920, help='Exported image width')
    parser.add_argument('--eh', dest='export_height', metavar='export_height',
                        type=int, default=1080, help='Exported image height')
    parser.add_argument('--ed', dest='export_dpi', metavar='export_dpi',
                        type=int, default=100, help='Exported image DPI')
    parser.add_argument('--ea', '--export-autoscale', dest='export_autoscale', action='store_true', default=False,
                        help='Force an "Autoscale All" on the Y axes of the exported image '
                             '(instead of keeping the Y limits saved in the workspace). '
                             'Only used together with -e; has no effect otherwise.')
    parser.add_argument('--ui-scale', dest='ui_scale', metavar='ui_scale', default=None,
                        help='UI scale: auto, off, or a factor such as 1.5. Overrides the '
                             'persisted Appearance setting for this run; IPLOT_UI_SCALE '
                             'overrides both.')
    parser.add_argument('--display-info', dest='display_info', action='store_true', default=False,
                        help='Print the detected screen metrics and the resolved UI scale, '
                             'then exit. Use this when reporting a rendering problem.')
    parser.add_argument('--version', action='version',
                        version=f"{parser.prog} - {get_versions()['version']}")
    args = parser.parse_args()

    # The high-DPI scale factor rounding policy has no effect once the
    # QApplication exists, so it has to be set here rather than in entryPoint.
    apply_hidpi_policy()

    qApp = QApplication(argv)
    qApp.setApplicationName("MINT")
    qApp.setApplicationVersion(get_versions()['version'])
    qApp.setOrganizationDomain("www.iter.org")
    qApp.setOrganizationName("ITER")

    # must come after the organization/application names are set: QSettings depends on them
    from mint.gui.mtAppearance import apply_ui_scale, restore_appearance
    restore_appearance()
    if args.ui_scale is not None:
        # A command-line factor applies to this run only and is not persisted.
        apply_ui_scale(args.ui_scale, persist=False)

    return qApp, args
