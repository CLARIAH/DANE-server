import unittest
import DANE
from DANE.config import cfg
import threading
from worker import test_worker
from time import sleep
import sys
import os

from dane_server.handler import Handler
from dane_server.RabbitMQListener import RabbitMQListener

class TestBackend(unittest.TestCase):

    def test_backend(self):
        if not os.path.exists(cfg.DANE_SERVER.TEMP_FOLDER):
            os.makedirs(cfg.DANE_SERVER.TEMP_FOLDER)
        if not os.path.exists(cfg.DANE_SERVER.OUT_FOLDER):
            os.makedirs(cfg.DANE_SERVER.OUT_FOLDER)

        self.messageQueue = RabbitMQListener(cfg)
        handler = Handler(config=cfg, queue=self.messageQueue)
        self.messageQueue.run()

        self.worker = test_worker(cfg)

        w_thread = threading.Thread(target=self.worker.run)
        w_thread.setDaemon(True)
        w_thread.start()

        doc = DANE.Document(
            {
                'id': 'UNITTEST123',
                'url': 'http://127.0.0.1/example',
                'type': 'Text'
            },{
                'id': 'TEST',
                'type': 'Software'
            }
        ) 

        doc.set_api(handler)
        doc.register()

        self.assertIsNotNone(doc._id)

        task = DANE.Task('TEST')
        task.set_api(handler)
        task.assign(doc._id)

        # Wait for task to finish
        for _ in range(10):
            sleep(1) 
            task.refresh()
            if task.isDone():
                # if task is done we can continue
                break

        self.assertTrue(task.isDone())

        self.assertTrue(doc.delete())
        self.assertTrue(task.delete())

        self.worker.stop()
        # Wait for the worker to stop
        for _ in range(10):
            if w_thread.is_alive():
                sleep(0.1)

    def tearDown(self):
        # hacky way to ensure we dont delete a real exchange/queue
        if 'TEST' in cfg.RABBITMQ.EXCHANGE:
            self.messageQueue.channel.exchange_delete(cfg.RABBITMQ.EXCHANGE)
        if 'TEST' in cfg.RABBITMQ.RESPONSE_QUEUE:
            self.messageQueue.channel.queue_delete(cfg.RABBITMQ.RESPONSE_QUEUE)

        # delete the worker queue
        self.worker.channel.queue_delete(queue=self.worker.queue)

        self.messageQueue.stop()

if __name__ == '__main__':
    unittest.main()
