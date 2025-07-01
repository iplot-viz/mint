# Copyright (c) 2020-2025 ITER Organization,
#               CS 90046
#               13067 St Paul Lez Durance Cedex
#               France
# Author IO
#
# This file is part of mint module.
# mint python module is free software: you can redistribute it and/or modify it under
# the terms of the MIT license.
#
# This file is part of ITER CODAC software.
# For the terms and conditions of redistribution or use of this software
# refer to the file LICENSE located in the top level directory
# of the distribution package
#


# Description: Helper to parse the row-column values in a table
# Author: Jaswant Sai Panchumarti

import numpy as np
from pandas import Series

from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__, level="INFO")


def is_non_empty_string(var):
    return isinstance(var, str) and not var.isspace() and len(var)


def str_to_arr(value: str):
    if value is None:
        return None
    else:
        str_list = [e.strip() for e in value.split(',')]
        for v in reversed(str_list):
            if v == '':
                str_list.pop(str_list.index(v))
        return str_list if len(str_list) else None


def get_value(row: Series, col_name: str, type_func=str):
    v = row[col_name]
    if type_func == bool:
        v = v in ['1', 1, 'True', 'true']
    if v is None:
        return type_func()
    try:
        return type_func(v)
    except ValueError:
        return type_func()


# str.isnumeric() does not work for negative numbers
def is_numeric(val: any) -> bool:
    if val is None:
        return False
    try:
        float(val)
        return True
    except ValueError:
        return False


# TODO: Check for 0 and pass it as number (it is probably checked fot true/false)
# TODO: Is pulse number is overrider we discard start_time and end_time
# TODO: Check if overriding any value at row level resets all values from timerangeselector
# TODO: Use min/max from all plots when sharing x axis
def parse_timestamp(value):
    if isinstance(value, str):
        try:
            if is_numeric(value):
                return int(value) if float(value) > 10 ** 15 else float(value)
            else:
                return int(np.datetime64(value, 'ns'))
        except (Exception,):
            if len(value) > 0:
                logger.error(f"Unable to parse string '{value}' as timestamp")
            pass

    return None
