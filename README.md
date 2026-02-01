## Description

This project contains example usage of the iterplot libary in a Qt application. 
The Qt application allows to select a set of UDA variables and the plot them using either matplotlib or VTK graphics library.
Following features are currently supported:

* Plotting multiple graphs in a row/column layout
* Plotting multiple signals in one plot (either stacked or not) by using the `ROW.COLUMN.STACK` format
* Support for Pan/Zoom/Crosshair/Distance/Markers
* Support for automatically downloading UDA data (for continous signals - currently Matplotlib only)
* Support for basic data processing. See [iplotProcessing](https://github.com/iplot-viz/iplotprocessing)
* Customize appearance and styling of canvas, plots, axes, fonts, lines in a cascading manner.* 
* Computation of different statistical metrics for the displayed signals.
* Export of canvas data to CSV format.
* Export of canvas data and MINT tables to .h5 or .parquet formats

## Installation
Install the package from PyPi:

  ```bash
  pip install iter-mint
  ```

## Run the app
```bash
mint
```


## Contributing

1. Fork it!
2. Create your feature branch: ```git checkout -b my-new-feature ```
3. Commit your changes: ```git commit -am 'Add some feature' ```
4. Push to the branch:```git push origin my-new-feature ```
5. Submit a pull request
