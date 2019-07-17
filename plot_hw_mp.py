import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import socket
import plotitems as pi
import math

SECONDS_PER_DAY = 86400
HOST_IP, SERVER_PORT = 'localhost', 50000
SOCKET_TIMEOUT = 2.0
NUM_ANTS = 110


class MpPlotter:
    def __init__(self, read_socket, n_plots, axis_sets):
        self.num_plots = n_plots
        self.xs = {}
        self.ys = {}
        self.mjd_start = None
        self.ax = axis_sets
        self.read_socket = read_socket
        self.mp_data = ''

    def update(self, i):
        mp_points = self.get_mps()
        if mp_points:
            for m in mp_points:
                try:
                    mjd, ant, mp, val = m.split(',')
                except ValueError:
                    return
                # Times will be referenced to initial MJD, so store it here
                if not self.mjd_start:
                    self.mjd_start = float(mjd)
                # The first time a monitor point is seen, create its own storage arrays
                if not (ant, mp) in self.xs:
                    self.xs[(ant, mp)] = [(float(mjd) - self.mjd_start) * SECONDS_PER_DAY]
                    self.ys[(ant, mp)] = [float(val)]
                else:
                    self.xs[(ant, mp)].append((float(mjd) - self.mjd_start) * SECONDS_PER_DAY)
                    self.ys[(ant, mp)].append(float(val))
                # Treat single plot (possibly with multiple monitor points) differently from multiple plots
                if num_plots == 1:
                    self.ax['1'].clear()
                    self.ax['1'].set(xlabel='time (s)', ylabel='value', title='Multiple Monitor Points')
                    self.ax['1'].legend(['A simple line'])
                    for m in self.xs:
                        self.ax['1'].plot(self.xs[m], self.ys[m])
                # Multiple plots display only a single monitor point each
                else:
                    for m in self.xs:
                        self.ax[m].clear()
                        self.ax[m].set(xlabel="time (s)", ylabel="value", title="MP: {}".format(m))
                        self.ax[m].plot(self.xs[m], self.ys[m])

    def get_mps(self):
        # See if decoded data make sense
        try:
            rev = self.read_socket.recv(2048)
            self.mp_data = self.mp_data + rev.decode('ascii')
        except:
            return ''
        mp_points = []
        pos = self.mp_data.find('\n')
        while pos != -1:
            x = self.mp_data[: pos]
            mp_points.append(x)
            self.mp_data = self.mp_data[pos + 1:]
            pos = self.mp_data.find('\n')
        return mp_points


mps = ['drive_state',
       'brake',
       'plus_limit',
       'minus_limit',
       'fan_err',
       'ant_el',
       'nd1',
       'nd2',
       'foc_temp',
       'lna_a_current',
       'lna_b_current',
       'rf_a_power',
       'rf_b_power',
       'laser_a_voltage',
       'laser_b_voltage',
       'feb_a_current',
       'feb_b_current',
       'feb_a_temp',
       'feb_b_temp',
       'lj_temp',
       'psu_voltage']

plot_items = pi.PlotItems(NUM_ANTS + 1, mps)
mp_plot_list = plot_items.mp_list
if plot_items.separate_plots:
    num_plots = len(mp_plot_list)
else:
    num_plots = 1

style.use('classic')
fig = plt.figure(facecolor='white')
ax = {}
if num_plots == 1:
    ax['1'] = (fig.add_subplot(1, 1, 1))

else:
    plot_rows = int(math.sqrt(num_plots) + 0.9999)
    plot_cols = int(num_plots / plot_rows + 0.9999)
    num_pos = plot_rows * plot_cols
    for i in range(num_plots):
        ax[mp_plot_list[i]] = (fig.add_subplot(plot_rows, plot_cols, i + 1, ))


if mp_plot_list:
    connected = False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(SOCKET_TIMEOUT)

    retry = True
    while retry:
        try:
            s.settimeout(10.0)
            s.connect((HOST_IP, SERVER_PORT))
            s.settimeout(SOCKET_TIMEOUT)
            connected = True
            retry = False
        except ConnectionRefusedError:
            print("Connection to '{}' refused".format(HOST_IP))
            resp = input("Retry? <y|n>: ")
            if resp.lower() == 'y':
                retry = True
            else:
                retry = False
                connected = False
    mp = ''
    if connected:
        for item in mp_plot_list:
            mp = "{}{},{}\n".format(mp, item[0], item[1])
        print(mp)
        s.sendall(mp.encode('ascii'))

        mp_plotter = MpPlotter(s, num_plots, ax)
        ani = animation.FuncAnimation(fig, mp_plotter.update, interval=500)
        plt.show()
print("Finished")
