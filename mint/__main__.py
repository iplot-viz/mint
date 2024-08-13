# Description: The MINT application to interact and explore data signals from codac databases and IMAS IDSs
# Author: Jaswant Sai Panchumarti

import sys
from mint.app import create_app, dirs, run_app
import os
import subprocess


def is_screen_4k():
    try:
        process = subprocess.run(["xrandr"], stdout=subprocess.PIPE, check=True)
        lines = process.stdout.decode('utf-8').splitlines()
        # We need to look at the first line
        screen_resolution = []
        for line in lines:
            if "*" in line:
                screen_resolution.append(line.split()[0])

        return all(res == "3840x2160" for res in screen_resolution)

    except subprocess.CalledProcessError as cpe:
        print("Error with xrandr ", cpe)
        return False

    except ValueError as ve:
        print("Error with parsing output of xrandr ", ve)
        return False


def load_env(fpath):
    with open(fpath, 'r') as f:
        line = f.readline()
        while line:
            keyval = line.split("=")
            if len(keyval) == 2:
                os.environ[keyval[0]] = keyval[1]
            line = f.readline()


def main():
    if is_screen_4k():
        print("Found a 4K screen settings QT param")
        if os.environ.get('MINT_4K_CONFIG') is not None and os.path.isfile(os.environ.get('MINT_4K_CONFIG')):
            print("Found an environment file for MINT")
            load_env(os.environ.get('MINT_4K_CONFIG'))
        else:
            os.environ['QT_SCALE_FACTOR'] = "1.8"
            os.environ['QT_FONT_DPI'] = "50"
        print(" Applying QT_SCALE=" + os.environ.get('QT_SCALE_FACTOR') + " QT FONT " + os.environ.get('QT_FONT_DPI'))

    else:
        print("It is not a 4K screen")

    q_app, args = create_app(sys.argv)
    dirs.update(__file__)
    sys.exit(run_app(q_app, args))


if __name__ == "__main__":
    main()
