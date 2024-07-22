# Description: The MINT application to interact and explore data signals from codac databases and IMAS IDSs
# Author: Jaswant Sai Panchumarti

import sys
from mint.app import create_app, dirs, run_app
import os
import subprocess
def is4K():
    try:
        process=subprocess.run(["xrandr"],stdout=subprocess.PIPE,check=True)
        lines=process.stdout.decode('utf-8').splitlines()
        ##we need to look at the first line
        currents=lines[0].split(",")[1].strip()
        resol=currents.split(" ")
        resx=int(resol[1])
        resy=int(resol[3])
       

        if resy%2160==0 and resx%3840==0:
            
            return True
        else:
            return False
        
    except subprocess.CalledProcessError as cpe:
        print("Error with xrandr ",cpe)
        return False    
    except ValueError as ve:
        print("Error with parsing output of xrandr ",ve)
        return False
    
def loadEnv(fpath):
    with open(fpath,'r') as f:
        line=f.readline()
        while line:
            keyval=line.split("=")
            if(len(keyval)==2):
                os.environ[keyval[0]]=keyval[1]
            line=f.readline()

def main():
    if is4K() == True:
        print("Found a 4K screen settings QT param")
        if os.environ.get('MINT_4K_CONFIG') is not None and os.path.isfile(os.environ.get('MINT_4K_CONFIG')):
            print("Found an environment file for MINT")
            loadEnv(os.environ.get('MINT_4K_CONFIG'))
            
        else:
            os.environ['QT_SCALE_FACTOR']="1.8"
            os.environ['QT_FONT_DPI']="50"
        print(" Applying QT_SCALE="+os.environ.get('QT_SCALE_FACTOR')+ " QT FONT "+os.environ.get('QT_FONT_DPI'))
           
    else:
        print("It is not a 4K screen")
    qApp, args = create_app(sys.argv)
    dirs.update(__file__)
    sys.exit(run_app(qApp, args))


if __name__ == "__main__":
    main()
