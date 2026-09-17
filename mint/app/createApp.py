# Description: The MINT application attributes and arguments can be configured here.
# Author: Jaswant Sai Panchumarti

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import os
from argparse import ArgumentParser, Namespace
from iplotlib.core.display import apply_hidpi_policy
from mint._version import get_versions


CANVAS_IMPLS = ('matplotlib', 'pyqt')


def default_canvas_impl() -> str:
    """Canvas implementation used without --impl: MINT_IMPL when it names one, matplotlib otherwise."""
    value = os.environ.get('MINT_IMPL', '').strip().lower()
    return value if value in CANVAS_IMPLS else 'matplotlib'


def create_app(argv=None) -> (QApplication, Namespace):
    if argv is None:
        argv = []
    parser = ArgumentParser(description='MINT application')
    parser.add_argument('--impl', metavar='canvas_impl',
                        help='Use canvas implementation (matplotlib/pyqt); MINT_IMPL sets the default',
                        choices=list(CANVAS_IMPLS), default=default_canvas_impl())
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

    # Both of these are read once, when the QApplication is constructed, so
    # they have to be set here rather than in entryPoint.
    apply_hidpi_policy()
    _export_qt_scale_factor(args)

    qApp = QApplication(argv)
    qApp.setApplicationName("MINT")
    qApp.setApplicationVersion(get_versions()['version'])
    qApp.setOrganizationDomain("www.iter.org")
    qApp.setOrganizationName("ITER")

    # must come after the organization/application names are set: QSettings depends on them
    from mint.gui.mtAppearance import (apply_ui_scale, remember_detected_qt_scale,
                                       restore_appearance)
    restore_appearance()
    if args.ui_scale is not None:
        # A command-line factor applies to this run only and is not persisted.
        apply_ui_scale(args.ui_scale, persist=False)
    else:
        # The screen can only be queried now that the QApplication exists, so a
        # newly detected factor takes effect at the next start.
        qApp.pending_ui_scale = remember_detected_qt_scale()

    return qApp, args


def _export_qt_scale_factor(args):
    """Put QT_SCALE_FACTOR in the environment before Qt reads it.

    Qt reads it once, at QGuiApplication construction, and it is the only
    lever that scales fonts, style primitives, icons and spacing together:
    scaling the application font afterwards leaves radio indicators, check
    boxes and scroll bars at their pixel size. Anything already in the
    environment wins, so a launcher script or a site profile stays in control.
    """
    if args.ui_scale is not None:
        from iplotlib.core.display import MODE_FIXED, parse_scale_setting
        mode, value = parse_scale_setting(args.ui_scale)
        if mode == MODE_FIXED and abs(value - 1.0) > 1e-6 and not os.environ.get('QT_SCALE_FACTOR'):
            os.environ['QT_SCALE_FACTOR'] = f"{value:g}"
            return
    # Named explicitly: QSettings() takes the organization and application
    # names from the QApplication, which does not exist yet.
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                         "ITER", "MINT")
    from mint.gui.mtAppearance import startup_qt_scale_factor
    factor = startup_qt_scale_factor(settings)
    if factor:
        os.environ['QT_SCALE_FACTOR'] = factor
