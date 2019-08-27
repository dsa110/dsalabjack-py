from labjack import ljm
from encoder import convert_encoder
import hwmc_logging as log
import time
from astropy.time import Time
import os
import labjack_ports as port

MODULE = os.path.basename(__file__)

NUM_SIM = 110

NO_TYPE = 0
ANT_TYPE = 1
ABE_TYPE = 2

POLLING_INTERVAL = 1


# -------------- LabJack initialization class ------------------
class LabjackList:
    def __init__(self, log_msg_q, mp_q, simulate=False):
        log_msg_q.put((log.INFO, MODULE, "Searching for LabJack T7's"))
        # Set up arrays to hold device information for discovered LabJack devices
        self.num_found = 0
        self.num_ant = 0
        self.num_abe = 0
        self.ants = {}
        self.abes = {}
        self.stop_time = 0.0
        self.move_time = 0.0
        if simulate:
            a_device_types = []
            a_connection_types = []
            a_serial_numbers = []
            a_ip_addresses = []
            self.num_found = NUM_SIM
            for i in range(NUM_SIM):
                a_device_types.append(ljm.constants.dtT7)
                a_connection_types.append(ljm.constants.ctETHERNET)
                a_serial_numbers.append("-2")
                a_ip_addresses.append("192.168.1.{}".format(i))
        else:
            try:
                (self.num_found, a_device_types, a_connection_types, a_serial_numbers, a_ip_addresses) =\
                            ljm.listAll(ljm.constants.dtT7, ljm.constants.ctTCP)
            except ljm.LJMError as e:
                log_msg_q.put((log.FATAL, MODULE, "Error searching for LabJack devices. LJMError: {}".format(e)))
                raise ljm.LJMError
        if self.num_found > 0:
            sim_ant_num = 1
            for i in range(self.num_found):
                lj_handle = None
                try:
                    lj_handle = ljm.open(a_device_types[i], a_connection_types[i], a_serial_numbers[i])
                except ljm.LJMError:
                    self.num_found -= self.num_found
                    if self.num_found <= 0:
                        return

                if simulate:
                    (lj_type, lj_location) = (ANT_TYPE, sim_ant_num)
                    sim_ant_num += 1
                else:
                    (lj_type, lj_location) = self._get_type_and_location(lj_handle)
                if lj_type == ANT_TYPE:
                    self.ants[lj_location] = DsaAntLabjack(lj_handle, lj_location, log_msg_q, mp_q)
                    self.num_ant += 1
                elif lj_type == ABE_TYPE:
                    self.abes[lj_location] = DsaAbeLabjack(lj_handle, lj_location, log_msg_q, mp_q)
                    self.num_abe += 1

    @staticmethod
    def _get_type_and_location(lj_handle):
        addr_bits = int(ljm.eReadName(lj_handle, port.ANT_ID))
        if addr_bits < 128:
            lj_type = ANT_TYPE
        else:
            lj_type = ABE_TYPE
        location = int(addr_bits & 0x7f)
        return lj_type, location


# -------------- LabJack antenna class ------------------

ABSOLUTE_ZERO = 273.15
DRIVE_STATE = {0: ' Off', 1: '  Up', 2: 'Down', 3: ' Bad'}
BRAKE_STATE = {0: ' On', 1: 'Off'}
LIMIT_STATE = {0: ' On', 1: 'Off'}

OFF = 0
UP = 1
DOWN = 2

DRIVE_RATE = 40  # deg/min
TIMEOUT = 60  # seconds timeout for elevation acquisition
ACQ_WINDOW = 0.1  # Allowable position error in deg

DRIVE_BITS = {OFF: [1, 1],
              UP: [0, 1],
              DOWN: [1, 0]}

NUM_FRAMES = 3
A_NAMES = ["AIN0", "TEMPERATURE_DEVICE_K", "DIO_STATE"]
A_WRITES = [0, 0, 0]
A_NUM_VALS = [14, 1, 1]
LEN_VALS = sum(A_NUM_VALS)


