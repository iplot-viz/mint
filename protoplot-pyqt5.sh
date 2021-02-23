#!/bin/bash
PYVERSION="3.8"
PYVERS=` echo $PYVERSION | tr -d '.,'`
if [ ! -f /etc/scl/conf/rh-python"${PYVERS}" ]
then
    exit 1
fi
PYRUN=`python -V`

if [[ $LD_LIBRARY_PATH == *"/opt/codac/qt5/lib"* ]]
then
echo "not adding qt5"
else
export LD_LIBRARY_PATH=/opt/codac/qt5/lib:$LD_LIBRARY_PATH 
fi

if [[ $PYTHONPATH == *"/opt/codac/apps/iplotlib-qt"* ]]
then
echo "not adding qt5"
else
export PYTHONPATH=$PYTHONPATH:/opt/codac/apps/iplotlib-qt 
fi
export http_proxy=http://proxy.codac.iter.org:8080
export https_proxy=https://proxy.codac.iter.org:8080

if [[ $PYRUN == "Python 3.8"* ]]
then

python /opt/codac/apps/protoplot-pyqt5/main.py
else
scl enable rh-python${PYVERS} "python /opt/codac/apps/protoplot-pyqt5/main.py  " 
fi

