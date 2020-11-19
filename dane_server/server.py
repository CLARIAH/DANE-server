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
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import quote
import requests

from dane_server.handler import Handler, INDEX
from dane_server.RabbitMQListener import RabbitMQListener
import DANE
from DANE.config import cfg

def main():
    logger = logging.getLogger('DANE')
    logger.setLevel(cfg.LOGGING.LEVEL)
    # create file handler which logs to file
    if not os.path.exists(os.path.realpath(cfg.LOGGING.DIR)):
        os.mkdir(os.path.realpath(cfg.LOGGING.DIR))

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
    messageQueue.run() # blocking from here on

if __name__ == '__main__':
    main()
