from DANE.base_classes import base_worker
import json

class test_worker(base_worker):
    # we specify a queue name because every worker of this type should 
    # listen to the same queue
    __queue_name = 'TEST'

    def __init__(self, config,
                response={'state': 200, 
                'message': 'Success'}):

        super().__init__(queue=self.__queue_name, 
                binding_key='#.TEST', config=config)

        self.response = response

    def callback(self, job_request):
        return json.dumps(self.response)

# To use this:
# tt = test_worker(cfg)
# tt.run()
