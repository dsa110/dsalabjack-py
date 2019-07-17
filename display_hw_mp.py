import socket
import math
import tkinter as tk
import time

HOST_IP = 'localhost'
MP_SERVER_PORT = 50000
CMD_SERVER_PORT = 50001
SOCKET_TIMEOUT = 2.0
BLOCK_SIZE = 2048
NUM_ANTS = 110

ROW_PAD = 20
COL_PAD = 30


mps = {'drive_state': ("Drive state", 'enum', ('invalid', 'down', 'up', 'off')),
       'brake': ("Brake", 'dig', None),
       'plus_limit': ("+ Limit", 'dig', None),
       'minus_limit': ("- Limit", 'dig', None),
       'fan_err': ("Fan error", 'dig', None),
       'ant_el': ("Elevation", 'analog', "deg"),
       'nd1': ("Noise 1", 'dig', None),
       'nd2': ("Noise 2", 'dig', None),
       'foc_temp': ("Focus temp", 'analog', "'C"),
       'lna_a_current': ("LNA 1 current", 'analog', "mA"),
       'lna_b_current': ("LNA 2 current", 'analog', "mA"),
       'rf_a_power': ("RF1 power", 'analog', "dBm"),
       'rf_b_power': ("RF2 power", 'analog', "dBm"),
       'laser_a_voltage': ("Laser1 voltage", 'analog', "V"),
       'laser_b_voltage': ("Laser2 voltage", 'analog', "V"),
       'feb_a_current': ("FEB 1 current", 'analog', "mA"),
       'feb_b_current': ("FEB 2 current", 'analog', "mA"),
       'feb_a_temperature': ("FEB 1 temperature", 'analog', "°C"),
       'feb_b_temperature': ("FEB 2 temperature", 'analog', "°C"),
       'lj_temp': ("LabJack temperature", 'analog', "°C"),
       'psu_voltage': ("Power supply", 'analog', "V")}

