from math import log

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas
from iplotlib.Plot import Plot2D
from iplotlib_matplotlib.Dates import NanosecondDateFormatter
from matplotlib.axis import Tick
from matplotlib.dates import AutoDateFormatter, AutoDateLocator, ConciseDateFormatter
from matplotlib.ticker import FuncFormatter, ScalarFormatter
from pandas.plotting import register_matplotlib_converters
from utils.data import hash_code


class AutoDateLocator2(AutoDateLocator):

    def __call__(self):
        # docstring inherited
        dmin, dmax = self.viewlim_to_dt()
        locator = self.get_locator(dmin, dmax)
        print("CLO",locator)
        return locator()

    def viewlim_to_dt(self):
        vmin, vmax = self.axis.get_view_interval()
        if vmin > vmax:
            vmin, vmax = vmax, vmin
        return vmin, vmax




def date_axis():
    register_matplotlib_converters()
    x = np.array(['2020-12-11T11:26:37.000000000', '2020-12-14T11:26:37.200000000', '2020-12-14T11:26:37.400000000', '2020-12-14T11:26:37.600000000',
            '2020-12-14T11:26:37.800000000', '2020-12-14T11:26:38.000000000', '2020-12-14T11:26:38.200000000', '2020-12-14T11:26:38.400000000',
            '2020-12-14T11:26:38.600000000', '2020-12-14T11:26:38.800000000'], dtype="datetime64[ns]")
    y = np.array([7675.92578125, 7666.66650391, 7675.92578125, 7666.66650391, 7675.92578125, 7666.66650391, 7675.92578125, 7685.18505859, 7675.92578125, 7666.66650391])

    x = np.array(['2020-12-14T10:26:00.000000100', '2020-12-14T10:26:00.000000200'], dtype="datetime64[ns]")
    y = np.array([5, 10])

    x = x.astype('int64')

    print(x)

    ax = plt.subplot()
    ax.set_xlim([x[0], x[-1]])
    ax.set_autoscalex_on(False)
    formatter = NanosecondDateFormatter()
    # formatter = ScalarFormatter()
    # formatter.set_useLocale(False)
    # ax.xaxis.set_major_locator(matplotlib.ticker.AutoLocator())
    ax.xaxis.set_major_formatter(formatter)

    # auto2 = AutoDateLocator2()
    # ax.xaxis.set_major_locator(auto2)



    plt.plot(x, y)
    plt.show()



date_axis()




