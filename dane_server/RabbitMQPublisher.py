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

import pika
import sys
import json
from time import sleep
import functools
import logging
from DANE.handlers import RabbitMQHandler 

logger = logging.getLogger('DANE')

class RabbitMQPublisher(RabbitMQHandler):

    def __init__(self, config):
        super().__init__(config)

    def assign_callback(self, callback):
        self.callback = callback

    def publish(self, routing_key, task, document):
        try:
            super().publish(routing_key, task, document)
        except pika.exceptions.UnroutableError:
            fail_resp = { 'state': 422, 
                    'message': 'Unroutable task' }
            self.callback(task._id, fail_resp)
            pass
        except Exception as e:
            raise e
