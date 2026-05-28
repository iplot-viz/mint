"""Shared fixtures and helpers for MINT integration tests."""

import atexit
import json
import os
import tempfile

ROOT = os.path.dirname(__file__)
CSV_DIR = os.path.join(ROOT, 'csv', 'ITER')
WORKSPACES_DIR = os.path.join(ROOT, 'workspaces')
BASELINE_DIR = os.path.join(ROOT, 'baseline')


def _unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def write_csv_datasource_config() -> str:
    """Write a temporary IPLOT_SOURCES_CONFIG pointing at the CSV fixture.

    Returns the absolute path to the generated cfg. The file is written to
    a system temp location so concurrent pytest workers do not collide,
    and unlinked at interpreter exit so repeated test runs do not leak.
    """
    # Forward slashes for JSON on all platforms.
    csv_path = CSV_DIR.replace('\\', '/')
    cfg = {
        "csv": {
            "path": csv_path,
            "type": "CSV",
        }
    }
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.cfg', delete=False, encoding='utf-8')
    json.dump(cfg, tmp)
    tmp.close()
    os.environ['IPLOT_SOURCES_CONFIG'] = tmp.name
    atexit.register(_unlink_quiet, tmp.name)
    return tmp.name
