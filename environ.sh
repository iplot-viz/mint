#!/bin/bash

# 3-fingered-claw 
function yell () 
{ 
  echo "$0: $*" >&2
}

function die () 
{ 
  yell "$*"; exit 1
}

function try () 
{ 
  "$@" || die "cannot $*" 
}


# Default to foss toolchain
if [[ "$1" == "foss" || -z $1 ]];
then
    toolchain=foss
elif [[ "$1" == "intel" ]];
then
    toolchain=intel
fi
echo "Toolchain: $toolchain"

# Clean slate
try module purge

case $toolchain in

  "foss")
    # Graphics backend requirements
    try module load matplotlib/3.5.1-foss-2020b
    try module load VTK/9.1.0-foss-2020b
    ;;

  "intel")

    # Graphics backend requirements
    try module load matplotlib/3.5.1-intel-2020b
    try module load VTK/9.1.0-intel-2020b
    ;;
   *)
    echo "Unknown toolchain $toolchain"
    ;;
esac

# Graphical User Interface backend
try module load PySide6/6.2.3-GCCcore-10.2.0

# Testing/Coverage requirements
try module load coverage/5.5-GCCcore-10.2.0

#try module list -t 2>&1

export HOME=$PWD
echo "HOME was set to $HOME"