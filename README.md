## Description

This project contains example usage of the iterplot libary in a Qt application. 
The Qt application allows to selec a set of UDA variables and the plot them using either matplotlib or gnuplot.
Following features are currently supported:

* Plotting multiple graphs in a row/column layout
* Plotting multiple signals in one plot (either stacked or not) by using the `ROW.COLUMN.STACK` format
* Support for Pan/Zoom/Crosshair
* Support for automatically downloading UDA data (for continous signals - currently Matplotlib only)

## Running the example

Install
`$pip install .`
Run
`$ mint`