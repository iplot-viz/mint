#!/bin/bash
# Bamboo script
# Stage 1 : Pip install

# Set up environment
source ci/st00-header.sh $* || exit 1

# Create a virtualized environment for installing mint
if [ -d "${PREFIX_DIR}" ];
then
    try rm -r ${PREFIX_DIR}
fi

try mkdir ${PREFIX_DIR}

# Test install command
try python3 -m pip install --no-deps iplotlogging/ --prefix=${PREFIX_DIR}
try python3 -m pip install --no-deps iplotdataaccess/ --prefix=${PREFIX_DIR}
try python3 -m pip install --no-deps iplotlib/ --prefix=${PREFIX_DIR}
try python3 -m pip install --no-deps iplotprocessing/ --prefix=${PREFIX_DIR}
try python3 -m pip install --no-deps iplotwidgets/ --prefix=${PREFIX_DIR}
try python3 -m pip install --no-deps . --prefix=${PREFIX_DIR}

export PYTHONPATH=${PYTHONPATH}:$(get_abs_filename "./${PREFIX_DIR}")
try python3 -c "import mint"

# Stash
tar -cvzf ${PREFIX_DIR}.tar.gz ./${PREFIX_DIR}

# Clean up
try rm -r ${PREFIX_DIR}