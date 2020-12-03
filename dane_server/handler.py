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

from elasticsearch import Elasticsearch
from elasticsearch import exceptions as EX
import json
import os
import logging
from functools import partial
from urllib.parse import urlsplit

import DANE.handlers
import threading
from DANE import Task

logger = logging.getLogger('DANE')

INDEX = 'dane-index' # TODO make configurable?

class Handler(DANE.handlers.ESHandler):

    def __init__(self, config, queue, resume_unfinished=True):
        super().__init__(config, queue)
        self.queue.assign_callback(self.callback)

        if resume_unfinished:
            logger.info("Starting Task Scheduler")
            # TODO make interval configable
            self.scheduler = TaskScheduler(handler=self, interval=10)
            self.scheduler.start()

class TaskScheduler(threading.Thread):
    def __init__(self, handler, interval=1):
        super().__init__()
        self.stopped = threading.Event()
        self.interval = interval
        self.daemon = True
        self.handler = handler

    def run(self):
        while not self.stopped.wait(self.interval):
            unfinished = self.handler.getUnfinished(only_runnable=True)
            if len(unfinished) > 0:
                for task in unfinished:
                    try:
                        Task.from_json(task).set_api(self.handler).run()
                    except Exception as e:
                        logger.exception("Error during task scheduler")
