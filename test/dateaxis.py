import matplotlib.pyplot as plt
import numpy as np
from iplotlib.Plot import Plot2D
from matplotlib.axis import Tick
from matplotlib.dates import AutoDateFormatter, AutoDateLocator
from pandas.plotting import register_matplotlib_converters
from utils.data import hash_code


class AutoDateLocator2(AutoDateLocator):

    def get_locator(self, dmin, dmax):

        loc = super().get_locator(dmin, dmax)
        print("** LOCATOR",loc)
        return loc

def hide_xais_with_grid():
    ax = plt.subplot()

    ax.grid(True)
    # ax.get_xaxis().set_visible(False)

    for tic in ax.get_xaxis().get_major_ticks():
        print("MAOR TICK",tic)
        t:Tick = tic
        t.tick1line.set_visible(False)
        t.tick2line.set_visible(False)
        t.label1.set_visible(False)
        t.label2.set_visible(False)

    plt.plot([1, 2, 3, 4, 5])
    plt.show()


def date_axis():
    register_matplotlib_converters()
    # x = np.array(['2020-12-14T11:26:37.000000000', '2020-12-14T11:26:37.200000000', '2020-12-14T11:26:37.400000000', '2020-12-14T11:26:37.600000000',
    #         '2020-12-14T11:26:37.800000000', '2020-12-14T11:26:38.000000000', '2020-12-14T11:26:38.200000000', '2020-12-14T11:26:38.400000000',
    #         '2020-12-14T11:26:38.600000000', '2020-12-14T11:26:38.800000000'], dtype="datetime64[ns]")
    x = np.array(['2020-12-14T11:26:37.000000000', '2020-12-14T11:26:37.200000000', '2020-12-14T11:26:37.400000000', '2020-12-14T11:26:37.600000000', '2020-12-14T11:26:37.800000000',
                  '2020-12-14T11:26:38.000000000', '2020-12-14T11:26:38.200000000', '2020-12-14T11:26:38.400000000', '2020-12-14T11:26:38.600000000', '2020-12-14T11:26:38.800000000'],
                 dtype="datetime64[ns]")
    # x = np.array(['2020-12-14T11:26:37.000000000', '2020-12-14T11:26:38.200000000', '2020-12-14T11:26:39.400000000', '2020-12-14T11:26:40.600000000', '2020-12-14T11:26:41.800000000',
    #               '2020-12-14T11:26:42.000000000', '2020-12-14T11:26:43.200000000', '2020-12-14T11:26:44.400000000', '2020-12-14T11:26:45.600000000', '2020-12-14T11:26:46.800000000'],
    #              dtype="datetime64[ns]")

    y = np.array([7675.92578125, 7666.66650391, 7675.92578125, 7666.66650391, 7675.92578125, 7666.66650391, 7675.92578125, 7685.18505859, 7675.92578125, 7666.66650391])

    ax = plt.subplot()
    print("CUR1",ax.get_xaxis().get_major_formatter(),"and",ax.get_xaxis().get_major_locator())
    locator = AutoDateLocator2()
    formatter = AutoDateFormatter(locator)
    # ax.get_xaxis().set_major_formatter(formatter)
    # ax.get_xaxis().set_major_locator(locator)
    print("CUR2", ax.get_xaxis().get_major_formatter(), "and", ax.get_xaxis().get_major_locator())
    # ax.get_xaxis().set_minor_formatter(formatter)
    # ax.get_xaxis().set_major_locator(locator)

    ax.grid(True)
    # ax.xaxis_date(True)

    plt.plot(x, y)
    # plt.tight_layout()

    plt.show()

# hide_xais_with_grid()
# date_axis()

plot_props = ["title"]
p1 = Plot2D(title="Hello")
p2 = Plot2D(title="Hello2")
print(hash_code(p1, plot_props))
print(hash_code(p2, plot_props))