class MpShow:
    def __init__(self):
        self.quit = False
        self.read_socket = None
        self.write_socket = None
        self.connected = False
        self.mp_data = ''
        self.ant = ''
        self.ant_num = None

        # Create a new main window, and a metnod for handling its exit
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", self.quit_callback)

        # Add a frame inside this to control edge spacing
        main_frame = self._add_main_frame()

        # Add a sub-frame for the controls, populated with the controls
        self._add_control_frame(main_frame, 1, 0)

        # Add another sub-frame for the analog monitor points
        self._add_analog_frame(main_frame, 1, 1)

        # And a frame for enumeration monitor points
        self._add_enum_frame(main_frame, 2, 1)

        # The frame for the digital (boolean) data
        self._add_dig_frame(main_frame, 2, 2)

        #  A frame for antenna commands
        self._add_cmd_frame(main_frame, 3, 0, 3)

        # And finally, the frame for displaying informational messages
        self._add_msg_frame(main_frame, 4, 0, 3)

    def _add_main_frame(self):
        main_frame = tk.Frame(self.root, relief=tk.RIDGE, bd=4)
        main_frame.grid(row=0)
        main_frame.rowconfigure(0, pad=ROW_PAD)
        label_main = tk.Label(main_frame, text=" Antenna Monitor Point Display ", font=('Arial', 14), fg='blue', bd=4,
                              bg='white', relief=tk.RAISED)
        label_main.grid(row=0, column=0, columnspan=3)
        return main_frame

    def _add_control_frame(self, main_frame, row, col):
        control_frame = tk.Frame(main_frame, relief=tk.GROOVE, bd=4)
        control_frame.grid(row=row, column=col, sticky=tk.NW+tk.SE, rowspan=2)
        control_frame.columnconfigure(0, minsize=10, pad=COL_PAD)
        control_frame.columnconfigure(1, pad=COL_PAD)
        control_frame.columnconfigure(2, pad=COL_PAD)
        control_frame.rowconfigure(0, pad=ROW_PAD)
        control_frame.rowconfigure(1, pad=ROW_PAD)
        control_frame.rowconfigure(2, pad=ROW_PAD)
        control_frame.rowconfigure(3, pad=ROW_PAD)

        # Create Tkinter variable to hold antenna number
        self.tk_ant = tk.StringVar(self.root)

        # Create a spinner for antenna number, with a label
        label_ant = tk.Label(control_frame, text="Antenna")
        label_ant.grid(row=0, column=0, sticky=tk.E)
        self.tk_ant = tk.Spinbox(control_frame, from_=1, to=110, width=6)
        self.tk_ant.grid(row=0, column=1)

        # Create a label and text display for selected antenna
        label_ant_sel = tk.Label(control_frame, text="Selected antenna")
        label_ant_sel.grid(row=1, column=0, sticky=tk.E)
        self.text_ant_sel = tk.Text(control_frame, height=1, width=6, bg='white', fg='blue')
        self.text_ant_sel.grid(row=1, column=1)

        # Add a button to start data capture, and a quit button
        add_button = tk.Button(control_frame, text="Connect", width=6, command=self.connect_callback)
        add_button.grid(row=2, column=1)
        quit_button = tk.Button(control_frame, text="Quit", width=6, command=self.quit_callback)
        quit_button.grid(row=3, column=1)

    def _add_msg_frame(self, main_frame, row, col, span=1):
        # Create a frame for messages
        msg_frame = tk.Frame(main_frame, relief=tk.GROOVE, bd=4)
        msg_frame.grid(row=row, column=col, sticky=tk.NW+tk.SE, columnspan=span)
        msg_frame.columnconfigure(0, pad=COL_PAD)
        msg_frame.rowconfigure(0, pad=ROW_PAD)

        self.msg_field = tk.Text(msg_frame, height=1, bg='white', fg='blue', font=('Courier', 8))
        self.msg_field.grid(row=0, column=0, sticky=tk.W+tk.E)

    def _add_analog_frame(self, main_frame, row, col):
        # Set up the frame for displaying analog values
        a_display_frame = tk.Frame(main_frame, relief=tk.GROOVE, bd=4)
        a_display_frame.grid(row=row, column=col, columnspan=2, sticky=tk.W)

        # Count analog monitor points
        a_cell_info = []
        analog_count = 0
        for key, val in mps.items():
            mp_name, mp_type, mp_units = val
            if mp_type == 'analog':
                a_cell_info.append((key, mp_name, mp_units))
                analog_count += 1

        n_rows = int(math.sqrt(analog_count) + 0.9999)
        n_cols = int(analog_count / n_rows + 0.9999)

        # Add in fields for monitor points
        a_title = tk.Label(a_display_frame, text="Analog Monitor Points")
        a_title.grid(row=0, column=0, columnspan=2*n_cols, sticky=tk.S)
        a_labels = []
        a_units = []
        self.a_fields = {}
        i = 0
        width = 10
        for r in range(n_rows):
            for c in range(n_cols):
                if i < analog_count:
                    current_cell_info = a_cell_info[i]
                    a_labels.append(tk.Label(a_display_frame, text=current_cell_info[1]))
                    a_labels[i].grid(row=2*r+1, column=2*c, sticky=tk.S)
                    self.a_fields[current_cell_info[0]] = tk.Text(a_display_frame, background='white', width=width,
                                                                  height=1, bd=3)
                    self.a_fields[current_cell_info[0]].grid(row=2*r+2, column=2*c, sticky=tk.N, pady=5)
                    a_units.append(tk.Label(a_display_frame, text=current_cell_info[2]))
                    a_units[i].grid(row=2*r+2, column=2*c+1, sticky=tk.W)
                    i += 1

    def _add_enum_frame(self, main_frame, row, col):
        # Set up the frame for displaying enumeration values
        e_display_frame = tk.Frame(main_frame, relief=tk.GROOVE, bd=4)
        e_display_frame.grid(row=row, column=col, sticky=tk.NW+tk.SE)
        e_display_frame.columnconfigure(0, pad=COL_PAD)
        e_display_frame.columnconfigure(1, pad=COL_PAD)
        e_display_frame.rowconfigure(0, pad=ROW_PAD)

        # Count enumeration monitor points
        e_cell_info = []
        self.e_enums = {}
        enum_count = 0
        for key, val in mps.items():
            mp_name, mp_type, enums = val
            if mp_type == 'enum':
                e_cell_info.append((key, mp_name))
                self.e_enums[key] = enums
                enum_count += 1

        n_rows = int(math.sqrt(enum_count) + 0.9999)
        n_cols = int(enum_count / n_rows + 0.9999)

        # Add in fields for monitor points
        label_enum = tk.Label(e_display_frame, text="Enumeration Monitor Points")
        label_enum.grid(row=0, column=0, columnspan=n_cols)
        e_labels = []
        self.e_fields = {}
        i = 0
        width = 10
        for r in range(n_rows):
            for c in range(n_cols):
                if i < enum_count:
                    current_cell_info = e_cell_info[i]
                    e_labels.append(tk.Label(e_display_frame, text=current_cell_info[1]))
                    e_labels[i].grid(row=2*r+1, column=c)
                    self.e_fields[current_cell_info[0]] = tk.Text(e_display_frame, background='white', width=width,
                                                                  height=1, bd=3)
                    self.e_fields[current_cell_info[0]].grid(row=2*r+2, column=c, sticky=tk.N)
                    i += 1

    def _add_dig_frame(self, main_frame, row, col):
        # Set up the frame for displaying digital values
        d_display_frame = tk.Frame(main_frame, relief=tk.GROOVE, bd=4)
        d_display_frame.grid(row=row, column=col, sticky=tk.NW+tk.SE)
        d_display_frame.columnconfigure(0, pad=COL_PAD)
        d_display_frame.columnconfigure(1, pad=COL_PAD)
        d_display_frame.rowconfigure(0, pad=ROW_PAD)

        # Count digital monitor points
        d_cell_info = []
        digital_count = 0
        for key, val in mps.items():
            mp_name, mp_type, mp_units = val
            if mp_type == 'dig':
                d_cell_info.append((key, mp_name))
                digital_count += 1

        n_rows = int(math.sqrt(digital_count) + 0.9999)
        n_cols = int(digital_count / n_rows + 0.9999)

        # Add in fields for monitor points
        label_dig = tk.Label(d_display_frame, text="Digital Monitor Points")
        label_dig.grid(row=0, column=0, columnspan=n_cols)
        labels = []
        self.d_fields = {}
        i = 0
        width = 10
        for r in range(n_rows):
            for c in range(n_cols):
                if i < digital_count:
                    current_cell_info = d_cell_info[i]
                    labels.append(tk.Label(d_display_frame, text=current_cell_info[1]))
                    labels[i].grid(row=2*r+1, column=c, sticky=tk.S)
                    self.d_fields[current_cell_info[0]] = tk.Checkbutton(d_display_frame, width=width, height=1, bd=3)
                    self.d_fields[current_cell_info[0]].grid(row=2*r+2, column=c, sticky=tk.N)
                    i += 1

    def _add_cmd_frame(self, main_frame, row, col, span=1):
        # Set up the frame for the commands to the antennas
        cmd_frame = tk.Frame(main_frame, relief=tk.GROOVE, bd=4)
        cmd_frame.grid(row=row, column=col, columnspan=span, sticky=tk.NW)
        cmd_frame.rowconfigure(0, pad=20)
        label_cmd = tk.Label(cmd_frame, text="Antenna/Frontend Controls")
        label_cmd.grid(row=0, column=0, columnspan=9, sticky=tk.W+tk.E)

        # Add the few controls needed for the antenna/frontend functions
        up_button = tk.Button(cmd_frame, text="Move up", width=8, command=self.up_callback)
        up_button.grid(row=1, column=0, padx=10, pady=10)
        down_button = tk.Button(cmd_frame, text="Move down", width=8, command=self.down_callback)
        down_button.grid(row=1, column=1, padx=10)
        stop_button = tk.Button(cmd_frame, text="Stop", width=8, command=self.stop_callback)
        stop_button.grid(row=1, column=2, padx=10)
        goto_button = tk.Button(cmd_frame, text="Go to -->", width=8, command=self.move_el_callback)
        goto_button.grid(row=1, column=3, padx=10)
        nd_a_on_button = tk.Button(cmd_frame, text="Noise 1 on", width=8, command=self.nd_a_on_callback)
        nd_a_on_button.grid(row=1, column=5, padx=10)
        nd_a_off_button = tk.Button(cmd_frame, text="Noise 1 off", width=8, command=self.nd_a_off_callback)
        nd_a_off_button.grid(row=1, column=6, padx=10)
        nd_b_on_button = tk.Button(cmd_frame, text="Noise 2 on", width=8, command=self.nd_b_on_callback)
        nd_b_on_button.grid(row=1, column=7, padx=10)
        nd_b_off_button = tk.Button(cmd_frame, text="Noise 2 off", width=8, command=self.nd_b_off_callback)
        nd_b_off_button.grid(row=1, column=8, padx=10)

        # Create an entry field for antenna elevation angle
        vcmd = cmd_frame.register(self.el_validate_callback)
        self.el_field = tk.Entry(cmd_frame, width=8, justify=tk.RIGHT, validate='all', validatecommand=(vcmd, '%P'))
        self.el_field.grid(row=1, column=4, sticky=tk.W)
        self.el_field.insert(0, '0.0')

        # Create Tkinter variable to hold requested elevation
        self.tk_el = tk.DoubleVar(self.root)

    def el_validate_callback(self, P):
        if P == '':
            return True
        try:
            ang = float(P)
        except:
            return False
        if ang < 0.0 or ang > 180.0:
            return False
        else:
            return True

    def update(self):
        mp_points = self.get_mps()
        if mp_points:
            for m in mp_points:
                try:
                    mjd, ant, mp, val = m.split(',')
                except ValueError:
                    return
                if mp in self.a_fields:
                    sval = "{: .3f}".format(float(val))
                    self.a_fields[mp].delete(1.0, tk.END)
                    self.a_fields[mp].insert(tk.END, sval)
                elif mp in self.e_fields:
                    self.e_fields[mp].delete(1.0, tk.END)
                    self.e_fields[mp].insert(tk.END, self.e_enums[mp][int(val)])
                elif mp in self.d_fields:
                    if val == '0':
                        self.d_fields[mp].deselect()
                    else:
                        self.d_fields[mp].select()
        self.root.update()

    def get_mps(self):
        # See if decoded data make sense
        try:
            rec = self.read_socket.recv(BLOCK_SIZE)
            self.mp_data = self.mp_data + rec.decode('ascii')
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

    def make_connection(self):
        self.connected = False
        self.read_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.read_socket.settimeout(SOCKET_TIMEOUT)
        self.write_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.write_socket.settimeout(SOCKET_TIMEOUT)
        try:
            self.read_socket.settimeout(10.0)
            self.read_socket.connect((HOST_IP, MP_SERVER_PORT))
            self.read_socket.settimeout(SOCKET_TIMEOUT)
            self.write_socket.connect((HOST_IP, CMD_SERVER_PORT))
            self.write_socket.settimeout(SOCKET_TIMEOUT)
            self.connected = True
        except ConnectionRefusedError:
            self.show_msg("Connection to '{}' refused".format(HOST_IP))
            self.connected = False
        if self.connected:
            self.show_msg("Connected to '{}'".format(HOST_IP))
            mp = ''
            for key in mps:
                mp = "{}{},{}\n".format(mp, self.ant, key)
            self.read_socket.sendall(mp.encode('ascii'))
            self.text_ant_sel.delete(1.0, tk.END)
            self.text_ant_sel.insert(tk.END, self.ant)

    def show_msg(self, msg):
        self.msg_field.config(state=tk.NORMAL)
        self.msg_field.delete(1.0, tk.END)
        self.msg_field.insert(tk.END, msg)
        self.msg_field.config(state=tk.DISABLED)

    def connect_callback(self):
        self.ant_num = self.tk_ant.get()
        self.ant = 'ant{}'.format(self.ant_num)
        self.make_connection()
        return

    def quit_callback(self):
        self.quit = True
        self.root.destroy()

    def up_callback(self):
        if self.ant:
            cmd = "move {} up\n".format(self.ant_num)
            self.write_socket.sendall(cmd.encode('ascii'))

    def down_callback(self):
        if self.ant:
            cmd = "move {} down\n".format(self.ant_num)
            self.write_socket.sendall(cmd.encode('ascii'))

    def stop_callback(self):
        if self.ant:
            cmd = "move {} stop\n".format(self.ant_num)
            self.write_socket.sendall(cmd.encode('ascii'))

    def move_el_callback(self):
        if self.ant:
            self.tk_el =self.el_field.get()
            cmd = "move {} {}\n".format(self.ant_num, float(self.tk_el))
            self.write_socket.sendall(cmd.encode('ascii'))

    def nd_a_on_callback(self):
        if self.ant:
            cmd = "nd {} a on\n".format(self.ant_num)
            self.write_socket.sendall(cmd.encode('ascii'))

    def nd_a_off_callback(self):
        if self.ant:
            cmd = "nd {} a off\n".format(self.ant_num)
            self.write_socket.sendall(cmd.encode('ascii'))

    def nd_b_on_callback(self):
        if self.ant:
            cmd = "nd {} b on\n".format(self.ant_num)
            self.write_socket.sendall(cmd.encode('ascii'))

    def nd_b_off_callback(self):
        if self.ant:
            cmd = "nd {} b off\n".format(self.ant_num)
            self.write_socket.sendall(cmd.encode('ascii'))


window = MpShow()
while not window.quit:
    window.update()
    t = 1 - time.time() % 1
    time.sleep(t)

print("Finished")
