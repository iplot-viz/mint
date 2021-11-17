#!/bin/bash
PYVERSION="3.8"
PYVERS=` echo $PYVERSION | tr -d '.,'`
PYRUN=$(python -V 2>&1)

#if [[ $LD_LIBRARY_PATH == *"/opt/codac/qt5/lib"* ]]
#then
#echo "not adding qt5"
#else
#export LD_LIBRARY_PATH=/opt/codac/qt5/lib:$LD_LIBRARY_PATH 
#fi

if [[ $PYTHONPATH == *"/opt/codac/apps/mint"* ]]
then
echo "not adding mint "
else
#export PYTHONPATH=$PYTHONPATH:/opt/codac/apps/iplotlib-qt/iplotlib:/opt/codac/apps/iplotlib-qt/iplotlogging:/opt/codac/apps/iplotlib-qt/iplotprocessing:/opt/codac/apps/iplotlib-qt/iplotdataccess:/opt/codac/apps/
export PYTHONPATH=$PYTHONPATH:/opt/codac/apps/mint
fi
export http_proxy=http://proxy.codac.iter.org:8080
export https_proxy=https://proxy.codac.iter.org:8080

if [[ $PYRUN == "Python 3.8"* ]]
then

python /opt/codac/apps/mint/mint/__main__.py
else
/usr/bin/python3.8 /opt/codac/apps/mint/mint/__main__.py  
fi

