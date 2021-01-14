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
import threading
from time import sleep
import functools
import logging
from DANE.handlers import RabbitMQHandler 
import DANE

logger = logging.getLogger('DANE')

class RabbitMQListener(RabbitMQHandler):

    internal_lock = threading.RLock()

    def __init__(self, config):
        self._connected = False
        super().__init__(config)

    def connect(self):
        if not self._connected:
            
            super().connect()

            self.queue = self.config.RABBITMQ.RESPONSE_QUEUE

            self.channel.basic_qos(prefetch_count=1)
            self._connected = True
            self._is_interrupted = False

    def run(self):
        logger.debug("Starting blocking response queue listener")
        if self._connected:
            for method, props, body in self.channel.consume(self.queue, 
                    inactivity_timeout=1):
                with self.internal_lock:
                    if self._is_interrupted or not self._connected:
                        break
                    if not method:
                        continue
                    self._on_response(self.channel, method, props, body)
        else:
            raise DANE.errors.ResourceConnectionError('Not connected to AMQ')

    def stop(self):
        if self._connected:
            self._is_interrupted = True

    def assign_callback(self, callback):
        self.callback = callback

    def _do_callback(self, *args):
        try:
            return self.callback(*args)
        except Exception as e:
            logger.exception('Unhandled callback error')

    def _on_response(self, ch, method, props, body):
        # TODO find way to decode correctly to JSON
        body = json.loads(body.decode("utf-8"))

        self._do_callback(props.correlation_id, body)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    def publish(self, routing_key, task, document):
        with self.internal_lock:
            try:
                super().publish(routing_key, task, document)
            except pika.exceptions.UnroutableError:
                fail_resp = { 'state': 422, 
                        'message': 'Unroutable task' }
                self.callback(task._id, fail_resp)
                pass
            except Exception as e:
                raise e
