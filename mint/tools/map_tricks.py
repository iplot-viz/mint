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


# Description: Utility functions for dictionaries.
# Author: Jaswant Panchumarti

from collections.abc import MutableMapping
from contextlib import suppress


def find_dict_in_list(lst):
    for v in lst:
        if isinstance(v, (list, tuple)):
            yield from find_dict_in_list(v)
        elif isinstance(v, dict):
            yield v
        else:
            continue


# Adapted from [here](https://stackoverflow.com/questions/3405715/elegant-way-to-remove-fields-from-nested-dictionaries)
# with above function to recursively hunt down dictionaries nested inside lists and/or tuples.

def delete_keys_from_dict(dictionary, keys):
    for key in keys:
        with suppress(KeyError):
            del dictionary[key]
    for value in dictionary.values():
        if isinstance(value, MutableMapping):
            delete_keys_from_dict(value, keys)
        elif isinstance(value, list):
            for dicti in find_dict_in_list(value):
                delete_keys_from_dict(dicti, keys)
