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


# Description: The MINT application directories
# Author: Jaswant Sai Panchumarti

import os

EXEC_PATH = __file__
ROOT = os.path.dirname(EXEC_PATH)
DEFAULT_DATA_SOURCES_CFG = os.path.join(ROOT, 'mydatasources.cfg')
DEFAULT_DATA_DIR = os.path.join(ROOT, 'data')


def update(exec_path: str = EXEC_PATH):
    global DEFAULT_DATA_DIR, DEFAULT_DATA_SOURCES_CFG, EXEC_PATH, ROOT

    EXEC_PATH = exec_path
    ROOT = os.path.dirname(EXEC_PATH)
    DEFAULT_DATA_SOURCES_CFG = os.path.join(ROOT, 'mydatasources.cfg')
    DEFAULT_DATA_DIR = os.path.join(ROOT, 'data')
