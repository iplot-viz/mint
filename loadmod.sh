#module load IMAS
module load Python/3.6.4-intel-2018a
module load matplotlib/2.1.2-intel-2018a-Python-3.6.4
module load libMemcached/1.0.18-GCCcore-6.4.0
module load PyQt5/5.9.2-intel-2018a-Python-3.6.4
module load SWIG/3.0.12-intel-2018a-Python-3.6.4
module load CMake/3.12.1

export PYTHONPATH=$PWD/udahpc/lib:$PWD/modobj/iterplot:$PWD/modobj/userfunction:$PYTHONPATH
export LD_LIBRARY_PATH=$PWD/udahpc/lib:$LD_LIBRARY_PATH