class DsaAntLabjack:
    def __init__(self, lj_handle, ant_num, log_msg_q, mp_q):
        self.stop = False
        self.lj_handle = lj_handle
        self.ant_num = ant_num
        self.valid = False
        self.log_msg_q = log_msg_q
        self.cmd_q = None
        self.mp_q = mp_q
        self.monitor_points = {'drive_state': 0,    # 0 = off, 1 = up, 2 = down
                               'brake': 0,          # 0 = off, 1 = on
                               'plus_limit': 0,
                               'minus_limit': 0,
                               'fan_err': 0,
                               'ant_el': 0.0,
                               'nd1': 0,
                               'nd2': 0,
                               'foc_temp': -273.15,
                               'lna_a_current': 0.0,
                               'lna_b_current': 0.0,
                               'rf_a_power': 0.0,
                               'rf_b_power': 0.0,
                               'laser_a_voltage': 0.0,
                               'laser_b_voltage': 0.0,
                               'feb_a_current': 0.0,
                               'feb_b_current': 0.0,
                               'feb_a_temp': 0.0,
                               'feb_b_temp': 0.0,
                               'lj_temp': -273.15,
                               'psu_voltage': 0.0}

        # Initialize LabJack settings
        self.valid = True
        self._init_labjack()
        self.log_msg_q.put((log.INFO, MODULE, "Antenna {} connected".format(self.ant_num)))

    def _init_labjack(self):
        # Analog section
        # Input voltage range
        ljm.eWriteName(self.lj_handle, "AIN_ALL_RANGE", 10.0)
        # Digital section
        # Input register for LabJack ID
        ljm.eWriteName(self.lj_handle, "FIO_DIRECTION", 0)
        # Output register for drive motor control
        ljm.eWriteName(self.lj_handle, "EIO_DIRECTION", 3)
        # Input register for drive status
        ljm.eWriteName(self.lj_handle, "CIO_DIRECTION", 0)
        # Input/output for noise diode and fan
        ljm.eWriteName(self.lj_handle, "MIO_DIRECTION", 3)

    def __del__(self):
        if self.valid is True:
            ljm.close(self.lj_handle)

    def get_data(self):
        a_values = [0] * LEN_VALS
        a_values = ljm.eNames(self.lj_handle, NUM_FRAMES, A_NAMES, A_WRITES, A_NUM_VALS, a_values)
        self.monitor_points['ant_el'] = convert_encoder(a_values[0])
        self.monitor_points['foc_temp'] = 50 * a_values[1] - 25
        self.monitor_points['lna_a_current'] = 100 * a_values[2]
        self.monitor_points['rf_a_power'] = 28.571 * a_values[3] - 90
        self.monitor_points['laser_a_voltage'] = a_values[4]
        self.monitor_points['feb_a_current'] = 1000 * a_values[5]
        self.monitor_points['feb_a_temp'] = 50 * a_values[6] - 25
        self.monitor_points['lna_b_current'] = 1000 * a_values[7]
        self.monitor_points['rf_b_power'] = 28.571 * a_values[8] - 90
        self.monitor_points['laser_b_voltage'] = a_values[9]
        self.monitor_points['feb_b_current'] = 100 * a_values[10]
        self.monitor_points['feb_b_temp'] = 50 * a_values[11] - 25
        self.monitor_points['psu_voltage'] = a_values[12]
        self.monitor_points['lj_temp'] = a_values[14] - ABSOLUTE_ZERO
        dig_val = int(a_values[15])
        self.monitor_points['drive_state'] = (dig_val >> 8) & 0b11
        self.monitor_points['nd1'] = ~(dig_val >> 20) & 0b01
        self.monitor_points['nd2'] = ~(dig_val >> 21) & 0b01
        self.monitor_points['brake'] = (dig_val >> 16) & 0b01
        self.monitor_points['plus_limit'] = (dig_val >> 17) & 0b01
        self.monitor_points['minus_limit'] = (dig_val >> 18) & 0b01
        self.monitor_points['fan_err'] = (dig_val >> 22) & 0b01
        ts = float("{:.6f}".format(Time.now().mjd))
        self.mp_q.post((ts, "ant{}".format(self.ant_num), self.monitor_points))
        return self.monitor_points

    @staticmethod
    def cmd_help():
        print("Available commands:")
        print("\thelp:\t\tGives this help")
        print("\tmove arg:\tmove the antenna\n\t\t\t\targ = up|down|stop|<angle>")
        print("\tnd arg:\tswitch noise diode\n\t\t\t\targ = off|on")

    def execute_cmd(self, cmd):
        lj_ant_cmds = {'nd': self.switch_nd,
                       'move': self.move_ant,
                       'brake': self.switch_brake,
                       'help': self.cmd_help}

        cmd_name = cmd[0]
        args = cmd[1:]
        if cmd_name in lj_ant_cmds:
            lj_ant_cmds[cmd_name](args)
        else:
            self.cmd_help()
        return

    def run(self):
        while not self.stop:
            self.get_data()
            if not self.cmd_q.empty():
                cmd = self.cmd_q.get()
                self.cmd_q.task_done()
                self.execute_cmd(cmd)
            t = time.time()
            time.sleep(POLLING_INTERVAL - t % POLLING_INTERVAL)
        self.log_msg_q.put((log.INFO, MODULE, "Antenna {} disconnecting".format(self.ant_num)))

    def switch_nd(self, pol_state):
        if len(pol_state) != 2:
            self.log_msg_q.put((log.ERROR, MODULE, "Ant {}: Invalid number of noise diode arguments"
                                .format(self.ant_num)))
            return
        (pol, state) = pol_state
        if state == 'off':
            state_val = 1
        elif state == 'on':
            state_val = 0
        else:
            msg = "Ant {}: Invalid noise diode state requested: {}".format(self.ant_num, state)
            self.log_msg_q.put((log.ERROR, MODULE, msg))
            return
        if pol == 'ab' or pol == 'both':
            msg = "Ant {}: Turning both polarizations noise diode {}".format(self.ant_num, state)
            ljm.eWriteNames(self.lj_handle, 1, [port.ND_A, port.ND_B], [state_val, state_val])
        elif pol == 'a':
            msg = "Ant {}: Turning polarization a noise diode {}".format(self.ant_num, state)
            ljm.eWriteName(self.lj_handle, port.ND_A, state_val)
        elif pol == 'b':
            msg = "Ant {}: Turning polarization b noise diode {}".format(self.ant_num, state)
            ljm.eWriteName(self.lj_handle, port.ND_B, state_val)
        else:
            msg = "Ant {}: Invalid noise diode state requested: {}".format(self.ant_num, pol)
        self.log_msg_q.put((log.ERROR, MODULE, msg))

    def switch_brake(self, state):
        if type(state) is list:
            state = state[0]
        if state == 'off':
            msg = "Ant {}: Turning brake {}".format(self.ant_num, state)
            ljm.eWriteName(self.lj_handle, port.BRAKE, 0)
        elif state == 'on':
            msg = "Ant {}: Turning brake {}".format(self.ant_num, state)
            ljm.eWriteName(self.lj_handle, port.BRAKE, 1)
        else:
            msg = "Ant {}: Invalid brake state requested: {}".format(self.ant_num, state)
        self.log_msg_q.put((log.ERROR, MODULE, msg))

    def ctrl_antenna_motor(self, state):
        if state in DRIVE_BITS:
            bits = DRIVE_BITS[state]
            ljm.eWriteNameArray(self.lj_handle, port.DRIVE, len(bits), bits)

    def move_ant(self, pos):
        if len(pos) != 1:
            msg = "Ant {}: Move needs one argument: <target angle in deg> | up | down | stop".format(self.ant_num)
            self.log_msg_q.put((log.ERROR, MODULE, msg))
            return
        pos = pos[0]
        if is_number(pos):
            pos = float(pos)
            msg = "Ant {}: Moving antenna to {} deg elevation".format(self.ant_num, pos)
            self.log_msg_q.put((log.INFO, MODULE, msg))
            self.move_time = abs(self.monitor_points['ant_el'] - pos)/ DRIVE_RATE
            self.stop_time = time.time() + TIMEOUT
            err = 0.0
            self.switch_brake('off')
            while time.time() < self.stop_time:
                err = pos - self.monitor_points['ant_el']
                if abs(err) > ACQ_WINDOW:
                    if err > 0:
                        self.ctrl_antenna_motor(UP)
                    else:
                        self.ctrl_antenna_motor(DOWN)
                    time.sleep(0.1)
                    self.get_data()
                else:
                    break
            self.ctrl_antenna_motor(OFF)
            self.switch_brake('on')
            if abs(err) > ACQ_WINDOW:
                msg = "Ant {}: Move timed out".format(self.ant_num)
            else:
                msg = "Ant {}: Elevation acquired".format(self.ant_num)

            self.log_msg_q.put((log.ERROR, MODULE, msg))
        else:
            if pos == 'up':
                self.switch_brake('off')
                msg = "Ant {}: Moving up".format(self.ant_num)
                self.ctrl_antenna_motor(UP)
            elif pos == 'down':
                self.switch_brake('off')
                msg = "Ant {}: Moving down".format(self.ant_num)
                self.ctrl_antenna_motor(DOWN)
            elif pos == 'stop' or pos == 'off':
                msg = "Ant {}: Stopping".format(self.ant_num)
                self.ctrl_antenna_motor(OFF)
                self.switch_brake('on')
            else:
                msg = "Ant {} Invalid argument for 'move': {}. Should be [up|down|stop|<angle>"\
                    .format(self.ant_num, pos)
            self.log_msg_q.put((log.INFO, MODULE, msg))

    def write_mp_data(self, filename, timestamp, ant_num, mp_data, first=False, append=False):
        if first:
            if append:
                data_file = open(filename, 'a+')
            else:
                data_file = open(filename, 'w+')
                data_file.write("time,ant_num")
                for k, v in mp_data.items():
                    data_file.write(",{}".format(k))
                data_file.write("\n")
        else:
            data_file = open(filename, 'a+')
            data_file.write("{:.8f},{:03d}".format(timestamp, ant_num))
            for k, v in mp_data.items():
                data_file.write(",{:.4f}".format(v))
            data_file.write("\n")
        data_file.close()


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


