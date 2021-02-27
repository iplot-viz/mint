from access.dataAccess import DataAccess
from iplotlib.Signal import UDAPulse
from iplotlib.UDAAccess import UDAAccess

da = DataAccess()

UDAAccess.da = da
listDS = da.loadConfig()


# s1 = UDAPulse(datasource="codacuda", varname="CWS-SCSU-HR00:AISPARE-2169-XI", ts_start="2020-10-21T14:30:52.195", ts_end="2020-10-21T14:50:55.195")

# s1 = UDAPulse(datasource="codacuda", varname="IC-ICH1-DSRF:FWD", ts_start=1536852150000000002, ts_end=1536852150000000034)
# s1 = UDAPulse(datasource="codacuda", varname="IC-ICH1-DSRF:FWD", pulsenb=123456, ts_relative=True)
s1 = UDAPulse(datasource="codacuda", varname="BUIL-B36-VA-RT-RT1:CL0001-TT02-STATE", ts_start="2021-02-22T12:00:00.000000000", ts_end="2021-02-22T12:00:01.000000000")


print("DATA",s1.get_data())


