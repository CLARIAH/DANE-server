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

from elasticsearch import Elasticsearch
from elasticsearch import exceptions as EX
import json
import os
import logging
from functools import partial
from urllib.parse import urlsplit

import DANE
import DANE.base_classes
import threading

logger = logging.getLogger('DANE-server')

INDEX = 'dane-index' # TODO make configurable?

class ESHandler(DANE.base_classes.base_handler):

    def __init__(self, config, queue, resume_unfinished=False):  #TODO change default to True
        super().__init__(config)
        self.queue = queue
        self.queue.assign_callback(self.callback)

        self.es = None
        self.connect()

        if resume_unfinished:
            th = threading.Timer(interval=3, function=self._resume_unfinished)
            th.daemon = True
            th.start()
        
    def connect(self):
        
        self.es = Elasticsearch() # TODO accept host and port
        if not self.es.indices.exists(index=INDEX):
            self.es.indices.create(index=INDEX, body={
                "settings" : {
                    "index" : {
                        "number_of_shards" : 1,  # TODO do we need this?
                        "number_of_replicas" : 1 
                    }
                },
                "mappings": {
                    "properties": {
                        "role": {
                            "type": "join",
                            "relations": {
                                "document": ["task", "results"]
                            }
                        },
                        # properties of a document:
                        "target": {
                            "properties": {
                                "id": { "type": "keyword" },
                                "url": { "type": "text" },
                                "type": { "type": "keyword" }
                            }
                        },
                        "creator": {
                            "properties": {
                                "id": { "type": "keyword" },
                                "type": { "type": "keyword" },
                                "name": { "type": "text" }
                            }
                        },
                        # task properties
                        "task": {
                            "properties": {
                                "priority": { "type": "byte" },
                                "key": { "type": "keyword" },
                                "state": { "type": "short" },
                                "msg": { "type": "text" },
                                "args": { "type": "object" }
                            }
                        },
                        # result properties:
                        "result": {
                            "properties": {
                                "generator": {
                                    "properties": {
                                        "id": { "type": "keyword" },
                                        "type": { "type": "keyword" },
                                        "name": { "type": "keyword" },
                                        "homepage": { "type": "text" }
                                    }
                                }, 
                                "payload": {
                                    "type": "object"
                                }
                            }
                        }
                    }
                }
            })

    def _resume_unfinished(self):
        unfinished = self.getUnfinished()['tasks']
        if len(unfinished) > 0:
            logger.info("Attempting to resume unfinished tasks")
            for tid in unfinished:
                self.taskFromTaskId(tid).retry()

    def getDirs(self, document):
        # expect that TEMP and OUT folder exist 
        TEMP_SOURCE = self.config.DANE_SERVER.TEMP_FOLDER
        OUT_SOURCE = self.config.DANE_SERVER.OUT_FOLDER

        if not os.path.exists(TEMP_SOURCE):
            os.mkdir(TEMP_SOURCE)
        if not os.path.exists(OUT_SOURCE):
            os.mkdir(OUT_SOURCE)

        # Get a more specific path name, by chunking id into (at most)
        # three chunks of 2 characters
        chunks = os.path.join(*[document._id[i:2+i] for i in range(0, 
            min(len(document._id),6), 2)])
        TEMP_DIR = os.path.join(TEMP_SOURCE, chunks, document._id)
        OUT_DIR = os.path.join(OUT_SOURCE, chunks, document._id)

        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)
        if not os.path.exists(OUT_DIR):
            os.makedirs(OUT_DIR)

        return {
            'TEMP_FOLDER': TEMP_DIR,
            'OUT_FOLDER': OUT_DIR
        }
 
    def registerDocument(self, document):
        
        docs = self.search(document.target['id'],
                document.creator['id'])['documents']

        if len(docs) > 0:
            raise ValueError('A document with target.id `{}`, '\
                    'and creator.id `{}` already exists'.format(
                        document.target['id'],
                        document.creator['id']))

        doc = json.loads(document.to_json())
        doc['role'] = 'document'

        res = self.es.index(index=INDEX, body=json.dumps(doc), refresh=True)
        document._id = res['_id']
        
        logger.info("Registered new document #{}".format(document._id))
        
        return document._id

    def deleteDocument(self, document):
        if document._id is None:
            logger.error("Can only delete registered documents")
            raise KeyError("Failed to delete unregistered document")

        self.es.delete(INDEX, document._id)
        logger.info("Deleted document #{}".format(document._id))
        
    def assignTask(self, task, document_id):
        if not self.es.get(index=INDEX, id=document_id)['found']:
            raise KeyError('No document with id `{}` found'.format(
                document_id))

        query = {
          "query": {
            "bool": {
              "must": [
                {
                  "has_child": {
                    "type": "task",
                    "query": {
                      "bool": {
                        "must": {
                          "match": {
                            "task.key": task.key
                          }
                        }
                      }
                    }
                  }
                },
                {
                  "match": {
                    "_id": document_id
                  }
                }
              ]
            }
          }
        }

        if self.es.count(index=INDEX, body=query)['count'] > 0:
            raise ValueError('Task `{}` '\
                    'already assigned to document `{}`'.format(
                        task.key,
                        document_id))

        task.state = 201
        task.msg = 'Created'

        t = json.loads(task.to_json())
        t['role'] = { 'name': 'task', 'parent': document_id }

        res = self.es.index(index=INDEX, 
                routing=document_id,
                body=json.dumps(t),
                refresh=True)


        task._id = res['_id']
        
        logger.info("Assigned task {} () to document #{}".format(task.key,
            task._id,
            document_id))

        return task

    def taskFromTaskId(self, task_id):

        query = {
         "_source": "task",
          "query": {
            "bool": {
              "must": [
                {
                  "has_parent": {
                    "parent_type": "document",
                    "query": { # since we must have a query..
                      "exists": {
                        "field": "target.id"
                      }
                    }
                  }
                },
                {
                  "match": {
                    "_id": task_id
                  }
                },
                { "exists": {
                    "field": "task.key"
                  }
                }
              ]
            }
          }
        }
        
        result = self.es.search(index=INDEX, body=query)

        if result['hits']['total']['value'] == 1:
            # hacky way to pass _id to Task
            result['hits']['hits'][0]['_source']['task']['_id'] = \
                    result['hits']['hits'][0]['_id']
            task = DANE.Task.from_json(result['hits']['hits'][0]['_source'])
            task.set_api(self)
            return task
        else:
            raise KeyError("No result for given task id")

    def getTaskState(self, task_id):
        return int(self.taskFromTaskId(task_id).state)

    def getTaskKey(self, task_id): 
        return self.taskFromTaskId(task_id).key

    def _set_task_states(self, states, task):
        tid = task.task_id
        for s in states:
            if s['task_id'] == tid:
                task.task_state = int(s['task_state'])
                task.task_msg = s['task_msg']
                return

    def documentFromDocumentId(self, document_id):
        result = self.es.get(index=INDEX, id=document_id, 
                _source_excludes=['role'],
                ignore=404)

        if result['found']:
            result['_source']['_id'] = result['_id']
            document = DANE.Document.from_json(json.dumps(result['_source']))
            document.set_api(self)
            return document
        else:
            raise KeyError("No result for given document id")

    def documentFromTaskId(self, task_id):
        query = {
         "_source": {
            "excludes": [ "role" ]    
         },
          "query": {
            "bool": {
              "must": [
                {
                  "has_child": {
                    "type": "task",
                    "query": { 
                      "match": {
                        "_id": task_id
                      }
                    }
                  }
                }
              ]
            }
          }
        }
        
        result = self.es.search(index=INDEX, body=query)

        if result['hits']['total']['value'] == 1:
            result['hits']['hits'][0]['_source']['_id'] = \
                    result['hits']['hits'][0]['_id']

            document = DANE.Document.from_json(json.dumps(
                result['hits']['hits'][0]['_source']))
            document.set_api(self)
            return document
        else:
            raise KeyError("No result for given task id")

    def _run(self, task):
        document = self.documentFromTaskId(task._id)
        
        routing_key = "{}.{}".format(document.target['type'], 
                task.key)

        logger.info("Queueing task {} ({}) for document {}".format(task._id,
            task.key, document._id))
        self.updateTaskState(task._id, 102, 'Queued')

        # TODO should the server sided paths be enforced?
        # can be useful to not enforce, for adhoc usage
        if 'PATHS' not in task.args.keys():
            task.args['PATHS'] = self.getDirs(document)

        self.queue.publish(routing_key, task, document)

    def run(self, task_id):
        task = self.taskFromTaskId(task_id)
        if task.state == 201:
            # Fresh of the press task, run it no questions asked
            self._run(task)
        elif task.state in [502, 503]:
            # Task that might be worth automatically retrying 
            self._run(task)
        else:
            # Requires manual intervention
            # and task resubmission once issue has been resolved
            pass

    def retry(self, task_id, force=False):
        task = self.taskFromTaskId(task_id)
        if task.state not in [102, 200] or force:
            # Unless its already been queued or completed, we can run this again
            # Or we can force it to run again
            self._run(task)

    def callback(self, task_id, response):
        try:
            task_key = self.getTaskKey(task_id)

            state = int(response.pop('state'))
            message = response.pop('message')

            print(response) # TODO make response/result class 
            # store results in ES

            if state != 200:
                logger.warning("Task {} ({}) failed with msg: #{} {}".format(
                    task_key, task_id, state, message))            
            else:
                logger.info("Callback for task {} ({})".format(task_id, task_key))

            #doc = self.documentFromTaskId(task_id)
            #doc.set_api(self)

            self.updateTaskState(task_id, state, message)
            #job.run() # TODO how do we trigger other tasks?
        except KeyError as e:
            logger.exception('Callback on non-existing task')
        except Exception as e:
            logger.exception('Unhandled error during callback')

    def updateTaskState(self, task_id, state, message):        
        self.es.update(index=INDEX, id=task_id, body={
            "doc": {
                "task": {
                    "state": state,
                    "msg": message
                }
            }
        }, refresh=True)

    def search(self, target_id, creator_id):
        query = {
            "_source": False,
            "query": {
                "bool": {
                    "must": [
                        { "match": { "target.id": target_id }},
                        { "match": { "creator.id": creator_id }}
                    ]
                }
            }
        }

        res = self.es.search(index=INDEX, body=query)

        return {'documents': [doc['_id'] for doc in res['hits']['hits'] ] }

    def getUnfinished(self):
        query = {
         "_source": False,
          "query": {
            "bool": {
              "must": [
                {
                  "has_parent": {
                    "parent_type": "document",
                    "query": { # since we must have a query..
                      "exists": {
                        "field": "target.id"
                      }
                    }
                  }
                }
            ], "must_not": {
                  "match": {
                    "task.state": 200
                  }
                }
              }
            }
          }
        
        result = self.es.search(index=INDEX, body=query)

        return {'tasks': [res['_id'] for res in result['hits']['hits']]}
