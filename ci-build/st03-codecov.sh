#!/bin/bash
# Bamboo script
# Stage 3 : Code coverage of unit tests

# Set up environment
. ci/st00-header.sh $* || exit 1

# Unzip artifact
tar -xvzf ${PREFIX_DIR}.tar.gz ./${PREFIX_DIR}

export PYTHONPATH=${PYTHONPATH}:$(get_abs_filename "./${PREFIX_DIR}/lib/python3.11/site-packages")
# run tests
coverage run --source=mint -m pytest mint

# report
coverage report -i
