import hwmc_logging as log
import socket
import select
import os

MODULE = os.path.basename(__file__)

SERVER_IP = 'localhost'
SERVER_PORT = 50001
BLOCK_SIZE = 1024

CONTINUE = 1
STOP = -1


class HwmcCommands:
    def __init__(self, cmd_qs, log_msg_q):
        self.stop = False
        self.stop_request = False
        self.cmd_qs = cmd_qs
        self.log_msg_q = log_msg_q

    def command_thread(self):
        while not self.stop:
            if not self.stop_request:
                resp = input("Command: ")
                self.log_msg_q.put((log.DEBUG, MODULE, "Command received: {}".format(resp)))
                self.log_msg_q.task_done()
                retval = self._q_command(resp)
                if retval == STOP:
                    self.stop_request = True

    def command_server_thread(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(False)
        server.bind((SERVER_IP, SERVER_PORT))
        server.listen(5)
        inputs = [server]
        outputs = []

        while not self.stop:
            readable, writable, exceptional = select.select(inputs, outputs, inputs, 1)
            for s in readable:
                if s is server:
                    connection, client_address = s.accept()
                    connection.setblocking(False)
                    inputs.append(connection)
                else:
                    try:
                        data = s.recv(BLOCK_SIZE)
                        data = data.decode('ascii').lower()
                        ant_cmds = data.splitlines()
                        # Do not check for validity; that will be done in the command processor.
                        for ant_cmd in ant_cmds:
                            self._q_command(ant_cmd)
                        if data:
                            if s not in outputs:
                                outputs.append(s)
                    except (ConnectionResetError, ConnectionAbortedError):
                        inputs.remove(s)
                        outputs.remove(s)

            for s in exceptional:
                inputs.remove(s)
                if s in outputs:
                    outputs.remove(s)
                s.close()

    def _q_command(self, cmd_in):
        c = cmd_in.strip().lower()
        line = c.split(' ')
        n = len(line)
        cmd = line[0]
        if cmd == 'stop':
            return STOP
        if n > 1:
            ant = line[1]
            ant_cmd = [cmd] + line[2:]
            if ant is not '':
                if ant == 'all' or ant == '0':
                    for q in self.cmd_qs:
                        q.put(ant_cmd)
                else:
                    try:
                        ant = int(ant)
                    except ValueError:
                        ant = -1
                    if 0 < ant and ant in self.cmd_qs:
                        self.cmd_qs[ant].put(ant_cmd)
        return CONTINUE