# -------------- LabJack analog backend class ------------------

class DsaAbeLabjack:
    def __init__(self, device_type, connection_type, serial_number, mp_q):
        self.valid = False
        self.mp_q = mp_q
        self.monitor_points = {'drive_state': 0,  # 0 = off, 1 = up, 2 = down
                               'brake': 0,  # 0 = off, 1 = on
                               'plus_limit': 0,
                               'minus_limit': 0,
                               'ant_el': 0.0,
                               'foc_temp': -273.15,
                               'rf_a_power': -100.0,
                               'rf_b_power': -100.0,
                               'laser_a_current': 0.0,
                               'laser_b_current': 0.0,
                               'laser_a_opt_power': 0.0,
                               'laser_b_opt_power': 0.0,
                               'psu_a_volt': 0.0,
                               'psu_b_volt': 0.0,
                               'box_temp': -273.15}
        # Open a LabJack
        try:
            self.lj_handle = ljm.open(device_type, connection_type, serial_number)
        except ljm.LJMError:
            self.valid = False
            return  # To be replaced with a raise exception?
        self.valid = True
        print("Hello from analog backend")

    def __del__(self):
        if self.valid is True:
            ljm.close(self.lj_handle)
        print("Goodbye from analog backend")

    def get_data(self):
        if self.valid is True:
            analog_vals = ljm.eReadNameArray(self.lj_handle, "AIN0", 9)
            self.monitor_points['ant_el'] = convert_encoder(analog_vals[0])
        return self.monitor_points
