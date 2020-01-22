from DANE_utils.base_classes import base_worker
from os.path import getsize
import json

import sys
sys.path.append('../src/')
import settings

class test_worker(base_worker):
    # we specify a queue name because every worker of this type should 
    # listen to the same queue
    __queue_name = 'TEST'

    def __init__(self, config):
        super().__init__(queue=self.__queue_name, 
                binding_key='#.TEST', config=config)

    def callback(self, job_request):
        print('Got request', job_request)

        return json.dumps({'state': 200, 
            'message': 'Success', 
            'foo': 'bar'})

if __name__ == '__main__':
    tt = test_worker(settings.config)
    print(' # Initialising worker. Ctrl+C to exit')

    try: 
        tt.run()
    except KeyboardInterrupt:
        tt.stop()
