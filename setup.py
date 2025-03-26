# Description: Install entry-point (mint), resources and unit tests
# Author: Jaswant Sai Panchumarti

import os
import sys

import setuptools

sys.path.append(os.getcwd())
import versioneer

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
)
