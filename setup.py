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
    name="mint",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    author="Panchumarti Jaswant EXT",
    author_email="jaswant.panchumarti@iter.org",
    description="A Python Qt application for ITER Data Visualtization using the iplotlib framework",
    long_description=long_description,
    url="https://git.iter.org/scm/vis/mint.git",
    project_urls={
        "Bug Tracker": "https://jira.iter.org/browse/IDV-241?jql=project%20%3D%20IDV%20AND%20component%20%3D%20MINT",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    package_dir={"": "."},
    packages=setuptools.find_packages(where="."),
    python_requires=">=3.8",
    install_requires=[
        "iplotlogging>=0.2.1",
        "iplotlib >= 0.5.0",
        "iplotDataAccess >= 0.4.0",
        "iplotWidgets",
        "iplotProcessing >= 0.4.0",
        "psutil >= 5.8.0",
    ],
    extras_require={
        'test': ['pytest', 'coverage'],  # Test dependencies
    },
    entry_points={
        "console_scripts": [
            "mint = mint.__main__:main",
            "mint-signal-cfg = mint.gui.mtSignalConfigurator:main",
        ]
    },
    package_data={
        "mint.data": ["scsv/*", "workspaces/*", "data_signals/*", "blueprint.json"],
        "mint.gui": ["icons/*.png", "res/*.ui"],
        "mint": ["mydatasources.cfg"],
        "mint.tests": [],  # Exclude everything from the tests package
    },
)
