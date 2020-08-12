import sys
from matplotlib.backends.qt_compat import QtCore, QtWidgets, is_pyqt5
#from iterplot.canvas import plotCanvas as ipc
from iterplot.canvas import MyCanvasFactory as ipc
from iterplot.windows import plotQtWindow  as pw

from matplotlib.backends.qt_compat import QtCore, QtWidgets, is_pyqt5



###main class inherit from QDialog to be executed
def plotData(host,varname,pulsenb,nbp=1000):
    uport=3090
    ualias="udagpfs"
    uproto="uda"
    pulses=[]
    pulses.append(pulsenb)

    myfact=ipc.MyCanvasFactory('MatplotlibQt5')
    mycanvas=myfact.getCanvas('MatplotlibQt5')
    mycanvas.clearAllVar()
    mycanvas.clearPlots(True)

    mycanvas.initLayout(1,7,5,True)
    mycanvas.addNewDS(uproto,host,uport,ualias)
    ###varname,pulsenb,startTime,endTime,isnew,procname,data source name
    mycanvas.appendVariables(varname,pulses,0,0,1,None,ualias)
    mycanvas.setAppearanceByIdx(0,varname,'symbol',"+")
    mycanvas.setPlotPpByIdx(0,'title','data from DIIID')
    

    mycanvas.setTitle("Example of using ITER data plot")
    mycanvas.FetchAndPlotD()
    #mycanvas.show()
    #mycanvas.activateWindow()
    #mycanvas.raise_()
    return mycanvas
def main():
    udah=sys.argv[1]
    varn=sys.argv[2]
    pulsenb=sys.argv[3]
    mycanvas=plotData(udah,varn,pulsenb)
    return mycanvas

                              
if __name__ == "__main__":
    qapp = QtWidgets.QApplication.instance()
    if not qapp:
        print ("qapp not defined")
        qapp = QtWidgets.QApplication(sys.argv)
    mycanvas=main()
    myplotWindows=pw.plotQtWindow()
    myplotWindows.addPlotCanvas(mycanvas)
    myplotWindows.show()
    myplotWindows.activateWindow()
    myplotWindows.raise_()
    qapp.exec_()
       
        
