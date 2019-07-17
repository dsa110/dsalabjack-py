import select
import socket
import hwmc_logging as log
import queue
import os

MODULE = os.path.basename(__file__)
SERVER_IP = 'localhost'
SERVER_PORT = 50000
BLOCK_SIZE = 1024


class MpServer:
    def __init__(self, monitor_q, log_msg_q):
        self.monitor_q = monitor_q
        self.log_msg_q = log_msg_q
        log_msg_q.put((log.INFO, MODULE, "Initializing monitor server"))
        self.stop = False

    def run_server(self):
        self.log_msg_q.put((log.INFO, MODULE, "Starting monitor server"))
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(False)
        server.bind((SERVER_IP, SERVER_PORT))
        server.listen(5)
        inputs = [server]
        outputs = []
        message_queues = {}
        mp_filter = {}

        while inputs:
            if self.stop:
                self.log_msg_q.put((log.INFO, MODULE, "Stopping monitor server"))
                break
            mon_data = []
            if not self.monitor_q.empty():
                mon_data = self.monitor_q.get()
            readable, writable, exceptional = select.select(inputs, outputs, inputs, 1)
            for s in readable:
                if s is server:
                    connection, client_address = s.accept()
                    connection.setblocking(False)
                    inputs.append(connection)
                    message_queues[connection] = queue.Queue()
                else:
                    try:
                        data = s.recv(BLOCK_SIZE)
                        data = data.decode('ascii').lower()
                        data_lines = data.splitlines()
                        for line in data_lines:
                            source, mp = line.split(',')
                            filt = (source, mp)
                            if s not in mp_filter:
                                mp_filter[s] = [filt]
                            elif filt not in mp_filter[s]:
                                mp_filter[s].append(filt)
                        if data:
                            if s not in outputs:
                                outputs.append(s)
                    except (ConnectionResetError, ConnectionAbortedError):
                        inputs.remove(s)
                        outputs.remove(s)

            for s in writable:
                if mon_data:
                    filt = mp_filter[s]
                    mjd, mp_source, mp_name, val = str(mon_data).split(',')
                    for f in filt:
                        source, mp = f
                        if source == mp_source.lower() and mp == mp_name.lower():
                            s.send(mon_data)

            for s in exceptional:
                inputs.remove(s)
                if s in outputs:
                    outputs.remove(s)
                s.close()
                del message_queues[s]
