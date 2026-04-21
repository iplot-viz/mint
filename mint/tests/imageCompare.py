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


def _rescale_to_match(actual_path: str, baseline_path: str) -> None:
    """Resize the actual image to the baseline's dimensions if they drift
    by at most a few pixels. pyqtgraph's Qt-based rendering varies by one
    or two pixels per dimension between Linux distros (freetype/fontconfig
    differences), which is too small to matter visually but enough to trip
    matplotlib.compare_images' strict size check. Rescaling within a tight
    tolerance normalises the size without masking real regressions.
    """
    from PIL import Image

    with Image.open(baseline_path) as baseline, Image.open(actual_path) as actual:
        if baseline.size == actual.size:
            return
        bw, bh = baseline.size
        aw, ah = actual.size
        # Only rescale if the drift is under ~2% per dimension; anything
        # bigger is a real change and should fail the size check.
        if abs(bw - aw) / bw > 0.02 or abs(bh - ah) / bh > 0.02:
            return
        resized = actual.resize(baseline.size, Image.LANCZOS)
        resized.save(actual_path)


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
                                        tol: float = 20.0,
                                        width: int = 1000,
                                        height: int = 700) -> None:
    """Export a pyqtgraph scene to PNG via ImageExporter and diff it.

    pyqtgraph renders through Qt, which depends on system freetype and
    fontconfig — two different Linux distros produce images that differ
    by a handful of pixels (sub-pixel font rasterisation, anti-aliasing,
    pen cap rendering). Matplotlib's `compare_images` is strict about
    exact size, so we:

    - Set an explicit scene rect so the output is always width x height.
    - Disable antialiasing at pyqtgraph level to reduce drift sources.
    - Rescale the actual image to the baseline's size when the drift is
      tiny (<2% per dimension) so the RMS diff can still run.
    - Use a generous RMS tolerance (default 20.0) that catches real
      regressions (wrong data, missing plot) but tolerates font drift.

    This is the best we can do without a container that pins Qt/freetype.
    """
    import pyqtgraph.exporters  # noqa: F401 — registers exporter
    import pyqtgraph as pg

    pg.setConfigOptions(antialias=False)
    scene.setSceneRect(0, 0, width, height)

    actual_path = baseline_path.replace('.png', '_actual.png')
    exporter = pg.exporters.ImageExporter(scene)
    exporter.parameters()['width'] = width
    exporter.export(actual_path)
    try:
        if os.path.exists(baseline_path):
            _rescale_to_match(actual_path, baseline_path)
        _compare_or_bootstrap(actual_path, baseline_path, tol)
    finally:
        if os.path.exists(actual_path):
            try:
                os.remove(actual_path)
            except OSError:
                pass
