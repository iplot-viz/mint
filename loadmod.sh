module load matplotlib/3.3.3-intel-2020a-Python-3.8.2
module load Python/3.8.2-GCCcore-9.3.0
module load PyQt5/5.13.2-GCCcore-9.3.0-Python-3.8.2
module load libMemcached/1.0.18-GCCcore-9.3.0

# Support for gnuplot QT widget requires gnuplot binary with Qt support and widget lbrary
GNUPLOT_PATH=/home/ITER/mazurp/gnuplot/bin/bin
GNUPLOTWIDGET_PATH=/home/ITER/mazurp/tmp/iplotlib-gnuplot/qt/gnuplotwidget/gnuplotwidget/lib
# Support for UDA
UDA_PYTHON_PATH=/home/ITER/mazurp/tmp/udaclientPy38GCC9/udahpcPy38/lib/
# The plot library itself if not already in PYTHONPATH
PLOTLIBRARY_PATH=/home/ITER/mazurp/tmp/iplotlib-gnuplot/

OPENSSL_PATH=/work/imas/opt/EasyBuild/software/OpenSSL/1.0.1f-goolf-1.5.16/lib/

export UDA_HOST=io-ls-udafe01.iter.org
export PATH=${GNUPLOT_PATH}:${PATH}
export LD_LIBRARY_PATH=/usr/local/lib64:${OPENSSL_PATH}:${GNUPLOTWIDGET_PATH}:${UDA_PYTHON_PATH}:${LD_LIBRARY_PATH}
export PYTHONPATH=${UDA_PYTHON_PATH}:${PYTHONPATH}:${PLOTLIBRARY_PATH}
