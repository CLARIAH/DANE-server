# DANE-server
DANE-server is the back-end component of [DANE](https://github.com/CLARIAH/DANE) and takes care of task routing as well as the (meta)data storage. A task submitted to 
DANE-server is registered in a database, and then its `.run()` function is called. Running a task involves assigning it to a worker via a message queue.

A specific task is run by publishing the task to a [RabbitMQ Topic Exchange](https://www.rabbitmq.com/tutorials/tutorial-five-python.html),
on this exchange the task is routed based on its Task Key. The task key corresponds to the `binding_key` of a worker,
and each worker with this binding_key listens to a shared queue. Once a worker is available it will take the next task from the queue and process it.

DANE-server depends on the [DANE](https://github.com/CLARIAH/DANE) package for the logic of how to iterate over tasks, and how to interpret a task
in general.

# Installation

DANE-server has been tested with Python 3 and is installable through pip:

    pip install dane-server

Besides the python base, the DANE-server also relies on an [Elasticsearch](https://www.elastic.co/elasticsearch/) server (version 7.9) for storage, 
and [RabbitMQ](https://www.rabbitmq.com/) (tested with version 3.7) for messaging.

After installing all dependencies it is necessary to configure the DANE server, how to do this is described here: https://dane.readthedocs.io/en/latest/intro.html#configuration

The base config for DANE-server consists of the following parameters, which you might want to overwrite:

```
LOGGING: 
    DIR: "./dane-server-logs/"
    LEVEL: "DEBUG"
DANE_SERVER:
    TEMP_FOLDER: "/home/DANE/DANE-data/TEMP/"
    OUT_FOLDER: "/home/DANE/DANE-data/OUT/"
```

# Usage

*NOTE: DANE-server is still in development, as such authorisation (amongst other featueres) has not yet been added. Use at your own peril.*

Run the server component (which listens to the RabbitMQ) as follows:

    dane-server

Besides the server component we also need the API, which we can start with:

    dane-api

If no errors occur then this should start a webserver (at port 5500) which will handle API requests, 
while in the background the server will handle interaction with the DB and RabbitMQ.

## API

The DANE api is documented with a swagger UI, available at: http://localhost:5500/DANE/

## Examples

Examples of how to work with DANE can be found at: https://dane.readthedocs.io/en/latest/examples.html
