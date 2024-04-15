# Description: Commonly used converters.
# Author: Piotr Mazur

import numpy as np


def str_to_arr(value):
    return None if value is None else [e.strip() for e in value.split(',')]


def to_unix_time_stamp(value: str, time_units: str = "ns") -> int:
    return np.datetime64(value, time_units).astype('int64').item()
