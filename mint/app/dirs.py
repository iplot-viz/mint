# Description: The MINT application directories
# Author: Jaswant Sai Panchumarti

import os

from PySide6.QtCore import QSettings

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


#: The folders a workspace and a signal set were last opened from or saved to, which the next session starts in. Per
#: user (QSettings).
WORKSPACES_FOLDER_KEY, SIGNAL_SETS_FOLDER_KEY = 'folders/workspaces', 'folders/signal_sets'


def remembered_folder(key: str, default: str) -> str:
    """The folder remembered for `key` (see remember_folder), or `default` without one, or once it is gone."""
    folder = QSettings().value(key)
    return folder if isinstance(folder, str) and os.path.isdir(folder) else default


def remember_folder(key: str, folder: str):
    QSettings().setValue(key, folder)
