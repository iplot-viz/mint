## Description

This project contains example usage of the iterplot libary in a Qt application. 
The Qt application allows to select a set of UDA variables and the plot them using either matplotlib or PyQtGraph graphics library.
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

## Development
Clone all the projects
```bash
mkdir mintdev
cd  mintdev
git clone -b develop git@github.com:iplot-viz/iplotlogging.git
git clone -b develop git@github.com:iplot-viz/iplotprocessing.git
git clone -b develop git@github.com:iplot-viz/iplotdataaccess.git
git clone -b develop git@github.com:iplot-viz/iplotwidgets.git
git clone -b develop git@github.com:iplot-viz/iplotlib.git
git clone -b develop git@github.com:iplot-viz/mint.git
```
Create virtual environment
```bash
python -m venv devenv
source devenv/bin/activate
```


Install all packages with the editable option
```bash
cd iplotlogging;pip install -e .
cd ../iplotprocessing;pip install -e .
cd ../iplotdataaccess;pip install -e .
cd ../iplotwidgets;pip install -e .
cd ../iplotlib;pip install -e .
cd ../mint;pip install -e .
```

Set the IPLOT_SOURCES_CONFIG environment variable to point to mydatasources.cfg
This configuration file is generally stored in the mint repository under the mint directory
```bash
export IPLOT_SOURCES_CONFIG=./mint/mint/mydatasources.cfg
```


### Config File Format

```json
{
    "my_source_name": {
        "type": "IMASPY",
        "database": "iter",
        "backend": "HDF5",
        "default": false,
        "populate_pulse_table": true,
        "pulse_list_folder": "/abs/path/to/local/pulses",
        "simdb_url": "https://simdb.iter.org/scenarios/api/v1.2/simulations",
        "simdb_metadata_url": "https://simdb.iter.org/scenarios/api/v1.2/simulation/{uuid}"
    }
}
```

### IMASPY DATA Source Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `type` | string | yes | Must be `"IMASPY"` |
| `database` | string | no | IMAS database name (default: `"ITER"`) |
| `backend` | string | no | IMAS backend (default: `"hdf5"`) |
| `user` | string | no | IMAS user (default: `"public"`) |
| `version` | string | no | IMAS DD version (default: `"3"`) |
| `default` | bool | no | Set as default data source |
| `populate_pulse_table` | bool | no | Enable pulse browser table population (default: `false`) |
| `pulse_list_folder` | string | no | **Absolute path** to a local folder to scan for IMAS files. Supported: `master.h5`, `*.h5`, `*.nc`, `*.tree`. |
| `simdb_url` | string | no | SIMDB REST API URL for fetching simulation list |
| `simdb_metadata_url` | string | no | SIMDB REST API URL template for per-simulation metadata (`{uuid}` is substituted) |


Start the application
```bash
mint
```


## Contributing

1. Fork it!
2. Create your feature branch: ```git checkout -b my-new-feature ```
3. Commit your changes: ```git commit -am 'Add some feature' ```
4. Push to the branch:```git push origin my-new-feature ```
5. Submit a pull request
