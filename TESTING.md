# MINT testing guide

## How to run

```bash
QT_QPA_PLATFORM=offscreen python -m pytest mint/tests/
```

Offscreen is required: the main-window builds real Qt widgets and needs a
platform plugin. All tests are self-contained (no UDA, no IMAS, no network).

## Coverage

`pytest-cov` is wired into `pyproject.toml`, so every run prints a
per-module coverage summary to the terminal and writes `coverage.xml`
to the repo root. CI uploads the XML as an artifact (`coverage-xml`)
on every workflow run. Nothing extra needs to be installed — `pip install
".[test]"` pulls `pytest-cov` as part of the test extra.

## Layout

```
mint/tests/
  fixtures.py                 # CSV data source config writer
  qAppSingleton.py            # Shared QApplication + font registration
  imageCompare.py             # Figure/pixmap vs baseline diff helpers
  csv/ITER/MCTB-TEST/         # CSV fixture data (pulse 111)
  baseline/                   # Committed reference PNGs
  test_01_mt_create_signals.py
  test_02_main_window_smoke.py
  test_03_signals_model.py
  test_04_calibrated_params.py
  test_05_workspace_roundtrip.py
  test_06_workspace_rendering.py
```

## What each test covers

| File | Behaviour pinned |
|------|------------------|
| `test_01_mt_create_signals` | Signals created from a table via `AccessHelper` |
| `test_02_main_window_smoke` | Main window + widgets boot offscreen (both backends) |
| `test_03_signals_model` | `append_dataframe` / `insertRows` / `set_dataframe` defaults |
| `test_04_calibrated_params` | `retType=doubleCalibrated` emitted only for CODAC + calibrated |
| `test_05_workspace_roundtrip` | `export_dict` → `import_dict` preserves the signals table; legacy `variables_table` key accepted |
| `test_06_workspace_rendering` | End-to-end: populate table, draw, diff rendered figure vs baseline |

## Shared helpers

- **`ensure_qapp()`** — returns the process-wide `QApplication`. Qt only allows
  one per process; every test file that builds widgets must go through this
  helper. It also registers DejaVu Sans from the matplotlib bundle so the
  offscreen platform plugin has a real font to measure text with (fallback
  fonts on Windows/CI produce unstable glyph metrics).
- **`write_csv_datasource_config()`** — writes a temp JSON config pointing at
  the committed CSV tree and sets `IPLOT_SOURCES_CONFIG`. Call once per test
  class in `setUpClass`.
- **`compare_figure_to_baseline(figure, path)`** — render a matplotlib Figure
  at a fixed `figsize`/`dpi` and diff against a committed PNG. Deterministic
  because it bypasses Qt layout.
- **`compare_pixmap_to_baseline(pixmap, path)`** — same idea for a Qt pixmap
  (used for pyqtgraph). Less deterministic than figure rendering; Linux-only.

If the baseline file is missing on first run, the helper bootstraps it. Review
the image before committing.

## Backends, platforms and baselines

Visual tests run on both backends with the same test code. The matplotlib
backend produces deterministic PNGs across OSes when rendered via
`figure.savefig`, so its baseline is cross-platform.

Pyqtgraph renders through Qt, which cannot match matplotlib's Agg backend
for cross-platform determinism: Qt's painter depends on system freetype
and fontconfig, so the same scene renders a couple of pixels differently
on CODAC (RHEL) vs GitHub Actions (ubuntu-latest). To keep the pyqt
visual check useful rather than skipped, the helper:

- Exports the scene via `pg.exporters.ImageExporter` at a fixed width
  (not `QWidget.grab()`, which is even less stable).
- Pins a scene rect so the output size is deterministic.
- Disables pyqtgraph antialiasing to reduce drift sources.
- Rescales the actual image to the baseline size when they drift by
  <2% per dimension, so matplotlib's strict size check does not fail
  on sub-pixel font differences.
- Uses a generous RMS tolerance that catches real regressions
  (missing plots, wrong data, wrong legends) but tolerates font drift.

Pyqt visual tests are still skipped on non-Linux because the drift there
is much larger. Regenerate pyqt baselines on Linux (CODAC or CI).

## Adding a new rendering test

1. Build the main window with `_build_main_window(impl)`.
2. Populate the signals model via `win.sigCfgWidget.model.set_dataframe(df)`.
3. Configure the time range via `win.dataRangeSelector.import_dict({...})` so
   the radio button, stacked widget and mapper all end up consistent.
4. Call `win.draw_clicked()` followed by `self.app.processEvents()`.
5. Diff the figure (matplotlib) or pixmap (pyqt) against the baseline.
6. Always `win.close()` in a `finally`.
