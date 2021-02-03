"""
This example shows that when only one point of a plot is given when using ConciseDateFormatter the x range is +/i 2 years
"""

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

from matplotlib.dates import AutoDateLocator, ConciseDateFormatter


x = np.array([datetime.now().isoformat(timespec='seconds')], dtype="datetime64[ns]")
y1 = [10]
y2 = [20]


fig, ax = plt.subplots()
# ax.grid(True)
ax.xaxis.set_major_formatter(ConciseDateFormatter(AutoDateLocator))

ax.plot(x, y1, marker="x")
ax.plot(x, y2, marker="o")

plt.show()
