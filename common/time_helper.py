import numpy as np
from iplotLogging import setupLogger as sl

logger = sl.get_logger(__name__, level="INFO")

# str.isnumeric() does not work for negative numbers
def is_numeric(val):
    try:
        float(val)
    except:
        return False
    else:
        return True


# TODO: Check for 0 and pass it as number (it is prbably cheked fot rue/false)
# TODO: Is pulse number is overrider we discard start_time and end_time
# TODO: Check if overriding any value at row level resets all values from timerangeselector
# TODO: Use min/max from all plots when sharing x axis
def parse_timestamp(value):
    if isinstance(value, str):
        try:
            if is_numeric(value):
                return int(value) if float(value) > 10**15 else float(value)
            else:
                return int(np.datetime64(value, 'ns'))
        except:
            if len(value) > 0:
                logger.error(
                    f"Unable to parse string '{value}' as timestamp")
            pass

    return None