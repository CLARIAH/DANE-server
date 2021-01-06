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
from DANE import Task

logger = logging.getLogger('DANE')

INDEX = 'dane-index' # TODO make configurable?

class Handler(DANE.handlers.ESHandler):

    def __init__(self, config, queue):
        super().__init__(config, queue)
        self.queue.assign_callback(self.callback)
