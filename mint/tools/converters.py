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
                cur_dict = cur_dict.setdefault('-'.join(list_line), '')
            else:
                cur_dict = cur_dict.setdefault(var, {})

    return result


def parse_vars_to_dict(lines: List, pattern) -> dict:
    result = {}
    folders = [line.split(':')[1].split('-')[0] for line in lines]
    for ix in range(len(lines)):
        if folders.count(folders[ix]) > 1:
            result.setdefault(f'{pattern}:{folders[ix]}', {})
            result[f'{pattern}:{folders[ix]}'].update({lines[ix] + '?V': ''})
        else:
            result.update({lines[ix] + '?V': ''})

    return result


def parse(lines):
    result = dict()
    folders = [line.split(':')[1].split('-')[0] for line in lines if ':' in line]
    for line in lines:
        list_line = line.replace(':', '-:', 1).split('-')
        cur_dict = result
        for ix in range(len(list_line)):
            if ix == len(list_line) - 1:
                cur_dict = cur_dict.setdefault('-'.join(list_line).replace('-:', ':', 1) + "?V", '')
            elif list_line[ix][0] == ':':
                cur_dict = cur_dict.setdefault('-'.join(list_line[:ix + 1]).replace('-:', ':'), {})
                cur_dict = cur_dict.setdefault('-'.join(list_line).replace('-:', ':', 1) + "?V", '')
                break
            else:
                cur_dict = cur_dict.setdefault(list_line[ix], {})

    return result
