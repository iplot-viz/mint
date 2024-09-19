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
    try module load matplotlib/3.8.2-gfbf-2023b
    try module load VTK/9.3.0-foss-2023b
    ;;

  "intel")

    # Graphics backend requirements
    try module load matplotlib/3.8.2-iimkl-2023b
    try module load VTK/9.3.0-intel-2023b
    ;;
   *)
    echo "Unknown toolchain $toolchain"
    ;;
esac

# Graphical User Interface backend
try module load PySide6/6.6.2-GCCcore-13.2.0

# Testing/Coverage requirements
try module load coverage/7.4.4-GCCcore-13.2.0

#try module -t list 2>&1

export HOME=$PWD
echo "HOME was set to $HOME"
