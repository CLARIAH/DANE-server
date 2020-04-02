# Distributed Annotation 'n' Enrichment (DANE) 

The DANE ecosystem is designed to enable easy deployment and rapid prototyping of compute intensive workers,
in an environment where batch processing is not feasible and compute resources are either limited or distributed. 

![DANE-eco](https://docs.google.com/drawings/d/e/2PACX-1vRCjKm3O5cqbF5LRlUyC6icAbQ3xmedKvArlY_8h31PJqAu3iZe6Q5qcVbs3rujVoGpzesD00Ck9-Hw/pub?w=953&amp;h=438)

In essence the DANE ecosystem consists of three parts, 1) The back-end (DANE-server), 2) The compute workers, 3) A client. 
The format of the communication between these components follows the [job specification format](https://dane.readthedocs.io/en/latest/DANE/jobs.html)
which details the source material to process, the tasks which should be performed, as well as information about the task results.
Util code to build workers, clients, or work with a job specification is included in the [DANE](https://github.com/CLARIAH/DANE) package.

## DANE-server
DANE-server is the back-end, component of DANE and takes care of job routing as well as the (meta)data storage. A job submitted to 
DANE-server is registered in a database, and then its `.run()` function is called. Running a job involves iterating over the tasks, and depending
on the structure of the tasks executing them sequentially or in parallel. 

A specific task is run by publishing the job to a [RabbitMQ Topic Exchange](https://www.rabbitmq.com/tutorials/tutorial-five-python.html),
on this exchange the task is routed based on its Task Key. The task key corresponds to the `binding_key` of a worker,
and each worker with this binding_key listens to a shared queue. Once a worker is available it will take the next job from the queue and process it.

DANE-server depends on the [DANE](https://github.com/CLARIAH/DANE) package for the logic of how to iterate over tasks, and how to interpret a job
in general.

# Installation

DANE-server has been tested with Python 3 and is installable through pip:

    pip install dane-server

Besides the python base, the DANE-server also relies on a [MariaDB](https://mariadb.org/) SQL server (version 10.4) for persistent storage, 
and [RabbitMQ](https://www.rabbitmq.com/) (tested with version 3.7) for messaging.

On Ubuntu 18.04, the MariaDB version in the repo is too low (10.1), so you will need to take measures to install a more recent version.
Additionally, MariaDB for some reason pretends to be an early version of MySQL, so if you get the error:

```
MySQL version 5.7.2 and earlier does not support COM_RESET_CONNECTION.
```

Then you can fix this by adding the following to the `mysqld` block in `/etc/mysql/my.cnf`:

```
version=5.7.99-10.4.10-MariaDB
```

After installing all dependencies it is necessary to configure the DANE server, how to do this is described here: https://dane.readthedocs.io/en/latest/intro.html#configuration

The base config for DANE-server consists of the following parameters, which you might want to overwrite:

```
MARIADB: 
    USER: 'new_user'
    PASSWORD: 'new_password'
    HOST: 'localhost'
    PORT: '3306'
    DATABASE: 'DANE-sql-store'
LOGGING: 
    DIR: "./dane-server-logs/"
    LEVEL: "DEBUG"
DANE_SERVER:
    TEMP_FOLDER: "/home/DANE/DANE-data/TEMP/"
    OUT_FOLDER: "/home/DANE/DANE-data/OUT/"
```

# Usage

*NOTE: DANE-server is still in development, as such authorisation (amongst other featueres) has not yet been added. Use at your own peril.*

Run the DANE-server server as follows:

    dane-server

If no errors occur then this should start a Flask server (at port 5500) which will handle API requests, and in the background the server will handle interaction with the DB and RabbitMQ.

## API

DANE-server can be interacted with via a small API that supports a small number of essential calls:

    /DANE/job/

Via POST a new job can be submitted. It expects a JSON object which is a serialised job specification.

    /DANE/job/<job_id>

Get information about an existing job.

    /DANE/job/<job_id>/retry

Resume a job, if it has crashed.

    /DANE/job/<job_id>/delete

Deletes the job
 
    /DANE/search/<source_id>

Return the job_id's for all jobs that have this source_id.

    /DANE/job/inprogress

Returns a list of job_id's for in progress jobs, or jobs which have errored.

    /DANE/task/<task_id>

Get information about this task

    /DANE/task/<task_id>/forceretry

This will force the DANE-server to retry this task, even if it completed successfully or is already queued.

    /DANE/task/<task_id>/reset

Reset the task state to `201`

## Examples

Examples of how to work with DANE can be found at: https://dane.readthedocs.io/en/latest/examples.html
