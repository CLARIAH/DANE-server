# Distributed Annotation 'n' Enrichment (DANE) 

The DANE ecosystem is designed to enable easy deployment and rapid prototyping of compute intensive workers,
in an environment where batch processing is not feasible and compute resources are either limited or distributed. 

![DANE-core](https://docs.google.com/drawings/d/e/2PACX-1vRCjKm3O5cqbF5LRlUyC6icAbQ3xmedKvArlY_8h31PJqAu3iZe6Q5qcVbs3rujVoGpzesD00Ck9-Hw/pub?w=953&amp;h=438)

In essence the DANE ecosystem consists of three parts, 1) The back-end (DANE-core), 2) The compute workers, 3) A client. 
The format of the communication between these components follows the [job specification format](https://github.com/CLARIAH/DANE-utils/blob/master/DANE_utils/jobspec.py)
which details the source material to process, the tasks which should be performed, as well as information about the task results.
Util code to build workers, clients, or work with a job specification is included in the [DANE-utils](https://github.com/CLARIAH/DANE-utils) package.

## DANE-core
DANE-core is the server, or back-end, component of DANE and takes care of job routing as well as the (meta)data storage. A job submitted to 
DANE-core is registered in a database, and then its `.run()` function is called. Running a job involves iterating over the tasks, and depending
on the structure of the tasks executing them sequentially or in parallel. 

A specific task is run by publishing the job to a [RabbitMQ Topic Exchange](https://www.rabbitmq.com/tutorials/tutorial-five-python.html),
on this exchange the task is routed based on its Task Key. The task key corresponds to the `binding_key` of a worker,
and each worker with this binding_key listens to a shared queue. Once a worker is available it will take the next job from the queue and process it.

DANE-core depends on [DANE-utils](https://github.com/CLARIAH/DANE-utils) package for the logic of how to iterate over tasks, and how to interpret a job
in general.

# Installation

DANE-core has been tested with Python 3.

    git clone https://github.com/CLARIAH/DANE-core.git
    cd DANE-core/
    pip install -r requirements.txt

Besides the python base, the DANE-core also relies on a [MariaDB](https://mariadb.org/) SQL server (tested with version 10.4) for persistent storage, 
and [RabbitMQ](https://www.rabbitmq.com/) (tested with version 3.7) for messaging.

After installing all dependencies it is necessary to correctly configure the settings file:
    
    cd server/ # inside DANE-core/
    cp example-settings.py settings.py

Open `settings.py` in your favourite editor and adjust the settings to match your configuration.

# Usage

*NOTE: DANE-core is still in development, as such authorisation (amongst other featueres) has not yet been added. Use at your own peril.*

Run the DANE-core server as follows:

    python3 server.py

If no errors occur then this should start a Flask server which will handle API requests, and in the background the server will handle interaction with the DB and RabbitMQ.
## API

DANE-core can be interacted with via a small API that supports a small number of essential calls:

    /DANE/job/

Via POST a new job can be submitted. It expects a JSON object which is a serialised job specification.

    /DANE/job/<job_id>

Get information about an existing job.

    /DANE/job/<job_id>/retry

Resume a job, if it has crashed.
 
    /DANE/search/<source_id>

Return the job_id's for all jobs that have this source_id.

## Examples

Examples of how to work with DANE can be found at: https://github.com/CLARIAH/DANE-utils/tree/master/examples
