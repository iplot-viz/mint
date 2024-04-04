import os
from mint.app import dirs

def test_update_sets_global_variables_to_new_values():
    """
    Test case for the update method in the dirs module.
    This test checks if the update method correctly sets the global variables
    when a new path is provided as an argument.
    """
    dirs.update("/new/path/to/exec")
    assert os.path.normpath(dirs.EXEC_PATH) == os.path.normpath("/new/path/to/exec")
    assert os.path.normpath(dirs.ROOT) == os.path.normpath("/new/path/to")
    assert os.path.normpath(dirs.DEFAULT_DATA_SOURCES_CFG) == os.path.normpath("/new/path/to/mydatasources.cfg")
    assert os.path.normpath(dirs.DEFAULT_DATA_DIR) == os.path.normpath("/new/path/to/data")

def test_update_sets_global_variables_to_default_when_no_argument():
    """
    Test case for the update method in the dirs module.
    This test checks if the update method correctly sets the global variables
    to their default values when no argument is provided.
    """
    dirs.update()
    assert os.path.normpath(dirs.EXEC_PATH) == os.path.normpath(dirs.__file__)
    assert os.path.normpath(dirs.ROOT) == os.path.normpath(os.path.dirname(dirs.__file__))
    assert os.path.normpath(dirs.DEFAULT_DATA_SOURCES_CFG) == os.path.normpath(os.path.join(dirs.ROOT, 'mydatasources.cfg'))
    assert os.path.normpath(dirs.DEFAULT_DATA_DIR) == os.path.normpath(os.path.join(dirs.ROOT, 'data'))

def test_update_handles_relative_paths_correctly():
    """
    Test case for the update method in the dirs module.
    This test checks if the update method correctly handles relative paths.
    """
    dirs.update("./relative/path")
    assert os.path.normpath(dirs.EXEC_PATH) == os.path.normpath("./relative/path")
    assert os.path.normpath(dirs.ROOT) == os.path.normpath("./relative")
    assert os.path.normpath(dirs.DEFAULT_DATA_SOURCES_CFG) == os.path.normpath("./relative/mydatasources.cfg")
    assert os.path.normpath(dirs.DEFAULT_DATA_DIR) == os.path.normpath("./relative/data")