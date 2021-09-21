# DANE-server
DANE-server is the back-end component of [DANE](https://github.com/CLARIAH/DANE) and takes care of task routing as well as the (meta)data storage. A task submitted to 
DANE-server is registered in a database, and then its `.run()` function is called. Running a task involves assigning it to a worker via a message queue.

A specific task is run by publishing the task to a [RabbitMQ Topic Exchange](https://www.rabbitmq.com/tutorials/tutorial-five-python.html),
on this exchange the task is routed based on its Task Key. The task key corresponds to the `binding_key` of a worker,
and each worker with this binding_key listens to a shared queue. Once a worker is available it will take the next task from the queue and process it.

DANE-server depends on the [DANE](https://github.com/CLARIAH/DANE) package for the logic of how to iterate over tasks, and how to interpret a task
in general.

# Local Installation

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

# Docker

To run DANE-server, using Docker make sure to install a Docker Engine, e.g. Docker Desktop for OSX.

## Build the Docker images

As the DANE-server has two separate processes. Two images need to be created:

- One for running the Task Scheduler
- One for running the API

Run the following from the main directory of this repo:

```
docker build -t dane-server -f Dockerfile.ts .
docker build -t dane-server-api -f Dockerfile.api .
```

**Note**: currently the build relies on the `es-index-cfg` branch of DANE (see `requirements.txt`)

After the images have been successfully built, it is possible to run DANE-server via Kubernetes as well

# Kubernetes

These instructions are optimized for `minikube`, which is for local development only. For deployment to a proper k8s cluster, you're on your own for now...

Note that the provided Kubernetes config only provisions your k8s cluster with:

- Endpoint to external Elasticsearch (make sure you got one running)
- RabbitMQ
- DANE server (task scheduler)
- DANE server API

In order to get a bunch of workers setup, you can check the k8s config files in [DANE-asr-worker](https://github.com/beeldengeluid/DANE-asr-worker) repository (later on more examples should follow).

## Create a configmap for config.yml

First make sure to create the config.yml from the config-k8s.yml:

```
cp config-k8s.yml config.yml
```

Now before applying the Kubernetes file `dane-server-k8s.yaml` to your cluster, first create a ConfigMap for config.yml

```
kubectl create configmap dane-server-cfg --from-file config.yml
```

Now the ConfigMap is there, make sure to check that dane-server-k8s.yml points to a existing Elasticsearch host. After that you can go ahead and run:

```
kubectl apply -f dane-server-k8s.yaml
```

## Configure your local DNS to access the API (and RabbitMQ dashboard)

Check the ip assigned to the `dane-server-ingress` (and `dane-rabbitmq-ingress`) by running:

```
kubectl get ingress
```

grab the IP from the `ADDRESS` column and put this in your `/etc/hosts` file:

```
{IP}    api.dane.nl rabbitmq.dane.nl
```

**Note**: you can assign different domain names by editing the Ingresses in `dane-server-k8s.yaml`
