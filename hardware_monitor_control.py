import hwmc_logging as log
import commands as cmds
import dsa_labjack as dlj
import time
from threading import Thread
import threading
import queue
import hw_monitor as mon
import os
from monitor_server import MpServer

MODULE = os.path.basename(__file__)

# Set up some parameters to control execution, memory allocation, and logging

SIM = False     # Simulation mode of LabJacks

ANT_CMD_Q_DEPTH = 5

log_level = log.INFO

# --------- Start main script ------------
thread_count = 1    # This starts with main thread

# Start logging
logfile_prefix = "dsa-110-test-"
log_msg_q = queue.Queue()
level = log.ALL
hw_log = log.HwmcLog(logfile_prefix, log_msg_q, level)
log_thread = Thread(target=hw_log.logging_thread)
log_thread.start()
thread_count += 1

# Start monitor point queue
mp_q = mon.Monitor_q("dsa-110-test-", log_msg_q)
monitor_thread = Thread(target=mp_q.run, name='mp_q-thread')
monitor_thread.start()
thread_count += 1

# Create the TCP/IP server and start its thread
mp_server = MpServer(mp_q, log_msg_q)
server_thread = Thread(target=mp_server.run_server, name='server_thread')
server_thread.start()
thread_count += 1

# Discover LabJack T7 devices on the network
devices = dlj.LabjackList(log_msg_q, mp_q, simulate=SIM)
ants = devices.ants
abes = devices.abes

# Set up a command queue for each antenna, these should not be deep, since there is no use case for sending multiple
# commands in rapid succession
ant_cmd_qs = {}
for ant_num, ant in ants.items():
    ant_cmd_qs[ant_num] = queue.Queue(ANT_CMD_Q_DEPTH)
    ants[ant_num].cmd_q = ant_cmd_qs[ant_num]

# Start running antenna control and monitor threads
for ant_num, ant in ants.items():
    t = Thread(target=ant.run, name='Ant-{}'.format(ant_num))
    t.start()
    thread_count += 1

# Start the command processor and command server
print("Waiting for threads to start")
while threading.activeCount() < thread_count:
    time.sleep(0.5)
print("Starting command processor")
cmd = cmds.HwmcCommands(ant_cmd_qs, log_msg_q)
cmd_thread = Thread(target=cmd.command_thread, name='cmd-thread')
cmd_thread.start()
cmd_server_thread = Thread(target=cmd.command_server_thread, name='cmd-server-thread')
cmd_server_thread.start()
thread_count += 2

while not cmd.stop_request:
    time.sleep(0.1)
cmd.stop = True

print("Stopping threads ", end='')
for ant_num, ant in ants.items():
    ant.stop = True
    print(".", end='')
time.sleep(2)

mp_server.stop = True
time.sleep(2)
mp_q.stop = True
time.sleep(2)
hw_log.stop = True

while threading.activeCount() > 1:
    print(".", end='')
    time.sleep(1.0)

print("\nFinished")
exit(0)
