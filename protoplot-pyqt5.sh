#!/bin/bash
PYVERSION="3.8"
PYVERS=` echo $PYVERSION | tr -d '.,'`
if [ ! -f /etc/scl/conf/rh-python"${PYVERS}" ]
then
    exit 1
fi 
scl enable rh-python${PYVERS} bash
python /opt/codac/apps/protoplot-pyqt5/main.py

