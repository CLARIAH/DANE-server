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

MAX_RETRY = 8
RETRY_INTERVAL = 2 # seconds

logger = logging.getLogger('DANE-server')

class RabbitMQUtil():

    internal_lock = threading.RLock()

    def __init__(self, config):
        self.config = config	
        self.callback = None
        self.retry = 0
        self.connect()

    def connect(self):
        if not hasattr(self, 'connection') or \
            not self.connection or self.connection.is_closed:
            credentials = pika.PlainCredentials(
                    self.config.RABBITMQ.USER, 
                    self.config.RABBITMQ.PASSWORD)

            try:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        credentials=credentials,
                        host=self.config.RABBITMQ.HOST,
                        port=self.config.RABBITMQ.PORT))
            except (pika.exceptions.AMQPConnectionError, 
                    pika.exceptions.ConnectionClosedByBroker) as e:
                self.retry += 1
                if self.retry <= MAX_RETRY:
                    nap_time = RETRY_INTERVAL ** self.retry
                    logger.warning('RabbitMQ Connection Failed. '\
                            'RETRYING in {} seconds'.format(nap_time))
                    sleep(nap_time)
                    self.connect()
                else:
                    logger.critical(
                            'RabbitMQ connection failed, no retries left')
                    raise e from None
            else:
                self.retry = 0
                self.channel = self.connection.channel()
                self.pub_channel = self.connection.channel()

                self.pub_channel.confirm_delivery()

                self.channel.exchange_declare(
                        exchange=self.config.RABBITMQ.EXCHANGE, 
                        exchange_type='topic')

                self.channel.queue_declare(
                        queue=self.config.RABBITMQ.RESPONSE_QUEUE, 
                        durable=True)

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
        self.thread = threading.Thread(target=self._process_data_events)
        self.thread.setDaemon(True)
        self.thread.start()

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

    def publish(self, routing_key, task_id, job):
        with self.internal_lock:
            try:
                self.pub_channel.basic_publish(
                    exchange=self.config.RABBITMQ.EXCHANGE,
                    routing_key=routing_key,
                    properties=pika.BasicProperties(
                        reply_to=self.config.RABBITMQ.RESPONSE_QUEUE,
                        correlation_id=str(task_id),
                        priority=int(job.priority),
                        delivery_mode=2
                    ),
                    mandatory=True,
                    body=job.to_json())
            except pika.exceptions.UnroutableError:
                fail_resp = { 'state': 422, 
                        'message': 'Unroutable task' }
                self.callback(task_id, fail_resp)
                pass
            except Exception as e:
                raise e
