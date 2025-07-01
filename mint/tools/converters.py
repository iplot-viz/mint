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


# Description: Commonly used converters.
# Author: Piotr Mazur

import numpy as np


def str_to_arr(value):
    return None if value is None else [e.strip() for e in value.split(',')]


def to_unix_time_stamp(value: str, time_units: str = "ns") -> int:
    return np.datetime64(value, time_units).astype('int64').item()
