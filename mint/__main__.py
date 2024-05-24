# Description: The MINT application to interact and explore data signals from codac databases and IMAS IDSs
# Author: Jaswant Sai Panchumarti

import sys
from mint.app import create_app, dirs, run_app


def main():
    qApp, args = create_app(sys.argv)
    dirs.update(__file__)
    sys.exit(run_app(qApp, args))


if __name__ == "__main__":
    main()
