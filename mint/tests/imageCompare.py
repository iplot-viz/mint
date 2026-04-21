"""Image comparison helper for MINT visual regression tests.

Uses matplotlib's bundled image comparator to diff a rendered pixmap
against a committed baseline PNG. First run bootstraps the baseline.

TODO: once iplotlib issue #34 lands on develop and a new iplotlib
release is cut, migrate to ``from iplotlib.qt.testing import
compare_pixmap_to_baseline`` and remove this copy.
"""

import os
import shutil

from matplotlib.testing.compare import compare_images


def _compare_or_bootstrap(actual_path: str, baseline_path: str, tol: float) -> None:
    if not os.path.exists(baseline_path):
        shutil.copyfile(actual_path, baseline_path)
        return
    diff = compare_images(baseline_path, actual_path, tol=tol)
    if diff is not None:
        raise AssertionError(
            f"Image mismatch vs baseline {os.path.basename(baseline_path)}: {diff}")


def compare_pixmap_to_baseline(pixmap, baseline_path: str, tol: float = 5.0) -> None:
    actual_path = baseline_path.replace('.png', '_actual.png')
    pixmap.save(actual_path, 'PNG')
    assert os.path.exists(actual_path), f"pixmap.save produced no file: {actual_path}"
    try:
        _compare_or_bootstrap(actual_path, baseline_path, tol)
    finally:
        if os.path.exists(actual_path):
            try:
                os.remove(actual_path)
            except OSError:
                pass


def compare_figure_to_baseline(figure, baseline_path: str, tol: float = 5.0,
                               figsize=(10, 7), dpi: int = 100) -> None:
    """Render a matplotlib Figure to PNG at a fixed size/DPI and diff it.

    Bypasses Qt layout entirely, so the output is deterministic regardless
    of whether the test runs alone or alongside others that leave widgets in
    unusual states.
    """
    actual_path = baseline_path.replace('.png', '_actual.png')
    figure.set_size_inches(*figsize)
    figure.savefig(actual_path, dpi=dpi)
    try:
        _compare_or_bootstrap(actual_path, baseline_path, tol)
    finally:
        if os.path.exists(actual_path):
            try:
                os.remove(actual_path)
            except OSError:
                pass


def compare_pyqtgraph_scene_to_baseline(scene, baseline_path: str,
                                        tol: float = 5.0,
                                        width: int = 1000) -> None:
    """Export a pyqtgraph scene to PNG via ImageExporter at a fixed width.

    Sidesteps QWidget.grab(), which relies on Qt's native painter pipeline
    and drifts between Linux distros. ImageExporter renders the scene to
    a QImage of a fixed width/height with pyqtgraph's own painter path,
    giving a more reproducible output across environments.
    """
    import pyqtgraph.exporters  # noqa: F401 — registers exporter
    import pyqtgraph as pg

    actual_path = baseline_path.replace('.png', '_actual.png')
    exporter = pg.exporters.ImageExporter(scene)
    exporter.parameters()['width'] = width
    exporter.export(actual_path)
    try:
        _compare_or_bootstrap(actual_path, baseline_path, tol)
    finally:
        if os.path.exists(actual_path):
            try:
                os.remove(actual_path)
            except OSError:
                pass
