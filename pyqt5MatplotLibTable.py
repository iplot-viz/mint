import sys

from PyQt5.QtWidgets import QApplication, QDialog,QMainWindow, QMenu, QLabel, QTabWidget, QVBoxLayout, QStyleFactory, QSizePolicy, QMessageBox, QWidget, QPushButton,QComboBox,QLineEdit,QGridLayout,QVBoxLayout,QHBoxLayout,QGroupBox
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QRegExp,Qt
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import QTableWidget,QTableWidgetItem,QFormLayout,QVBoxLayout
#from iterplot.canvas import plotCanvas as ipc
from iterplot.canvas import MyCanvasFactory as ipc
from iterplot.canvas import mouseToolbar as mt
from iterplot.processing import processing as pr
import userfunction.myfunc.simpleFunction
import random


udahost ="10.153.0.204"


###main class inherit from QDialog to be executed
class App(QDialog):
#### INIT PART #####################################
    def __init__(self,parent=None):
        super(App,self).__init__(parent)
        self.nbr=20
        self.nbc=4
        #self.mtb=mt.MouseToolbar()
        self.uhost="10.153.0.204"
        self.uport=3090
        self.ualias="udagpfs"
        self.uproto="uda"
        styleComboBox = QComboBox()
        styleComboBox.addItems(QStyleFactory.keys())
        styleLabel = QLabel("&Style:")
        styleLabel.setBuddy(styleComboBox)

        #self.dataAcc=DataAccess()
        #self.dataAcc.connect(udahost)
        #if self.dataAcc.errcode!=0:
         #   print ("Exiting cannot connect to UDA server")
          #  QMessageBox.about(self, "ERROR", "Cannot connect to UDA server")
           # sys.exit(-1)

        topLayout = QHBoxLayout()
        topLayout.addWidget(styleLabel)
        topLayout.addWidget(styleComboBox)
        
        self.createLeftVarGroupBox()
        self.createRightGroupBox()
        self.createTimeInfo()
        self.createApply()
        ##universla grid layout divides in row and columns
        mainLayout=QGridLayout()
        ##row/col/rowpsan/colspan
        #here the layout
        ########
        ### ###

        mainLayout.addLayout(topLayout,0,0,1,2)
        mainLayout.addWidget(self.leftVarGroupBox,1,0)
        mainLayout.addWidget(self.leftTimeGroupBox,2,0)
        mainLayout.addWidget(self.leftApplyGroupBox,3,0)
        mainLayout.addWidget(self.rightGroupBox,1,1,3,1)
        mainLayout.setRowStretch(1,1)
        mainLayout.setColumnStretch(0,1)
        mainLayout.setColumnStretch(1,2)
        self.setLayout(mainLayout)
        self.setWindowTitle("Example of combining PyQt and Matplotlib")
        self.mcursor=None
        self.funcdict={}
        self.show()
        self.createFunctionList()
    #################################################################################
    def createTable(self,nbrows=5,nbcol=3):
        self.tableWidget = QTableWidget()
        #self.tableWidget.horizontalHeaderItem().setTextAlignment(Qt.AlignHCenter)
        self.tableWidget.setRowCount(nbrows)
        self.tableWidget.setColumnCount(nbcol)
        self.tabHeader=('Variable Name','Plot','Transform','Status')
        self.tableWidget.setHorizontalHeaderLabels(self.tabHeader)
        for i in range(nbrows):
            comBox=QComboBox()
            comBox.addItems(['New', 'Shared'])
            self.tableWidget.setCellWidget(i,1,comBox)



    def createApply(self):
        self.leftApplyGroupBox=QGroupBox()
        plotButton =QPushButton("Plot Data")
        plotButton.clicked.connect(self.plotAction)
        l1=QVBoxLayout()
        l1.addWidget(plotButton)
        self.leftApplyGroupBox.setLayout(l1)

    def createTimeInfo(self):
        self.leftTimeGroupBox=QGroupBox("Time information")
        self.tabs = QTabWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tabs.addTab(self.tab1,"Pulse Information")
        self.tabs.addTab(self.tab2,"Absolute Timestamp")
        layoutP = QFormLayout()
        
        self.pulseText = QLineEdit()
        pulseLabel = QLabel("Pulse(s) number:")
        #reg_ex=QRegExp("[0-9]*")
        #pulseValidator = QRegExpValidator(reg_ex,self.pulseText)
        #self.pulseText.setValidator(pulseValidator)
        #pulseLabel.setBuddy(self.pulseText)
        
        layoutP.addRow("Pulse number",self.pulseText)
        self.tab1.setLayout(layoutP)
              
        self.timeStart=QLineEdit('2020-04-16T12:00:00')
        timeSLabel=QLabel("Start Time")
        self.timeEnd=QLineEdit('2020-04-16T18:00:00')
        timeELabel=QLabel("End Time")

        timeSLabel.setBuddy(self.timeStart)
        timeELabel.setBuddy(self.timeEnd)
        layout=QGridLayout()
        #layout.addWidget(pulseLabel,0,0,1,2)
        #layout.addWidget(self.pulseText,0,2,1,-1)
        layout.addWidget(timeELabel,1,0)
        layout.addWidget(self.timeStart,1,1)
        layout.addWidget(timeSLabel,1,2)
        layout.addWidget(self.timeEnd,1,3)
        self.tab2.setLayout(layout)
        l1=QVBoxLayout()
        l1.addWidget(self.tabs)
        self.leftTimeGroupBox.setLayout(l1)


     #########################declare your user defined functions ###################
    def createFunctionList(self):
        myproc='myLinearFunction'
        #self.args=[str(scale),str(offset),"dataY"]
        types=["D","D","P1Y"]
        outargs=["O0Y"]
        args=[]
        myprocdict={}
        linProc=pr.myProc()
        linProc.setDef(myproc,3,args,types,outargs)
        self.funcdict.update({myproc: linProc})
        myprocdict.update({ myproc:userfunction.myfunc.simpleFunction.myLinearFunction})
        linProc.setExec(myprocdict)


     ####################LEFT with input from users#####################
    def createLeftVarGroupBox(self):
        self.leftVarGroupBox=QGroupBox("What to plot?")
        #self.varTextInput = QLineEdit('Variable Name')
        #self.varTextInput.editingFinished.connect(self.resizeToContent)
        #varLabel = QLabel("Variable name :")
        #varLabel .setBuddy(self.varTextInput)
        #self.pulseText = QLineEdit()
        #pulseLabel = QLabel("Pulse number:")
        #reg_ex=QRegExp("[0-9]*")
        #pulseValidator = QRegExpValidator(reg_ex,self.pulseText)
        #self.pulseText.setValidator(pulseValidator)
        #pulseLabel.setBuddy(self.pulseText)
        #self.varTextScale = QLineEdit("1")
        #scaleLabel=QLabel("Scale: ")
        #scaleLabel.setBuddy(self.varTextScale)
       
        #self.varTextOffset = QLineEdit("0")
        #offsetLabel=QLabel("Offset : ")
        #offsetLabel.setBuddy(self.varTextOffset)

        #self.varTextOffset.setValidator(pulseValidator)
        #self.varTextScale.setValidator(pulseValidator)
        #plotButton =QPushButton("Plot Data")
        #plotButton.clicked.connect(self.plotAction)
        #layout=QGridLayout()
        layout=QVBoxLayout()
        self.createTable(self.nbr,self.nbc)
        #layout.addWidget(varLabel,0,0,1,2)
        #layout.addWidget(self.varTextInput,0,2,1,-1)
        #layout.addWidget(pulseLabel,1,0,1,2)
        #layout.addWidget(self.pulseText,1,2,1,2)
        #layout.addWidget(scaleLabel,2,0)
        #layout.addWidget(self.varTextScale,2,1)
        #layout.addWidget(offsetLabel,2,2)
        #layout.addWidget(self.varTextOffset,2,3)

        #layout.addWidget(plotButton,3,1,Qt.AlignHCenter)
        layout.addWidget(self.tableWidget)
        self.leftVarGroupBox.setLayout(layout)
        
    
    def createRightGroupBox(self):
        self.rightGroupBox=QGroupBox("Plotting area")
        self.mtb=mt.MouseToolbar()
        #self.mycanvas=ipc.PlotCanvas()
        self.fact=ipc.MyCanvasFactory('MatplotlibQt5')
        self.mycanvas=self.fact.getCanvas('MatplotlibQt5')
        self.mycanvas.addNewDS(self.uproto,self.uhost,self.uport,self.ualias)
        layout=QGridLayout()
        layout.setSpacing(1)
        layout.addWidget(self.mtb,1,0)
        layout.addWidget(self.mycanvas,2,0,6,1)
        self.rightGroupBox.setLayout(layout)
        self.mtb.mouseModeValue[str].connect(self.changeMouseMode)
    def changeMouseMode(self,value):
        self.mycanvas.setMouseMode(value)
        print ("mouse has been updated %s"%(value))
    def parsePulse(self,pulsen):
        pulses=[]
        if pulsen!=None and len(pulsen)>0 :
            pulses=pulsen.split(",")
        return pulses
    def readTable(self):
        j=0

        pulsenb=self.pulseText.text()
        pulses=self.parsePulse(pulsenb)
        self.mycanvas.clearAllVar()
        self.mycanvas.clearPlots(True)
        for i in range(self.nbr):
            #QTableWidgetItem
            if self.tableWidget.item(i,0)==None:
                break

            qvar=self.tableWidget.item(i,0).text()
            qplot=self.tableWidget.cellWidget(i,1).currentText()
            #if self.tableWidget.item(i,1)==None:
             #   qplot="New"
            #else:
             #   qplot=self.tableWidget.item(i,1).currentText()

            print ("new one "+qplot)
            if self.tableWidget.item(i,2)==None:
                qtrans=None
            else:
                qtrans=self.tableWidget.item(i,2).text()

            if qvar=="" or len(qvar)<1:
                break
            if qplot=="New":
                print("new 11")
                self.mycanvas.appendSignals(qvar,pulses,0,0,1,qtrans,self.ualias)
                self.mycanvas.setAppearanceByIdx(j,qvar,'symbol',"+")
                self.mycanvas.setPlotPpByIdx(j,'title','plot title AA')
                j=j+1
            else:
                self.mycanvas.appendSignals(qvar,pulses,0,0,0,qtrans,self.ualias)
        return j
    def writeSigStatus(self):
        return self.mycanvas.getSignalStatuses()
    def plotAction(self):
        nt=self.readTable()
        print ("ntot=%d"%(nt))
        if nt ==0:
            QMessageBox.about(self, "Error", "While parsing the table, no variable found")
        self.mycanvas.initLayout(nt,7,5,True)

        #self.mycanvas.show()

        #pulsenb=self.pulseText.text()
        #scale=self.varTextScale.text()
        #offset=self.varTextOffset.text()
        #myproc='myLinearFunction'
        #args=[str(scale),str(offset),"dataY"]
        #self.funcdict[myproc].setArgs(args)
        #self.mycanvas.plot(udahost,varname,pulsenb,0,0,self.funcdict[myproc])
        #self.mycanvas.setTitle("Example of data from DIIID")
        #self.mycanvas.setAppearanceByIdx(self,0,signame,propn,propv)
        self.mycanvas.fetchAndPlotD()
        self.mycanvas.setTitle("Example of data from DIIID")
        #self.mycanvas.show()
        #if self.mycanvas.errcode==-1:
         #   QMessageBox.about(self, "Error", "No data found")
        self.mystatuses=[]
        self.mystatuses=self.writeSigStatus()
        self.updateTableStatCol()
    def updateTableStatCol(self):
        sidx=self.tabHeader.index('Status')
        print("sidx=%d and lenstat=%d"%(sidx,len(self.mystatuses)))
        for i in range(len(self.mystatuses)):
            print ("i=%d"%(i))
            if self.tableWidget.item(i,sidx)==None:
                self.tableWidget.setItem(i,sidx,QTableWidgetItem(self.mystatuses[i]))
            else:
                self.tableWidget.item(i,sidx).setText(self.mystatuses[i])
            
    def resizeToContent(self):
        text=self.varTextInput.text()
        fm = self.varTextInput.fontMetrics()
        w=fm.boundingRect(text).width()
        self.varTextInput.resize(w+10,self.varTextInput.height())

       
        
if __name__ == '__main__':

    app = QApplication(sys.argv)
    
    ex = App()
    sys.exit(app.exec_())
