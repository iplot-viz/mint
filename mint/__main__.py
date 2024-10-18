# Description: The MINT application to interact and explore data signals from codac databases and IMAS IDSs
# Author: Jaswant Sai Panchumarti

import sys
from mint.app import create_app, dirs, run_app
import os
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)


def load_env(fpath):
    with open(fpath, 'r') as f:
        line = f.readline()
        while line:
            keyval = line.split("=")
            if len(keyval) == 2:
                os.environ[keyval[0]] = keyval[1]
            line = f.readline()


def main():
    if os.environ.get('MINT_XK_CONFIG') is not None and os.path.isfile(os.environ.get('MINT_XK_CONFIG')):
        logger.info("Found an environment XK_CONFIG file for MINT")
        load_env(os.environ.get('MINT_XK_CONFIG'))

    q_app, args = create_app(sys.argv)
    dirs.update(__file__)
    sys.exit(run_app(q_app, args))


if __name__ == "__main__":
    main()
