#!/usr/bin/env python
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
                    self.config['RABBITMQ']['user'], 
                    self.config['RABBITMQ']['password'])

            try:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        credentials=credentials,
                        host=self.config['RABBITMQ']['host'],
                        port=self.config['RABBITMQ']['port']))
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
                        exchange=self.config['RABBITMQ']['exchange'], 
                        exchange_type='topic')

                self.channel.queue_declare(
                        queue=self.config['RABBITMQ']['response_queue'], 
                        durable=True)

                self.channel.basic_consume(
                    queue=self.config['RABBITMQ']['response_queue'],
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
        return self.callback(*args)

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
                    exchange=self.config['RABBITMQ']['exchange'],
                    routing_key=routing_key,
                    properties=pika.BasicProperties(
                        reply_to=self.config['RABBITMQ']['response_queue'],
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
