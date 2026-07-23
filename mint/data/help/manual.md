# MINT - User Manual

*Make Informative and Nice Trends.* Visualization tool for ITER, developed alongside Science Division.

## Table of Contents

- [1. Introduction](#introduction)
- [2. Viewing data](#viewing-data)
    - [2.1 Installation](#installation)
    - [2.2 Logging](#logging)
    - [2.3 Time configuration](#time-configuration)
    - [2.4 Table](#table)
    - [2.5 Draw, Stream](#draw-stream)
    - [2.6 Export/Import workspace](#export-import-workspace)
    - [2.7 Export data](#export-data)
    - [2.8 Plotting area](#plotting-area)
    - [2.9 Expressions](#expressions)
    - [2.10 Data Sources](#data-sources)
- [3. ITER environment](#iter-environment)
- [4. Reference](#reference)
    - [4.1 Keyboard shortcuts](#keyboard-shortcuts)
    - [4.2 Access modes](#access-modes)
    - [4.3 Supported data source types](#datasource-types)
- [5. FAQ](#faq)
- [6. Error reference](#errors)
    - [6.1 Error categories](#error-categories)

## 1. Introduction {#introduction}

### 1.1 Purpose and scope {#purpose-scope}

This is a how-to guide for MINT - Make Informative and Nice Trends, the visualization tool developed alongside Science Division and used in the ITER control room. It retrieves both CODAC and IMAS data and is implemented in Python 3, PySide6, Matplotlib and VTK.

The current version is limited to 1-D traces. More complex plots are planned for upcoming releases.

### 1.2 Definitions {#definitions}

| Term | Meaning |
|------|---------|
| IMAS | Integrated Modelling Application Software |
| UDA  | Unified Data Access |
| CBS  | Control Breakdown Structure |
| Scsv | Semi-colon separated values |

### 1.3 References {#references}

- [RD1] IMAS data dictionary
- [RD2] NumPy
- [RD3] UDA user manual (TPLTGK)
- [RD4] Advanced Exercises (BBNVVH)
- [RD5] Example of user-defined processing
- [RD6] Example of user-defined data source

## 2. Viewing data {#viewing-data}

### 2.1 Installation {#installation}

On a CODAC environment:

```
$ sudo yum install codac-core-$(codac-version -v)-mint codac-core-$(codac-version -v)-uda-client-python3-utils -y
```

On SDCC (no installation required):

```
$ module load MINT
```

To start the tool:

```
$ mint
```

<div class="note">If MINT exits with <em>"no data sources found, exiting"</em>, it could not find a valid UDA or IMAS server. See <a href="#errors-no-data-sources">Error reference - No data sources</a> and <a href="#data-sources">section 2.10</a>.</div>

### 2.2 Logging {#logging}

Log files live under `~/.local/1Dtool/logs/`; the log file is `mint.log`.

Severity is controlled with the `IPLOT_LOG_LEVEL` environment variable, set *before* starting the tool. Allowed values: `DEBUG`, `WARNING`, `CRITICAL`, `ERROR`.

```
$ export IPLOT_LOG_LEVEL=DEBUG
$ mint
```

### 2.3 Time configuration {#time-configuration}

MINT always assumes UTC time, regardless of the host time zone. Timestamps follow ISO 8601.

Data can be queried by:

- Absolute time range (From time / To time, ISO 8601).
- Pulse ID. On CCS, a pulse identifier is a string with location, category and number, e.g. `ITER:CWS-SCSU-BASIN-FILL-TESTS/130125`. On SDCC, IMAS pulses use `pulse/run`, e.g. `135011/7`, or an Access Layer URI such as `imas:hdf5?path=/home/ITER/.../3/105027/32`.
- Relative time range, with an optional refresh interval (minimum 5 minutes).

<p style="text-align:center;margin:14px 0;"><img src="image_01.png" alt="Querying by absolute time range" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 1. Querying by absolute time range.</i></p>
<p style="text-align:center;margin:14px 0;"><img src="image_02.png" alt="Querying by pulse id on CCS" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 2. Querying by pulse id on CCS.</i></p>
<p style="text-align:center;margin:14px 0;"><img src="image_03.png" alt="Querying IMAS data by pulse id on SDCC" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 3. Querying IMAS data by pulse id on SDCC: pulse/run.</i></p>
<p style="text-align:center;margin:14px 0;"><img src="image_04.png" alt="Querying by pulse id on SDCC using URI" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 4. Querying by pulse id on SDCC: using URI.</i></p>
<p style="text-align:center;margin:14px 0;"><img src="image_05.png" alt="Querying by relative time range" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 5. Querying by relative time range.</i></p>

Multiple pulse IDs can be overlaid by separating them with commas. Use the *Search* button next to the Pulse ID field to browse pulses.

### 2.4 Table {#table}

#### 2.4.1 Icons and buttons

The toolbar above the variable table provides import / save / append actions, a *Hide/Show columns* menu, a *Search Vars* button (browse variables per data source), and *Load new module* to register an extra Python module for processing.

<p style="text-align:center;margin:14px 0;"><img src="image_06.png" alt="Icons and buttons above the variable table" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 6. Icons / buttons above the variable table.</i></p>

#### 2.4.2 Columns definition

| Column | Meaning |
|--------|---------|
| DS | Data Source alias. Choose `codacuda` for ITER plant data, `imasuda` for IMAS data. |
| Variable | Variable name. For IMAS, full structure with `[]` for arrays, e.g. `summary/heating_current_drive/ec[0]/power/value`. |
| Stack | Up to three dot-separated digits: row, column, optional stack id. Numbering starts at 1. Stack id defaults to 1; signals sharing a stack share the X axis. |
| Row span | Rows the plot occupies (default 1). |
| Col span | Columns the plot occupies (default 1). |
| Envelope | Empty disables envelope. Set to 1 to compute min/max/avg envelope. |
| Alias | Shortcut name used in legends and expressions. |
| Pulse ID | Per-row pulse override. Use `+(pulseID)` to add, `-(pulseID)` to exclude, comma-separated. |
| Start Time / End Time | Per-row time override (ISO 8601, or relative seconds for pulse mode; negative values allowed). |
| X / Y / Z | Redefine the X, Y, Z vectors used for plotting (Z for contour and slider plots). |
| Extremities | Set to 1 to retrieve the last point before the start time (useful for PON data). |
| Plot type | Default `PlotXY`. |
| Output datatype | Indicates the output type of data retrieved from the archive. |
| Status | Status of the different stages (data retrieval, processing). |
| Comment | Free-text description, useful when sharing CSV/workspace files. |

Complex layouts can be built by manipulating *Stack*, *Row span* and *Col span*. The example workspace `ExampleOfComplexLayout.json` reproduces a multi-plot layout combining stacks and column spans.

<p style="text-align:center;margin:14px 0;"><img src="image_07.png" alt="Example of a complex layout" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 7. Example of complex layout.</i></p>

### 2.5 Draw, Stream {#draw-stream}

Once the time range or pulse IDs are set and the table populated, click **Draw** to plot, or **Stream** to subscribe to incoming data. Streaming requires a window in seconds (max 3600 s).

<p style="text-align:center;margin:14px 0;"><img src="image_08.png" alt="Draw and Stream action buttons" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 8. Action buttons.</i></p>
<p style="text-align:center;margin:14px 0;"><img src="image_09.png" alt="Stream settings dialog" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 9. After clicking on Stream.</i></p>

<div class="note">Preferences are unavailable while streaming. Apply preferences via <em>Draw</em> first, then start the stream.</div>

### 2.6 Export/Import workspace {#export-import-workspace}

Use *File > Import Workspace* or *File > Export workspace*. Workspaces are JSON files.

<p style="text-align:center;margin:14px 0;"><img src="image_10.png" alt="File menu with workspace import / export options" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 10. Export / Import workspace.</i></p>

### 2.7 Export data {#export-data}

The *Export* button opens a dialog where you choose an output path and a format (parquet or hdf5). Only signals with a valid stack id are exported. Processing signals are discarded.

While the export runs, a progress bar in the status bar reports the variable currently being written, so long exports are no longer mistaken for a frozen application.

<p style="text-align:center;margin:14px 0;"><img src="image_11.png" alt="Export button highlighted" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 11. Export data.</i></p>

<div class="err-block">If the export fails or completes only partially, MINT shows a popup with the underlying reason. Common causes are listed under <a href="#errors">Error reference</a>: <a href="#errors-permission-denied">Permission denied</a>, <a href="#errors-export-expression">Expressions in Variable column</a>, <a href="#errors-export-custom-time">Per-signal time overrides</a>, <a href="#errors-export-xyz">Custom x/y/z processing</a>.</div>

### 2.8 Plotting area {#plotting-area}

Above the canvas sits a toolbar (movable when the canvas is detached). Buttons:

<p style="text-align:center;margin:14px 0;"><img src="image_12.png" alt="Canvas toolbar" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 12. Canvas toolbar.</i></p>

- **SELECT**: left double-click to put a plot in full-screen; right double-click to go back.
- **CROSSHAIR**: shows X/Y coordinates and the closest signal value. SELECT disables it.
- **PAN**: drag to pan; left double-click to reset.
- **ZOOM**: rubber-band a region (cover both X and Y); left double-click to reset.
- **DIST**: Euclidean distance between two clicks. Also shifts a signal along Y, or X (in pulse mode).
- **MARKER**: precise distance by selecting points (only with &lt; 100 points per plot).
- **RULER**: double-click to drop a ruler (A, B, C…) on a data point; a preview follows the cursor beforehand. The ruler stays pinned to that point as you zoom and pan, and shows the value of every signal it crosses. Drag it to move it, or right-click it → *Remove ruler*. With shared time on, the ruler appears on every plot and is removed from all of them at once. Rulers are listed in the *Rulers window* (below) and saved with the workspace.
- <img src="image_13.png" class="inline-icon" alt="Stats icon" /> Stats icon: min/avg/max, first/last value and time, sample count. Hide unused columns via *Hide/Show columns*.
- Undo / Redo: roll back or replay the last pan/zoom action.
- **HOME**: resets all plots to the original view. The data is served from cache. In relative time it also stops the auto-refresh — press *Draw* to resume it.
- Folder / Floppy: open / save preferences.
- Square-with-arrow: export the points of each signal currently rendered.
- Gears: open the preferences panel (canvas, plot, signal, axis levels).
- **MINI-MAP**: toggle a small overview of the current plot below the canvas. Enabled only when a single PlotXY is visible — either a single-plot canvas or focus mode — and stays greyed out otherwise. The mini-map shows the same signal over the original time window captured at *Draw* time, with an orange overlay that tracks the zoomed / panned region of the main plot in real time. The toggle is persisted with the workspace (`show_minimap` flag).
- **DETACH** / **REATTACH**: float the canvas in its own window.

Right-click a plot for per-plot actions, including **Reset zoom/pan** — the same reset as *Home* but limited to that plot, which is how you reset a single plot when *shared time* is off.

#### Reading tick labels with very large values

When the plotted values are too large for plain tick labels — e.g. a signal whose values are raw nanosecond timestamps — the axis compacts them in *offset + scale* form, shown in the corner of the axis. A corner label like `1e9+1.121e15` is interpreted as follows:

- `1e9` is the multiplier applied to each tick label;
- `+1.121e15` is the offset added afterwards.

So a tick labelled `824` really means `824 × 1e9 + 1.121e15 = 1,121,824,000,000,000`. Either part may appear alone: a corner label with only a power of ten (e.g. `1e18`) is just the multiplier, with no offset added. The statistics table always shows the full, uncompacted values.

<p style="text-align:center;margin:14px 0;"><img src="image_19.png" alt="Axis with offset + scale corner label" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 13. Offset + scale tick notation: each tick is multiplied by 1e9, then 1.121e15 is added.</i></p>

#### Rulers window

Opens behind the canvas when you activate the RULER tool; click the RULER button again to bring it to the front. Two layouts:

- **Rows**: one ruler per row with its X/Y values, one column per crossed signal with its value at the ruler (blank where the ruler sits off a signal; with shared time on, the ruler also carries the values of the other plots' signals at its position, which is what makes cross-plot deltas possible) and per-ruler controls — *Visible* (show or hide the ruler), *Labels* (choose whether to show the name tag, the signal-value tags, both or neither), *Color* (the ruler's lines and label boxes) and *Font color* (the label text; adapts to stay readable by default). Long signal names wrap over several header lines, and hovering a header shows the full name.
- **Columns**: a read-only view with one section per plot — rulers ordered by X value as columns, one row per signal below the X/Y rows, and a Δ column showing the gap between neighbours for X, Y and every signal.

*Hide/Show signals* picks which signal columns (or rows, in the Columns layout) are displayed. Columns can be resized, and you can copy the selection (Ctrl+C or right-click → *Copy*) or the whole table (*Copy table* button) to paste into a spreadsheet. *Export to CSV* writes the whole table (every ruler and every column) to a semicolon-separated `.scsv` file — the same convention as the signal-set export, so it opens cleanly in a spreadsheet — or a plain comma `.csv`. *Remove ruler* deletes the selected rulers; *Compute distance* opens a table with the ΔX, ΔY and per-signal deltas between two or more of them — even across plots — with its own *Copy* button; on time axes the ΔX also shows the duration in the statistics-table format, e.g. `9.5 s (9s500ms)`.

#### Canvas-level preferences

Title, font size, shared time, time-range difference, round hours, auto scale, Y min/max batch update, log scale, grid, show all ticks, number of ticks, background colour, legend (visibility, position, layout), crosshair labels (X, Y, Val), crosshair colour, font colour, line style (solid / dotted / dashed / none), line size, marker style (+ or o), marker size, line path (linear or last value), focus all plots on stack.

Plot-level preferences mirror the canvas-level ones. Signal-level preferences are a subset; the variable label can also be overridden. Axis x and y0 properties allow custom labels and limits, plus disabling autoscale.

Most preference changes survive subsequent *Draw* calls; axis-limit changes do not. Click *Apply* to commit and close the panel.

To persist preferences, save them and add to your profile:

```
IPLOT_CANVAS_CONFIG=~/.local/1DPreferences/default_properties.json
```

### 2.9 Expressions {#expressions}

#### 2.9.1 Simple processing

Wrap a variable in `${...}` and combine with NumPy operations. `${X}.data` and `${X}.time` refer to the data and time vectors of variable X.

Example: multiply `UTIL-HV-S22-BUS1:TOTAL_POWER` by `-2` and add an offset of `10`:

```
${UTIL-HV-S22-BUS1:TOTAL_POWER}*(-2)+10
```

Aliases can be reused in expressions. If the Stack column is empty, the signal is not drawn (it can still feed an expression).

#### 2.9.2 Complex processing

Combine several variables with aliases:

```
${Bus1} + ${Bus2} + ${Bus4}
```

The processing module aligns the time vectors when they differ (union of the time vectors, interpolated using the previous-value mode).

<div class="err-block">If the result of an expression has incompatible shapes, MINT will report it - see <a href="#errors-shape-mismatch">Signal arrays have incompatible shapes</a>.</div>

#### 2.9.3 Use of x and y columns

The *x* column rewrites the time vector; *y* rewrites the data vector. Example - plot a signal as the maximum value over a relative-time window:

| Column | Value |
|--------|-------|
| X | `(${ML4_max}.time-${ML4_max}.time[0])/86400000000000` |
| Y | `np.max(${ML4_max}.data) * np.ones(${ML4_max}.data.size)` |

NumPy is available via the `np.` prefix. The X/Y columns can also be used to plot one signal against another. Note: time vectors are nanoseconds since Unix epoch in absolute mode, or relative seconds in pulse mode.

<p style="text-align:center;margin:14px 0;"><img src="image_17.png" alt="X and Y columns in a complex processing example" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 14. Using X and Y columns in a complex processing.</i></p>

### 2.10 Data Sources {#data-sources}

The default configuration lives under `/etc/opt/codac/mint/datasources_def.cfg`. Example:

```
{
  "codacuda": {
    "type": "CODAC_UDA",
    "host": "io-ls-udasrv1.iter.org",
    "port": 3090,
    "rturl": "https://controls.iter.org/dashboard/backend/sse",
    "rtheaders": "REMOTE_USER:$USERNAME,User-Agent:python_client",
    "rtauth": null,
    "default": true,
    "uda_for_export": "io-ls-udasrv2.iter.org"
  },
  "imaspy": {
    "type": "IMASPY",
    "database": "iter",
    "path": "public",
    "backend": "MDSPLUS"
  }
}
```

Override the default file with `IPLOT_SOURCES_CONFIG`. *conninfo* contains connection info; for UDA it is `host=...,port=...`; for IMAS `database=...,path=...,backend=MDSPLUS`. *varprefix* can be left empty. *rturl* is optional (SSE streaming endpoint). *rtheaders* contains expected headers. *rtauth* is the authentication mechanism (`None` if none). *uda_for_export* is optional: set it to export data from a different UDA server than the one you plot from. The same *port* is used.

See also: [Reference - Supported data source types](#datasource-types) for the list of source types MINT recognises.

## 3. ITER environment {#iter-environment}

### 3.1 CODAC {#codac}

MINT is installed on all CODAC XPOZ terminals. The CCI team grants access to the relevant machines. The tool connects to the central UDA servers; IMAS data is not yet accessible from CODAC terminals.

### 3.2 SDCC cluster {#sdcc}

```
$ module load MINT
$ mint
```

From SDCC you can plot IMAS and CODAC data on the same canvas. IMAS data is only accessible by pulse IDs (no absolute time range).

### 3.3 Pulse identifier support {#pulse-identifier}

Until CCS v6.2 the pulse was a number; from CCS v6.3 it is a string with three parts: location, category, number, e.g. `ITER:PCS/12000`. Both syntaxes are supported; bare numbers fall back to the central UDA defaults. IMAS pulses currently use `<pulse>/<run>`, e.g. `130012/2`; Access Layer URIs of the form `imas:<backend>?path=/path/to/data/entry` are also supported.

## 4. Reference {#reference}

This section is auto-generated from the code at build time. Do not edit by hand — edits are overwritten.

### 4.1 Keyboard shortcuts {#keyboard-shortcuts}

<!-- AUTO_SHORTCUTS -->

### 4.2 Access modes {#access-modes}

<!-- AUTO_ACCESS_MODES -->

### 4.3 Supported data source types {#datasource-types}

<!-- AUTO_DATASOURCES -->

## 5. FAQ {#faq}

1. **Font is too small.** Two options. From the GUI: open the canvas preferences (gear icon in the canvas toolbar) and raise *Font size*. Globally for the whole application: set `QT_SCALE_FACTOR=2` (or another value) before starting MINT.
2. **The tool crashed - did I lose my table?** Every *Draw* dumps the table; copies live in `~/.local/1Dtool/dumps`.
3. **Can I run two instances?** Yes.
4. **PON data:** set *Extremities* to 1 to retrieve the first point of the interval.
5. **An expression fails because one signal has no data.** Currently a missing input signal aborts the expression. This will improve in a future release.
6. **I loaded a workspace and the canvas is blank.** Click *Draw* - it usually helps.
7. **A preference change is not visible.** Close the preferences panel - it usually helps.
8. **Can I move the canvas toolbar?** Only when the canvas is detached. Click *Detach* first; the toolbar then shows a small grab handle on its left edge — drag from there to move it. <p style="text-align:center;margin:14px 0;"><img src="image_18.png" alt="Toolbar drag handle highlighted" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 15. Moving the canvas toolbar (visible after Detach).</i></p>
9. **Overlay pulses on all plots?** Comma-separate pulse IDs. See `OverlayPulsesID.json`.
10. **Overlay or append a pulse on a single plot?** See `CustomizedPulsesPlots.json`.
11. **Specify a start/end time for pulse IDs?** Use Start/End Time with shared X axis off. See `CustomizedPulsesPlotsWithStartEnd.json`.
12. **Compare signals with two different time ranges?** Yes (untick shared X). See `WeekComparison.json`.
13. **Different time ranges on the same plot, no pulses?** See `WeekComparisonSamePlot.json`.
14. **Load a new Python module?** Click *Load new module* and import e.g. `scipy.fft as sfft`.
15. **Examples of self-written modules?** See Advanced Exercises [RD5].
16. **Add my own data source?** See Advanced Exercises [RD6].
17. **Where are the workspaces?**

    ```
    $ ls `rpm -ql ${CODAC_RPM_PREFIX}-mint | grep workspaces | head -n 1`     # CODAC
    $ ls `echo $(dirname "$IPLOT_SOURCES_CONFIG")/data/workspaces`              # SDCC
    ```

18. **Cell too small to write an expression?** Right-click and pick *Editor mode*; the resulting window is resizable.
19. **Hide unused columns?** Use *Hide/Show columns* above the table.
20. **Drag-and-drop a signal across plots?** Yes - in SELECT mode.
21. **Why is the mini-map button greyed out?** It is only available when a single PlotXY is visible — a single-plot canvas or focus mode.

## 6. Error reference {#errors}

MINT reports two kinds of feedback. *Validation messages* (e.g. `Invalid date format`, `Alias already in use`) are written to the log when you edit the table; they are self-explanatory and not duplicated here. *Conceptual errors* (network problems, mismatched signal shapes, permission issues) are the ones that benefit from extra context — those are catalogued below and are reachable from popups, the Status column tooltip and the Help menu.

### Error categories {#error-categories}

Most issues fall into one of the following families.

#### Data access {#cat-data-access}

Raised when MINT asks a data source for a signal and either cannot reach the server, cannot find the variable, or finds no data in the requested interval. Typical symptoms: the Status cell shows `Data-Access | 0 points` or a network/timeout message, the affected row turns red, and other rows in the same plot may turn orange (downstream errors). Most of the time the fix is to widen the time range, verify the variable name, or check that the data source is reachable.

#### Processing {#cat-processing}

Raised while MINT evaluates an expression or aligns signals before plotting. The two most common variants are arrays of incompatible shapes (signals with different sample counts that NumPy cannot broadcast) and expressions that return a scalar instead of an array. Mixing envelope and non-envelope signals also lives here. The Status cell carries the underlying NumPy or parser message; hover it for the human-readable explanation.

#### Export {#cat-export}

Raised by the *Export* dialog. The export only delivers raw data straight from the data source, so per-signal time overrides, custom x/y/z processing and signals defined as expressions in the *Variable* column are skipped (with a warning listing which aliases were skipped). A genuine failure — for example writing to a folder where the user has no permission — produces a red *Export failed* popup with the underlying reason and a Learn more button.

#### Configuration {#cat-configuration}

Raised at startup or while loading workspaces. Examples: `no data sources found, exiting` (the data sources file is missing or empty), `Blueprint does not have a DataSource key` (the blueprint JSON is malformed), `Could not load the embedded manual` (a packaged resource is missing). These almost always point at an environment or installation problem rather than user input.

#### Table validation {#cat-validation}

Raised when MINT rejects a value typed in the signals table — invalid date formats, duplicated aliases, non-numeric stack identifiers, out-of-range values. These messages already describe both the problem and the remedy, so they only appear in the log; no further explanation is needed.

#### Streaming {#cat-streaming}

Raised by the streaming pipeline. Symptoms include occasional *operands could not be broadcast together* warnings while the X and Y buffers of a signal are being updated, and `PlotItem not found` followed by an `IndexError` in the date axis formatter when a workspace is imported with a stream still active. The first one is transient and recovers on the next frame; the second one is a known race for which the workaround is to stop the stream before importing.

### Catalogued errors

<!-- AUTO_ERRORS -->
