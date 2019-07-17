import astropy.time
import time
import os

MODULE = os.path.basename(__file__)

ALL = 0
DEBUG = 1
INFO = 2
WARN = 3
ERROR = 4
FATAL = 5

level_str = {ALL: "ALL",
             DEBUG: "DEBUG",
             INFO: "INFO",
             WARN: "WARN",
             ERROR: "ERROR",
             FATAL: "FATAL"}


class HwmcLog:
    '''Error and message logging class for DSA-110 hardware monitoring'''
    def __init__(self, log_prefix, log_msg_q, logging_level):
        '''Create a logging class instance
        Information to be logged is put in a queue read by this process. The logging file is created
        from the prefix followed by the date, with a .log extension

        Arguments
        logprefix -- prefix to name of the file to send the logging information to
        log_msg_q -- a Queue object that this class receives its messages from
        logging_level -- minimum level to record in log file
        '''
        self.stop = False
        self.log_msg_q = log_msg_q
        self.logging_level = logging_level
        self.log_prefix = log_prefix
        if not self._open_log_file():
            raise FileNotFoundError

    def logging_thread(self):
        while not self.stop:
            while not self.log_msg_q.empty():
                (level, module, msg) = self.log_msg_q.get()
                if level >= self.logging_level:
                    ut = astropy.time.Time.now().iso
                    if level not in level_str:
                        level = FATAL
                    self.lf.write("[{0}]{{{1}}}|{2}|{3}\n".format(ut, level_str[level], module, msg))
            self.lf.flush()
            # Check to see if UT date has rolled over
            if astropy.time.Time.now().iso[: 10] != self.file_date:
                self.lf.close()
                if not self._open_log_file():
                    raise FileNotFoundError
            # Don't hog resources
            time.sleep(0.1)

        ut = astropy.time.Time.now().iso
        self.lf.write("[{0}]{{{1}}}|{2}|{3}\n".format(ut, level_str[INFO], MODULE, "Stopping logging"))
        self.lf.close()
        return

    def _open_log_file(self):
        ut = astropy.time.Time.now().iso
        self.file_date = ut[: 10]
        logfile_name =self.log_prefix + self.file_date + '.log'
        try:
            self.lf = open(logfile_name, 'a')
            self.lf.write("[{0}]{{{1}}}|{2}|{3}\n".format(ut, level_str[INFO], MODULE, "Starting logging"))
            succeed = True
        except OSError as e:
            print("Error {} opening file '{}'".format(e, logfile_name))
            succeed = False
        return succeed