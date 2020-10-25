module load matplotlib/3.2.1-intel-2020a-Python-3.8.2
module load Python/3.8.2-GCCcore-9.3.0
module load PyQt5/5.13.2-GCCcore-9.3.0-Python-3.8.2
module load libMemcached/1.0.18-GCCcore-9.3.0

#This app requies gnuplot binary with qt terminal support
GNUPLOT_PATH=/home/ITER/mazurp/gnuplot/bin/bin
GNUPLOTWIDGET_PATH=/home/ITER/mazurp/iplotlib-gnuplot/qt/gnuplotwidget/gnuplotwidget/lib
UDA_PYTHON_PATH=/home/ITER/mazurp/udaclientPy38GCC9/udahpcPy38/lib/

OPENSSL_PATH=/work/imas/opt/EasyBuild/software/OpenSSL/1.0.1f-goolf-1.5.16/lib/

export UDA_HOST=10.153.0.204
export PATH=${GNUPLOT_PATH}:${PATH}
export LD_LIBRARY_PATH=${OPENSSL_PATH}:${GNUPLOTWIDGET_PATH}:${UDA_PYTHON_PATH}:${LD_LIBRARY_PATH}
export PYTHONPATH=${UDA_PYTHON_PATH}:${PYTHONPATH}