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
    - [2.11 Assistant](#assistant)
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

This is a how-to guide for MINT - Make Informative and Nice Trends, the visualization tool developed alongside Science Division and used in the ITER control room. It plots CODAC plant data and IMAS data.

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

Plots use matplotlib by default. To use PyQtGraph instead, start MINT with `mint --impl pyqt`, or set `MINT_IMPL=pyqt` when it is started from a menu or an icon.

<div class="note">If MINT exits with <em>"no data sources found, exiting"</em>, it could not find a valid UDA or IMAS server. See <a href="#errors-no-data-sources">Error reference - No data sources</a> and <a href="#data-sources">section 2.10</a>.</div>

### 2.2 Logging {#logging}

Logs are written to `~/.local/1Dtool/logs/`, one `mint_*.log` file per MINT session.

To change how much is logged, set `IPLOT_LOG_LEVEL` before starting MINT: `DEBUG`, `INFO` (default), `WARNING`, `ERROR` or `CRITICAL`, from most to least detail.

```
$ export IPLOT_LOG_LEVEL=DEBUG
$ mint
```

### 2.3 Time configuration {#time-configuration}

All times are UTC, whatever the time zone of the computer, and written in ISO 8601 (`2026-08-13T05:52:06`). On the time axis, the part common to the whole view is shown once in the corner (`UTC:2026-08-13T05:52:`) and each tick shows only the rest, with its unit when it is a single number: `06s`, `20min`, `500ms`.

Data can be queried by:

- Absolute time range (From time / To time, ISO 8601).
- Pulse ID. On CCS, a pulse identifier is a string with location, category and number, e.g. `ITER:CWS-SCSU-BASIN-FILL-TESTS/130125`. On SDCC, IMAS pulses use `pulse/run`, e.g. `135011/7`, or an Access Layer URI such as `imas:hdf5?path=/home/ITER/.../3/105027/32`.
- Relative time range, with an optional refresh interval (minimum 5 minutes).

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_01.png" alt="Querying by absolute time range" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 1. Querying by absolute time range.</i></p>
<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_02.png" alt="Querying by pulse id on CCS" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 2. Querying by pulse id on CCS.</i></p>
<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_03.png" alt="Querying IMAS data by pulse id on SDCC" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 3. Querying IMAS data by pulse id on SDCC: pulse/run.</i></p>
<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_04.png" alt="Querying by pulse id on SDCC using URI" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 4. Querying by pulse id on SDCC: using URI.</i></p>
<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_05.png" alt="Querying by relative time range" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 5. Querying by relative time range.</i></p>

To overlay several pulses, separate their IDs with commas. *Search*, next to the Pulse ID field, browses the pulses. Its *Selected* column marks the pulses the plots use (this field, the pulse the time range was taken from, and the *PulseId* column of the table), and stays up to date while the window is open; sort by it to bring them to the top. Click a page number next to the `<` `>` arrows to jump to that page. *Started between* keeps only the pulses that started between two UTC times, alone or with a search pattern; it is greyed out when the pulses of the data source have no times.

### 2.4 Table {#table}

#### 2.4.1 Icons and buttons

Above the variable table: *Open*, *Append* and *Save Signal Sets* (the table as a file); *Hide/Show columns*; *Search Vars* to browse the variables of each data source; *Load new module* to add a Python module for use in expressions.

In the variable search window, the number of variables found is shown next to the search bar; double-click a node to expand all its children, or to collapse it again. For data sources with a controls metadata server (`controlsmetadata` key in the data sources file), the *Synoptic variables* check box lists the variables shown on the HMI, each with its unit in square brackets, data type and description. With it checked, the search also looks in the description and the unit: several words find the variables that have them all, in any order (`magnet temperature [K]`); a unit in square brackets (`[K]`) keeps only the variables in that unit, alone or with more words (`[K] temperature`); a word in capitals is matched as written, so `mass flow VAC` finds the mass flows of the VAC variables, not those that only mention a vacuum.

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_06.png" alt="Icons and buttons above the variable table" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 6. Icons / buttons above the variable table.</i></p>

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
| PulseId | Pulses for this row instead of the global ones: `+(pulseID)` adds one, `-(pulseID)` excludes one; comma-separated. |
| StartTime / EndTime | Time range for this row only (ISO 8601, or seconds relative to the pulse in pulse mode; negative values allowed). |
| X / Y / Z | Redefine the X, Y, Z vectors used for plotting (Z for contour and slider plots). |
| Extremities | Set to 1 to retrieve the last point before the start time (useful for PON data). |
| Plot type | Default `PlotXY`. |
| Output datatype | Indicates the output type of data retrieved from the archive. |
| Status | Status of the different stages (data retrieval, processing). |
| Comment | Free-text description, useful when sharing CSV/workspace files. |

Complex layouts can be built by manipulating *Stack*, *Row span* and *Col span*. The example workspace `ExampleOfComplexLayout.json` reproduces a multi-plot layout combining stacks and column spans.

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_07.png" alt="Example of a complex layout" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 7. Example of complex layout.</i></p>

### 2.5 Draw, Stream {#draw-stream}

Click **Draw** to plot, or **Stream** to follow live data. Streaming needs a time window, in seconds, minutes, hours or days (up to 7 days). The window is first filled from the archive, then live samples are added. Each signal keeps up to 10000 samples (`MINT_MAX_STREAMING_POINTS` changes it); beyond that, older samples are thinned out keeping their minima and maxima, and the last two minutes stay at full resolution. If the connection drops, MINT reconnects by itself and fills the gap from the archive; a stream silent for more than 60 s counts as dropped (`IPLOT_STREAM_READ_TIMEOUT`, in seconds, changes it).

Data is read in the background, so the window keeps responding. After *Draw* or a workspace import, all plots appear at once, each showing its progress (*Retrieving data (2/5) ..*), and each is drawn as soon as its data is in; the status bar shows the overall count (*Retrieving data (3/8)*), then *Ready.* once the plots are drawn. Zoom, pan, undo, redo and *Stream* also read in the background: the plots keep their current data, and the status bar says *Retrieving data...*, until the new data arrives. Signals used in another row's x, y or z are read first, and clicks wait until they are in, as during a relative-time refresh. UDA reads run two at a time; `MINT_DATA_ACCESS_WORKERS` changes that (up to 8; 0 turns background reading off, and the window freezes while it reads).

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_08.png" alt="Draw and Stream action buttons" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 8. Action buttons.</i></p>
<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_09.png" alt="Stream settings dialog" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 9. After clicking on Stream.</i></p>

<div class="note">Preferences cannot be changed while streaming: set them and press <em>Draw</em> before starting the stream. <em>Draw</em> stays disabled until the stream is stopped.</div>

### 2.6 Export/Import workspace {#export-import-workspace}

A workspace is a JSON file holding the table, the time settings and the plots, to reopen or share them. Use *File > Import Workspace* or *File > Export Workspace*.

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_10.png" alt="File menu with workspace import / export options" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 10. Export / Import workspace.</i></p>

### 2.7 Export data {#export-data}

The *Export* button opens a dialog where you choose an output path and a format (parquet or hdf5). Only signals with a valid *Stack* are exported; signals computed from expressions are left out. The *Time* box selects how timestamps are written: absolute time (nanoseconds) or relative time in seconds from the start of the time range. For pulse exports it has no effect. The *Sampling* box resamples all signals onto a common time base at the chosen frequency (1 Hz to 10 kHz): each interval holds the average of its samples, empty intervals repeat the previous value, and a `.resampling.log` file next to the output lists the affected ranges. The output then holds one time column plus one column per signal. *Native* keeps the original samples.

While the export runs, a progress bar in the status bar shows the variable being written.

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_11.png" alt="Export button highlighted" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 11. Export data.</i></p>

<div class="err-block">If the export fails or completes only partially, MINT shows a popup with the underlying reason. Common causes are listed under <a href="#errors">Error reference</a>: <a href="#errors-permission-denied">Permission denied</a>, <a href="#errors-export-expression">Expressions in Variable column</a>, <a href="#errors-export-custom-time">Per-signal time overrides</a>, <a href="#errors-export-xyz">Custom x/y/z processing</a>.</div>

### 2.8 Plotting area {#plotting-area}

Above the canvas sits a toolbar (movable when the canvas is detached). Buttons:

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_12.png" alt="Canvas toolbar" width="704" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 12. Canvas toolbar.</i></p>

- **SELECT**: left double-click to put a plot in full-screen; right double-click to go back.
- **CROSSHAIR**: shows X/Y coordinates and the closest signal value. SELECT disables it.
- **PAN**: drag to pan; left double-click to reset.
- **ZOOM**: drag a box to zoom into it, in X and Y; left double-click to reset.
- **DIST**: click two points to measure the distance between them; the window that opens can also shift a signal by that distance in X (in seconds on a time axis) or Y, or add a shifted copy with *Duplicate signal*. In SELECT mode, dragging a signal shifts it too.
- **MARKER**: precise distance by selecting points (only with &lt; 100 points per plot).
- **RULER**: double-click to drop a ruler (A, B, C…) on a data point. It stays on that point as you zoom and pan, and shows the value of every signal it crosses. Drag it to move it; right-click it → *Remove ruler* to delete it. With shared time on, it appears on every plot and is removed from all of them at once. Rulers are listed in the *Rulers window* (below) and saved with the workspace.
- <img src="image_13.png" class="inline-icon" alt="Stats icon" /> **Statistics**: min/avg/max, first and last value and time, and sample count of each signal; *Hide/Show columns* hides the ones you don't need.
- Undo / Redo: roll back or replay the last pan, zoom or shift. *Draw*, and each auto-refresh in relative time, clear this history.
- **HOME**: reset all plots to the original view. In relative time it also stops the auto-refresh; press *Draw* to resume it.
- Folder / Floppy: import / export a workspace (see [2.6](#export-import-workspace)).
- Square-with-arrow: save the points drawn for each signal to a CSV file.
- Camera: save the canvas as an image (PNG, SVG or JPEG).
- <img src="image_14.png" class="inline-icon" alt="Create Pulse icon" /> **Create Pulse**: create a UDA pulse from the visible time range — set category, status and a one-line description; leave the number empty for automatic numbering. Shown only with a write-capable UDA server.
- <img src="image_15.png" class="inline-icon" alt="Update Pulse icon" /> **Update Pulse**: search for an existing pulse and update its time range, status or description.
- Gears: open the preferences panel (canvas, plot, signal, axis levels).
- **MINI-MAP**: show or hide, below the canvas, the plot over its whole *Draw* time range, with an orange box marking the part you are looking at. Available only when a single PlotXY is shown (alone on the canvas or in full screen) and not while streaming. Saved with the workspace.
- **DETACH** / **REATTACH**: float the canvas in its own window.

Right-click a plot for per-plot actions:

- **Reset zoom/pan**: like *Home*, but only for that plot (useful with *shared time* off).
- **Set as time window**: copy the visible range of the plot into the time range (as seconds relative to the pulse, in pulse mode), so the next *Draw* reads exactly what you zoomed into.

#### Legend

Click a signal's line or name in the legend to hide the signal; click again to show it. Right-click either for its preferences. Drag the legend to move it, or drag its left or right side to make it narrower or wider: names that no longer fit are cut in the middle, and hovering one shows it in full. Click <img src="image_20.png" class="inline-icon" alt="Eye icon" /> in the top right corner of the plot to fold the legend away, and the closed eye to bring it back. Choosing a legend position in the preferences, or *Reset*, puts the legend back. Hidden signals and legend changes are kept by *Draw* and saved with the workspace.

#### Reading tick labels with very large values

When the plotted values are too large for plain tick labels — e.g. a signal whose values are raw nanosecond timestamps — the axis compacts them in *offset + scale* form, shown in the corner of the axis. A corner label like `1e9+1.121e15` is interpreted as follows:

- `1e9` is the multiplier applied to each tick label;
- `+1.121e15` is the offset added afterwards.

So a tick labelled `824` really means `824 × 1e9 + 1.121e15 = 1,121,824,000,000,000`. Either part may appear alone: a corner label with only a power of ten (e.g. `1e18`) is just the multiplier, with no offset added. The statistics table always shows the full, uncompacted values.

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_19.png" alt="Axis with offset + scale corner label" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 13. Offset + scale tick notation: each tick is multiplied by 1e9, then 1.121e15 is added.</i></p>

#### Rulers window

Opens behind the canvas when you activate the RULER tool; click the RULER button again to bring it to the front. Two layouts:

- **Rows**: one row per ruler and per plot it is on; with shared time on, a ruler is on every plot, and the *Plot* column tells the rows apart. Each row shows the ruler's X value and, for each signal it crosses, the signal value at the ruler (blank where the ruler is off the signal or the signal is on another plot); the Y value appears only on the plot the ruler was placed on. Controls: *Visible* shows or hides the ruler; *Labels* shows the ruler's own tags (name, X and Y), the signal-value tags, both or neither, on that row's plot only; *Color* sets the ruler's lines and label boxes; *Font color* sets the label text (by default it adapts to stay readable). Rows are listed by plot; click a header to sort by another column, or hover it to see a long signal name in full. Select several rows (Ctrl or Shift click, Ctrl+A for all) and change a control on any of them to apply it to all.
- **Columns**: a read-only view with one section per plot — rulers ordered by X value as columns, one row per signal below the X row (plus a Y row on the plot the ruler was placed on), and a Δ column showing the gap between neighbours for each of them.

*Hide/Show signals* picks which signal columns (rows, in the Columns layout) are shown; *Hide/Show labels* turns the name tags or the value tags of every ruler on or off at once, new rulers included. Copy the selection (Ctrl+C or right-click → *Copy*) or the whole table (*Copy table*) to paste it into a spreadsheet. *Export to CSV* saves the whole table as `.scsv` (semicolon-separated, like the signal sets) or `.csv`. *Remove ruler* deletes the selected rulers. *Compute distance* shows ΔX, ΔY and the difference of each signal between two or more selected rulers, also across plots, with its own *Copy* button; ΔY and the signal differences are signed (later ruler minus earlier), and on a time axis ΔX also shows as a duration, e.g. `9.5 s (9s500ms)`.

#### Canvas-level preferences

Title, font size, shared time, time-range difference, round hours, auto scale, Y min/max batch update, log scale, grid, show all ticks, number of ticks, background colour, legend (visibility, position, layout), crosshair labels (X, Y, Val), crosshair colour, font colour, line style (solid / dotted / dashed / none), line size, marker style (+ or o), marker size, line path (linear or last value), vertical lines (none, solid, dotted or dashed: a line in the signal colour and size through each point while a signal shows 50 points or fewer, as after a zoom), focus all plots on stack.

Plot-level preferences mirror the canvas-level ones. Signal-level preferences are a subset; the variable label can also be overridden. Axis x and y0 properties allow custom labels and limits, plus disabling autoscale.

*Draw* keeps most preference changes, but not axis limits. Click *Apply* to apply them and close the panel.

To keep preferences for the next sessions, click *Save preferences* in the canvas preferences: they are written to `~/.local/1DPreferences/default_properties.json` and loaded at start. To share one file among users, set `IPLOT_CANVAS_CONFIG` to its path; it takes precedence over the saved preferences.

### 2.9 Expressions {#expressions}

#### 2.9.1 Simple processing

Wrap a variable in `${...}` and combine with NumPy operations. `${X}.data` and `${X}.time` refer to the data and time vectors of variable X.

Example: multiply `UTIL-HV-S22-BUS1:TOTAL_POWER` by `-2` and add an offset of `10`:

```
${UTIL-HV-S22-BUS1:TOTAL_POWER}*(-2)+10
```

A row's alias can replace its variable name in expressions, e.g. `${Bus1}`. A row with an empty *Stack* is not drawn, but can still be used in expressions.

#### 2.9.2 Complex processing

Combine several variables with aliases:

```
${Bus1} + ${Bus2} + ${Bus4}
```

When the signals have different time stamps, MINT combines them over the union of their time stamps, each signal holding its previous value where it has no sample.

<div class="err-block">If the result of an expression has incompatible shapes, MINT will report it - see <a href="#errors-shape-mismatch">Signal arrays have incompatible shapes</a>.</div>

#### 2.9.3 Use of x and y columns

The *x* column replaces the time values; *y* replaces the data values. Example: X in days from the first sample, Y a flat line at the maximum of the signal:

| Column | Value |
|--------|-------|
| X | `(${ML4_max}.time-${ML4_max}.time[0])/86400000000000` |
| Y | `np.max(${ML4_max}.data) * np.ones(${ML4_max}.data.size)` |

NumPy is available via the `np.` prefix. The X/Y columns can also be used to plot one signal against another. Note: time vectors are nanoseconds since Unix epoch in absolute mode, or relative seconds in pulse mode.

In the *x*, *y* and *z* columns, `${self}` is the row's own signal. Use it instead of the row's own alias when the expression also uses other aliases, e.g. `${Bus1}.data - ${self}.data`.

<p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_17.png" alt="X and Y columns in a complex processing example" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 14. Using X and Y columns in a complex processing.</i></p>

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
  "imas": {
    "type": "IMAS",
    "database": "iter",
    "path": "public",
    "backend": "MDSPLUS"
  }
}
```

Override the default file with `IPLOT_SOURCES_CONFIG`. For UDA, *host* and *port* give the server. *rturl* is optional: the address for live streaming. *rtheaders* holds the headers it expects, and *rtauth* the authentication method (`null` if none). *uda_for_export* is optional: set it to export data from a different UDA server than the one you plot from. The same *port* is used. *variable_group_limit* is optional: a folder of the variable tree holding more variables than this number is split into sub-folders on `-`, `.` and `_` until none holds more; unset, the tree has one level of folders, split on the first `-` or `.` of the names. *cache_size* is optional (default 300): the number of data queries a UDA source keeps in memory.

See also: [Reference - Supported data source types](#datasource-types) for the list of source types MINT recognises.

### 2.11 Assistant {#assistant}

Ask in plain words for processing, plot settings, signals or a time range. Other languages work too; it answers in English. Open it with **AI Assistant** next to *Search Vars*, or *View > AI Assistant* (Ctrl+Shift+A). The button at the top right of the panel moves it to a window of its own and back.

- *smooth the pirani over 30 s*: adds a smoothed copy of the signal to the same plot.
- *put the second plot in log scale*, *no grid anywhere*.
- *outlet minus inlet*: a new signal in a new plot.
- *add the TF07 current*: lists the matching variables to tick and add.
- *two signals from EC in sdnuda*: lists the variables of that data source that start with EC. Right after a search, *no, in sdnuda* looks there instead.
- *last 6 hours*, *yesterday*, *pulse ITER:MCTB_PSS-TF07_FD/12*.
- *the same for MP0071*: repeats the last change on another signal.
- *why are these red?*: says why rows aren't drawn, and offers to change a data source that isn't available here.
- *disable FAST-TC0*: hides it from the plot, as a click on its legend entry does.
- *open the statistics*, *how many samples?*, *show the mini-map*, *open Search Vars*: opens them, or says what they are.
- With a file attached: *add the pressures from the report*, *over the dates in the file*.

Each answer comes as a card: nothing changes until **Apply** (or Enter with nothing typed, or *ok*), and **Undo** (or typing *undo*) puts it back; *no* dismisses it. If a signal it makes comes out with nothing to draw, the card says so. If a new time range leaves signals without data, it says when their latest sample is and offers the same span up to it. A number alone (*12 s*) repeats the last processing with it. The clip next to the input box attaches a CSV, Excel, PDF or signal set (*.scsv*) file (or drop one on the panel): the assistant finds the signal names, the dates and the pulses in it, and can add those signals or set their time range until the file is left out with its ×. Names written without their system (*MT0021-XI*) are looked up in the data source, and a list of names in a message, one per line or in a line, is read like a file. *Formula* on the card shows the expression it adds. When it isn't sure which signal or plot you mean, it asks; *both* or *the 3 of them* takes them all. The processing goes in the *x* or *y* column like any other expression, so the workspace opens the same without the assistant.

It runs on this computer, without network. Closing the panel frees the memory the model takes (about 2 GB), and opening it again takes a few seconds. It is off unless these are set (also in the file named by `MINT_XK_CONFIG`):

| Variable | Value |
|----------|-------|
| `MINT_ASSISTANT` | `1` |
| `MINT_ASSISTANT_MODEL` | path to the model file (`.gguf`) |
| `MINT_ASSISTANT_THREADS` | CPU threads, optional (up to 4 by default) |
| `MINT_ASSISTANT_SHA256` | SHA-256 of a model file MINT does not know yet, optional |
| `MINT_ASSISTANT_RECORD` | `1` to keep on this computer what you ask, what it answers and whether you apply each card (up to 1 MB), to retrain the assistant with, optional |

The runtime installs with `pip install iter-mint[assistant] --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`, which brings it ready built: without that address pip has to compile it, and CODAC has no compiler. It also brings what reads Excel (openpyxl) and PDF (pypdf) files.

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

<!-- The tables below are generated from the code by mint/tools/build_manual.py; do not edit them by hand. -->

### 4.1 Keyboard shortcuts {#keyboard-shortcuts}

<!-- AUTO_SHORTCUTS -->

### 4.2 Access modes {#access-modes}

<!-- AUTO_ACCESS_MODES -->

### 4.3 Supported data source types {#datasource-types}

<!-- AUTO_DATASOURCES -->

## 5. FAQ {#faq}

1. **Font is too small.** *View > Appearance > UI scale* enlarges the whole interface (125% to 200%); *Auto*, the default, only adapts the plot text to the screen. For the plots alone, open the canvas preferences (gear icon in the canvas toolbar) and raise *Font size*.
2. **The tool crashed - did I lose my table?** No: every *Draw* saves a copy of the table in `~/.local/1Dtool/dumps`.
3. **Can I run two instances?** Yes.
4. **PON data:** set *Extremities* to 1 to also get the last value before the start time.
5. **An expression fails because one signal has no data.** An expression is only computed when all its signals have data.
6. **I loaded a workspace and the canvas is blank.** Click *Draw*.
7. **A preference change is not visible.** Click *Apply*, or close the preferences panel.
8. **Can I move the canvas toolbar?** Only when the canvas is detached. Click *Detach* first; the toolbar then shows a small grab handle on its left edge — drag from there to move it. <p style="text-align:center;margin:14px 0;line-height:100%;"><img src="image_18.png" alt="Toolbar drag handle highlighted" style="border:1px solid #ccc;"/><br/><i style="color:#555;font-size:90%;">Figure 15. Moving the canvas toolbar (visible after Detach).</i></p>
9. **Overlay pulses on all plots?** Comma-separate pulse IDs. See `OverlayPulsesID.json`.
10. **Overlay or append a pulse on a single plot?** See `CustomizedPulsesPlots.json`.
11. **Specify a start/end time for pulse IDs?** Use *StartTime*/*EndTime* with *Shared time* off. See `CustomizedPulsesPlotsWithStartEnd.json`.
12. **Compare signals with two different time ranges?** Yes, with *Shared time* off. See `WeekComparison.json`.
13. **Different time ranges on the same plot, no pulses?** See `WeekComparisonSamePlot.json`.
14. **Load a new Python module?** Click *Load new module* and import e.g. `scipy.fft as sfft`.
15. **Examples of self-written modules?** See [RD5].
16. **Add my own data source?** See [RD6].
17. **Where are the workspaces?**

    ```
    $ ls `rpm -ql ${CODAC_RPM_PREFIX}-mint | grep workspaces | head -n 1`     # CODAC
    $ ls `echo $(dirname "$IPLOT_SOURCES_CONFIG")/data/workspaces`              # SDCC
    ```

18. **Cell too small to write an expression?** Right-click and pick *Editor mode*; the resulting window is resizable.
19. **Hide unused columns?** Use *Hide/Show columns* above the table.
20. **Drag-and-drop a signal across plots?** Yes - in SELECT mode.
21. **Why is the mini-map button greyed out?** It is only available when a single PlotXY is shown (alone on the canvas or in full screen) and not while streaming.
22. **A dark interface?** *View > Appearance > Theme > Dark* draws MINT, its plots and this manual in dark colours; *Auto* follows the light or dark mode of the system, and *None*, the default, keeps the light look. The colours set in the canvas preferences are kept, and MINT starts with the theme chosen last.

## 6. Error reference {#errors}

MINT reports two kinds of feedback. *Validation messages* (e.g. `Invalid date format`, `Alias already in use`) appear in the Status cell of the row when you Draw, and in the log; they are self-explanatory and not duplicated here. Other errors (network problems, mismatched signal shapes, permission issues) need more context: they are explained below, and popups, the Status cell tooltip and the Help menu link here.

### Error categories {#error-categories}

Most issues fall into one of the following families.

#### Data access {#cat-data-access}

Raised when MINT asks a data source for a signal and either cannot reach the server, cannot find the variable, or finds no data in the requested interval. Typical symptoms: the Status cell shows `Data-Access | 0 points` or a network/timeout message, the affected row turns red, and other rows in the same plot may turn orange (downstream errors). Most of the time the fix is to widen the time range, verify the variable name, or check that the data source is reachable.

#### Processing {#cat-processing}

Raised while MINT evaluates an expression or aligns signals before plotting. The most common: signals with different numbers of samples that cannot be combined, and expressions that return a single number instead of a signal. Mixing envelope and non-envelope signals also fails here. The Status cell shows the raw message; hover it for an explanation.

#### Export {#cat-export}

Raised by the *Export* dialog. The export only delivers raw data straight from the data source, so per-signal time overrides, custom x/y/z processing and signals defined as expressions in the *Variable* column are skipped (with a warning listing which aliases were skipped). A genuine failure — for example writing to a folder where the user has no permission — produces a red *Export failed* popup with the underlying reason and a Learn more button.

#### Configuration {#cat-configuration}

Raised at startup or while loading workspaces. Examples: `no data sources found, exiting` (the data sources file is missing or empty), `Blueprint does not have a DataSource key` (the blueprint JSON is malformed), `Could not load the embedded manual` (a packaged resource is missing). These almost always point at an environment or installation problem rather than user input.

#### Table validation {#cat-validation}

Raised when MINT rejects a value typed in the signals table — invalid date formats, duplicated aliases, non-numeric stack identifiers, out-of-range values. These messages already describe both the problem and the remedy: the Status cell of the row shows the first one, starting with `Invalid`, and the log keeps them all. A data source that isn't available here is catalogued below.

#### Streaming {#cat-streaming}

Two known messages while streaming. *operands could not be broadcast together* appears now and then while a signal is updated and clears by itself on the next update. `PlotItem not found` followed by an `IndexError` appears when a workspace is imported while a stream is running; stop the stream before importing.

### Catalogued errors

<!-- AUTO_ERRORS -->
