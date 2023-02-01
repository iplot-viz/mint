# Description: Commonly used converters.
# Author: Piotr Mazur

import numpy as np
from typing import List


def str_to_arr(value):
    return None if value is None else [e.strip() for e in value.split(',')]


def to_unix_time_stamp(value: str, time_units: str = "ns") -> int:
    return np.datetime64(value, time_units).astype('int64').item()


def parse_groups_to_dict(lines: List) -> dict:
    result = dict()
    for line in lines:
        cur_dict = result
        list_line = line.split('-')
        for var in list_line:
            if var.endswith('?V'):
                cur_dict = cur_dict.setdefault('-'.join(list_line)[:-2], '')
            else:
                cur_dict = cur_dict.setdefault(var, {})

    return result


def parse_vars_to_dict(lines: List, pattern) -> dict:
    result = {}
    folders = [line.split(':')[1].split('-')[0] for line in lines]
    for ix in range(len(lines)):
        if folders.count(folders[ix]) > 1:
            result.setdefault(f'{pattern}:{folders[ix]}', {})
            result[f'{pattern}:{folders[ix]}'].update({lines[ix]: ''})
        else:
            result.update({lines[ix]: ''})

    return result
