# Copyright 2020-present, Netherlands Institute for Sound and Vision (Nanne van Noord)
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##############################################################################

from functools import wraps

import json
import os
import sys, os
import logging
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import quote
import requests

from dane_server.handler import Handler, INDEX
from dane_server.RabbitMQListener import RabbitMQListener
from dane_server.RabbitMQPublisher import RabbitMQPublisher
import DANE
from DANE.config import cfg
import threading

def main():
    logger = logging.getLogger('DANE')
    logger.setLevel(cfg.LOGGING.LEVEL)
    # create file handler which logs to file
    if not os.path.exists(os.path.realpath(cfg.LOGGING.DIR)):
        os.makedirs(os.path.realpath(cfg.LOGGING.DIR), exist_ok=True)

    fh = TimedRotatingFileHandler(os.path.join(
        os.path.realpath(cfg.LOGGING.DIR), "DANE-server.log"), 
        when='W6', # start new log on sunday
        backupCount=3)
    fh.setLevel(cfg.LOGGING.LEVEL)
    # create console handler 
    ch = logging.StreamHandler()
    ch.setLevel(cfg.LOGGING.LEVEL)
    # create formatter and add it to the handlers
    formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

    messageQueue = RabbitMQListener(cfg)
    handler = Handler(config=cfg, queue=messageQueue)
    logger.info('Connected to ElasticSearch')
    logger.info('Connecting to RabbitMQ')

    # only start task scheduler if we run without supervisor
    # or if we're the first (this does restrict naming scheme 
    # used in supervisor TODO
    if ('SUPERVISOR_PROCESS_NAME' not in os.environ or
        os.environ['SUPERVISOR_PROCESS_NAME'].endswith('_00')): 
        publishQueue = RabbitMQPublisher(cfg)
        s_handler = Handler(config=cfg, queue=publishQueue)
        # TODO make interval configable
        scheduler = TaskScheduler(handler=s_handler, logger=logger, interval=5)
        scheduler.run()
    else:
        logger.info(os.environ['SUPERVISOR_PROCESS_NAME'] + ' started without task scheduler')

    messageQueue.run() # blocking from here on

class TaskScheduler(threading.Thread):
    def __init__(self, handler, logger, interval=1):
        super().__init__()
        self.stopped = threading.Event()
        self.interval = interval
        self.daemon = True
        self.handler = handler
        self.logger = logger

    def run(self):
        self.logger.info("Starting Task Scheduler")
        while not self.stopped.wait(self.interval):
            unfinished = self.handler.getUnfinished(only_runnable=True)
            if len(unfinished) > 0:
                for task in unfinished:
                    try:
                        DANE.Task.from_json(task).set_api(self.handler).run()
                    except Exception as e:
                        self.logger.exception("Error during task scheduler")
            else:
                # for heartbeat
                self.handler.queue.connection.process_data_events() 

if __name__ == '__main__':
    main()
