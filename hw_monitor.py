import queue
import time
import os
import astropy.time
import hwmc_logging as log

MODULE = os.path.basename(__file__)

class Monitor_q():
    def __init__(self, file_prefix, log_msg_q):
        self.stop = False
        self.mon_q_in = queue.Queue()
        self.mon_q_out = queue.Queue()
        self.file_prefix = file_prefix
        self.log_msg_q = log_msg_q
        if not self._open_mp_file():
            raise FileNotFoundError

    def post(self, mp):
        self.mon_q_in.put(mp)

    def get(self):
        msg = self.mon_q_out.get()
        self.mon_q_out.task_done()
        return msg

    def empty(self):
        return self.mon_q_out.empty()

    def run(self):
        while not self.stop:
            if not self.mon_q_in.empty():
                item = self.mon_q_in.get()
                self.mon_q_in.task_done()
                timestamp, source, mp_packet = item
                for mp in mp_packet:
                    self.mf.write("{},{},{},{}\n".format(timestamp, source, mp, mp_packet[mp]))
                    self.mon_q_out.put("{},{},{},{}\n".format(timestamp, source, mp, mp_packet[mp]).encode('ascii'))
            self.mf.flush()
            if astropy.time.Time.now().iso[: 10] != self.file_date:
                self.mf.close()
                self._open_mp_file()
            time.sleep(0.1)

    def _open_mp_file(self):
        ut = astropy.time.Time.now().iso
        self.file_date = ut[: 10]
        mp_file_name =self.file_prefix + self.file_date + '.mp'
        try:
            self.mf = open(mp_file_name, 'a')
            self.log_msg_q.put((log.INFO, MODULE, "Opening mp storage file: {}".format(mp_file_name)))
            succeed = True
        except OSError as e:
            print("Error {} opening file '{}'".format(e, mp_file_name))
            succeed = False
        return succeed