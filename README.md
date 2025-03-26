## Description

This project contains example usage of the iterplot libary in a Qt application. 
The Qt application allows to select a set of UDA variables and to plot them using either matplotlib or VTK graphics library.
Following features are currently supported:

* Plotting multiple graphs in a row/column layout
* Plotting multiple signals in one plot (either stacked or not) by using the `ROW.COLUMN.STACK` format
* Support for Pan/Zoom/Crosshair/Distance
* Support for automatically downloading UDA data (for continous signals - currently Matplotlib only)
* Support for basic data processing. See [iplotProcessing](https://git.iter.org/projects/VIS/repos/iplotprocessing/browse)
* Customize appearance and styling of canvas, plots, axes, fonts, lines in a cascading manner.

## Installation
```bash
pip install
```

## Run the app
```bash
mint
```

## Run standalone signal configurator.
```bash
mint-signal-cfg
```
