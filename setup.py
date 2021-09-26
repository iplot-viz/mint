# Description: Install entry-point (mint), resources and unit tests
# Author: Jaswant Sai Panchumarti

import setuptools
from mint._version import __version__

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="mint",
    setup_requires=[
        "setuptools-git-versioning"
    ],
    version_config={
        "version_callback": __version__,
        "template": "{tag}",
        "dirty_template": "{tag}.dev{ccount}.{sha}",
    },
    author="Lana Abadie",
    author_email="lana.abadie@iter.org",
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
    packages=setuptools.find_packages(where='.'),
    python_requires=">=3.8",
    install_requires=[
        "iplotlib >= 0.2.0", # bump to 0.3.0 in release/0.8.0
        "iplotDataAccess >= 0.1.0", # bump to 0.2.0 in release/0.8.0
        "iplotProcessing >= 0.1.0" # bump to 0.2.0 in release/0.8.0
    ],
    entry_points={
        'console_scripts': ['mint = mint.__main__:main', 'mint-signal-table = mint.gui.mtSignalTable:main']
    },
    package_data = {
        "mint": ["csv/*.csv", "workspaces/*"],
        "mint.gui": ["icons/*.png", "res/*.ui"],
        "mint": ["mydatasources.cfg"]
    }
)
