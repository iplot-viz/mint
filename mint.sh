#!/bin/bash
PYVERSION="3.8"
PYVERS=` echo $PYVERSION | tr -d '.,'`
PYRUN=$(python -V 2>&1)


if [[ $PYTHONPATH == *"/opt/codac/apps/mint"* ]]
then
echo "not adding mint "
else
export PYTHONPATH=$PYTHONPATH:/opt/codac/apps/mint
fi
export http_proxy=http://proxy.codac.iter.org:8080
export https_proxy=https://proxy.codac.iter.org:8080

if [[ $PYRUN == "Python 3.8"* ]]
then

python /opt/codac/apps/mint/mint/__main__.py $@
else
/usr/bin/python3.8 /opt/codac/apps/mint/mint/__main__.py  $@
fi

