"""
This example shows that when only one point of a plot is given when using ConciseDateFormatter the x range is +/i 2 years
"""

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime,timedelta
import calendar
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, DAILY, DateLocator,WeekdayLocator,DayLocator

currTimeDelta1 = datetime.utcnow() - timedelta(days=1)
currTimeDelta2= datetime.utcnow() + timedelta(days=1)

vmin = int(currTimeDelta1.timestamp()/3600/24)
vmax= int(currTimeDelta2.timestamp()/3600/24)
x = np.array([datetime.utcnow().isoformat(timespec='seconds')], dtype="datetime64[ns]")
y1 = [10]
y2 = [20]

print(vmin)
fig, ax = plt.subplots()
# ax.grid(True)
locator = AutoDateLocator()

ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
ax.set_xlim(vmin,vmax)
#ax.xaxis.set_major_formatter((locator))
ax.plot(x, y1, marker="x")
ax.plot(x, y2, marker="o")
xmin, xmax = ax.get_xlim()

print (xmin)
print(xmax)

plt.show()
