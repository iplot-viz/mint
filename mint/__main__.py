# Description: The MINT application to interact and explore data signals from codac databases and IMAS IDSs
# Author: Jaswant Sai Panchumarti

import sys
from mint.app import createApp, dirs, runApp


def main():
    qApp, args = createApp(sys.argv)
    dirs.update(__file__)
    sys.exit(runApp(qApp, args))


if __name__ == "__main__":
    main()
