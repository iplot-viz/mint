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
