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

logger = logging.getLogger('DANE')

class RabbitMQListener(RabbitMQHandler):

    internal_lock = threading.RLock()

    def __init__(self, config):
        super().__init__(config)

    def connect(self):
        if not hasattr(self, 'connection') or \
            not self.connection or self.connection.is_closed:
            
                super().connect()

                self.channel.basic_consume(
                    queue=self.config.RABBITMQ.RESPONSE_QUEUE,
                    on_message_callback=self._on_response,
                    auto_ack=False)

    def _process_data_events(self):
        while True:
            with self.internal_lock:
                try:
                    self.connection.process_data_events()
                except (pika.exceptions.StreamLostError,
                        pika.exceptions.ConnectionClosedByBroker) as e:
                    logger.warning(
                            'RabbitMQ connection interrupted, reconnecting')
                    self.connect()
                except Exception as e:
                    logger.exception('RabbitMQ connection lost')
                    raise e
            sleep(0.1)

    def run(self):
        logger.debug("Starting blocking queue listener")
        self._process_data_events()

    def stop(self):
        self.channel.stop_consuming()

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

        cb = functools.partial(self._do_callback, 
                props.correlation_id, body)
        self.connection.add_callback_threadsafe(cb)
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
