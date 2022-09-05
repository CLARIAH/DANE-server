from dane.base_classes import base_worker


class test_worker(base_worker):
    # we specify a queue name because every worker of this type should
    # listen to the same queue
    __queue_name = "TEST"
    __binding_key = "#.TEST"

    def __init__(self, config, response={"state": 200, "message": "Success"}):

        super().__init__(
            queue=self.__queue_name, binding_key=self.__binding_key, config=config
        )

        self.response = response

    def callback(self, task, doc):
        return self.response


# To use this:
# tt = test_worker(cfg)
# tt.run()
