"""Export of the data of a data source to files, parquet or hdf5, with the export script of iplotDataAccess.

This is the part of an export that reads the data and writes the files. MINT runs it in a worker process, so that
it can go on drawing meanwhile, or, without worker processes, in the GUI thread (see MTMainWindow.on_export_started).
It does not use Qt.
"""

import inspect
import os
import tempfile
from pathlib import Path

import pandas as pd

from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)

#: The type of the data sources whose data can be exported.
EXPORTED_SOURCE_TYPE = "CODAC_UDA"


def accepts_kwarg(func, name: str) -> bool:
    # Guards the progress-bar wiring against sibling releases (iplotlib, iplotDataAccess)
    # that predate the progress_callback parameter.
    try:
        return name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def reports_progress() -> bool:
    """Whether the export script of the installed iplotDataAccess tells which variable it exports. Not if it cannot
    be loaded, for want of the UDA client: the export says why it fails."""
    try:
        from iplotDataAccess.dataHandling.exportData.exportData import generateData
    except ImportError:
        return False
    return accepts_kwarg(generateData, 'progressCallback')


def export_data_source(data_access, data_s_name: str, variables, export_format: str, chunks: int, output_path: str,
                       pulses=None, ts=None, te=None, relative_time: bool = False, resample_freq=None,
                       progress=None) -> dict:
    """Export the `variables`, pairs of a name and a description, of the data source `data_s_name` of
    `data_access` to a file next to `output_path` for each pulse of `pulses`, or for the time range from `ts`
    to `te`. `progress`, if given, is told the name of each variable as its export starts.

    Gives the number of files it tried to write ('attempts'), of those it wrote ('exported'), and the reasons
    why the others failed ('errors').
    """
    from iplotDataAccess.dataHandling.exportData.exportData import generateData, connectUDA

    conn = data_access.ds_list[data_s_name]
    gen_kwargs = {}
    if progress is not None and accepts_kwarg(generateData, 'progressCallback'):
        gen_kwargs['progressCallback'] = progress

    # Relative time only applies to time-range exports; pulse exports
    # keep absolute timestamps.
    if relative_time and pulses is None:
        if accepts_kwarg(generateData, 'relativeTime'):
            gen_kwargs['relativeTime'] = True
        else:
            logger.warning("Relative time export requires a newer iplotDataAccess; "
                           "exporting absolute timestamps instead")

    # Resampling applies to time-range and pulse exports alike.
    if resample_freq:
        if accepts_kwarg(generateData, 'resampleFreq'):
            gen_kwargs['resampleFreq'] = resample_freq
        else:
            logger.warning("Resampling on export requires a newer iplotDataAccess; "
                           "exporting the original samples instead")

    # When configured, export pulls the data from an alternative UDA server (same port).
    if conn.uda_for_export:
        export_conn = connectUDA(conn.uda_for_export, conn.port)
        if export_conn.errc != 0:
            reason = (f"Export failed for data source '{data_s_name}': "
                      f"could not connect to export server '{conn.uda_for_export}'")
            logger.warning(reason)
            return dict(attempts=0, exported=0, errors=[reason])
    else:
        export_conn = conn

    attempts, exported, errors = 0, 0, []
    original_path = Path(output_path)
    # The export script reads the variables from a file, this export's own.
    handle, csv_file = tempfile.mkstemp(prefix=f"{data_s_name}_", suffix='.csv')
    os.close(handle)
    try:
        pd.DataFrame(list(variables)).to_csv(csv_file, index=False, sep=',', header=False)

        # Pulse mode: a file for each pulse, named after its start.
        windows = []
        for pulse in pulses or ():
            attempts += 1
            try:
                result = conn.get_pulse_info(pulse)
                if result is None:
                    raise LookupError("the data source has no such pulse")
                ts_iso = pd.to_datetime(result.timeFrom).isoformat().replace(':', '-')
            except Exception as e:
                reason = f"Export failed for data source '{data_s_name}' (pulse {pulse}): {e}"
                logger.warning(reason)
                errors.append(reason)
                continue
            windows.append((f"{result.timeFrom}", f"{result.timeTo}",
                            f"{data_s_name}_{ts_iso}_{original_path.stem}{original_path.suffix}", f" (pulse {pulse})"))
        if pulses is None:
            attempts += 1
            windows.append((f"{ts}", f"{te}", f"{data_s_name}_{original_path.stem}{original_path.suffix}", ""))

        for start, end, file_name, which in windows:
            new_path = original_path.with_name(file_name)
            # Use of export data script
            valid, err_msg = generateData(logfile=None, conn=export_conn, csvfile=csv_file, formatType=export_format,
                                          startTime=start, endTime=end, outputFolder=new_path, chunkS=chunks,
                                          **gen_kwargs)
            if valid:
                exported += 1
                logger.info(f"Export successful for data source: {data_s_name} (format: {export_format} | "
                            f"Path: {new_path}")
            else:
                reason = f"Export failed for data source '{data_s_name}'{which}: {err_msg}"
                logger.warning(reason)
                errors.append(reason)
    finally:
        os.remove(csv_file)
    return dict(attempts=attempts, exported=exported, errors=errors)
