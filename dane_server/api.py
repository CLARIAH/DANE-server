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

from flask import Flask, g
from flask import render_template, redirect, url_for, Blueprint, abort, send_from_directory
from flask import request, Response, make_response
from flask_restx import Api, Resource, fields, marshal

from functools import wraps

import json
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import quote
import requests

from dane_server.handler import INDEX
from DANE.handlers import ESHandler as Handler
from dane_server.RabbitMQPublisher import RabbitMQPublisher
import DANE
from DANE.config import cfg

logger = logging.getLogger('DANE')
logger.setLevel(cfg.LOGGING.LEVEL)
# create file handler which logs to file
if not os.path.exists(os.path.realpath(cfg.LOGGING.DIR)):
    os.makedirs(os.path.realpath(cfg.LOGGING.DIR), exist_ok=True)

fh = TimedRotatingFileHandler(os.path.join(
    os.path.realpath(cfg.LOGGING.DIR), "DANE-api.log"), 
    when='W6', # start new log on sunday
    backupCount=3)
fh.setLevel(cfg.LOGGING.LEVEL)
# create console handler 
ch = logging.StreamHandler()
ch.setLevel(cfg.LOGGING.LEVEL)
# create formatter and add it to the handlers
formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        "%Y-%m-%d %H:%M:%S")
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

bp = Blueprint('DANE', __name__)

app = Flask(__name__, static_url_path='/manage', 
        static_folder="web")
app.debug = True

api = Api(bp,
	title='DANE API',
    description='API to interact with DANE')

ns_doc = api.namespace('document', description='Document operations')
ns_docs = api.namespace('documents', description='Batch operations on Documents')
ns_task = api.namespace('task', description='Task operations')
ns_result = api.namespace('result', description='Result operations')
ns_workers = api.namespace('workers', description='Worker operations')
ns_search = api.namespace('search', description='Search operations')

"""------------------------------------------------------------------------------
REGULAR ROUTING 
------------------------------------------------------------------------------"""

_target = api.model('target', {
    'id' : fields.String(description='Target ID', required=True, 
        example='ITM123555'),
    'url' : fields.String(description='Target url', required=True, 
        example='http://low.res/vid.mp4'),
    'type' : fields.String(description='Target type', required=True, 
        example='Video', enum=["Dataset", "Image", "Video", "Sound", "Text"]),
})

_creator = api.model('creator', {
    'id' : fields.String(description='Creator ID', required=True, example='NISV'),
    'type' : fields.String(description='Creator type', required=True, 
        example='Organization', enum=["Organization", "Human", "Software"]),
})

_generator = api.model('generator', {
    'id' : fields.String(description='Generator ID', required=True, 
        example="214943e"),
    'name' : fields.String(description='Generator Name', required=True, 
        example="SHOTDETECTION"),
    'homepage' : fields.String(description='Generator homepage', required=True,
        example="https://github.com/beeldengeluid/shot-detection-worker.git"),
    'type' : fields.String(description='Generator type', required=True, 
        example="Software", enum=["Organization", "Human", "Software"]),
})

_anyField = api.model('AnyField', {
     '*': fields.Wildcard(fields.Raw),
    })

_document = api.model('Document', {
    '_id' : fields.String(description='DANE Assigned Document ID', 
        required=False, example="KJfYfHQBqBJknIB4zrJL"),
    'target' : fields.Nested(_target, description='Document target', 
        required=True),
    'creator' : fields.Nested(_creator, description='Document creator/owner',
        required=True),
    'created_at' : fields.String(description='Creation time', 
        required=False, example="2020-12-12T10:53:57"),
    'updated_at' : fields.String(description='Creation time', 
        required=False, example="2021-01-09T12:24:32")
})

_task = api.model('Task', {
    '_id' : fields.String(description='DANE assigned Task ID', required=False,
        example="D5fXfHQBqBJknIB44rIy"),
    'key' : fields.String(
        description='Key of the task, should match a worker binding key', 
        required=True, example="SHOTDETECTION"),
    'state' : fields.String(description='Status code of task state', 
        required=False, example="200"),
    'msg' : fields.String(description='Textual variant of state', 
        required=False, example="Success"),
    'priority' : fields.Integer(description='Task priority', required=True, 
        default=1, min=1, max=10),
    'created_at' : fields.String(description='Creation time', 
        required=False, example="2020-12-12T10:53:57"),
    'updated_at' : fields.String(description='Creation time', 
        required=False, example="2021-01-09T12:24:32"),
    'args': fields.Nested(_anyField, description='Task arguments', 
        required=False)
})

_result = api.model('Result', {
    '_id' : fields.String(description='DANE assigned Result ID', 
        required=False, example="v5d7fXQBqBJknIB4Sbn9"),
    'generator' : fields.Nested(_generator, description='Result generator', 
        required=True),
    'payload': fields.Nested(_anyField, description='Result payload', 
        required=True),
    'created_at' : fields.String(description='Creation time', 
        required=False, example="2020-12-12T10:53:57"),
    'updated_at' : fields.String(description='Creation time', 
        required=False, example="2021-01-09T12:24:32")
})

_worker = api.model('Worker', {
    'name' : fields.String(description='Worker binding key', required=True,
        example="SHOTDETECTION"),
    'active_workers' : fields.Integer(description='Actively running workers', 
        required=True, default=0),
    'in_queue' : fields.Integer(description='Number of tasks in queue', 
        required=True, default=0)
})

_fails = api.model('Failure', {
    'document' : fields.Nested(_document, description='Failed document', 
        required=False),
    'invalid': fields.Nested(_anyField, description='Invalid format doc', 
        required=False),
    'error' : fields.String(description='Error message', 
        required=True, example="Task already assigned")
})

_batchResultDoc = api.model('BatchResultDocuments', {
    'success' : fields.List(fields.Nested(_document), description='Successfully inserted documents', 
        required=False),
    'failed' : fields.List(fields.Nested(_fails), description='Failed documents', 
        required=False)
})

_failTasks = api.model('Failure', {
    'document_id' : fields.String(description='Document this applies to', 
        required=False, example="v5d7fXQBqBJknIB4Sbn9"),
    'error' : fields.String(description='Error message', 
        required=True, example="Task already assigned")
})

_batchResultTasks = api.model('BatchResultTasks', {
    'success' : fields.List(fields.Nested(_task), description='Successfully assigned tasks', 
        required=False),
    'failed' : fields.List(fields.Nested(_failTasks), description='Failed tasks', 
        required=False)
})

_searchResult = api.model('SearchResult', {
    'total' : fields.Integer(description='Total hits', required=True, example=1),
    'hits' : fields.List(fields.Nested(_document), description='Documents returned', 
        required=True)
})

_workerTasks = api.model('WorkerTasks', {
    'total' : fields.Integer(description='Total Tasks', required=True, example=1),
    'tasks' : fields.List(fields.Nested(_task), description='Tasks returned', 
        required=True)
})

_massResetResult = api.model('MassResetResult', {
    'total' : fields.Integer(description='Total Tasks affected', required=True, example=1),
    'error' : fields.String(description='Error message', 
        required=False, example="ConnectionError")
})

@ns_doc.route('/')
class DocumentListAPI(Resource):
    
    @ns_doc.marshal_with(_document)
    def post(self):
        postData = None
        try:
            postData = request.data.decode('utf-8')
        except Exception as e:
            logger.exception('Error handling post data')
            abort(500) # TODO handle this nicer

        try:
            if '_id' in json.loads(postData):
                raise TypeError
            doc = DANE.Document.from_json(postData)
        except (TypeError, json.decoder.JSONDecodeError) as e:
            logger.exception('FormatError')
            abort(400, 'Invalid document format')
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)

        try:
            doc.set_api(get_handler())
            doc.register()
        except DANE.errors.DocumentExistsError as e:
            abort(409, str(e))
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500, str(e))

        return doc

@ns_doc.route('/<doc_id>')
class DocumentAPI(Resource):

    @ns_doc.marshal_with(_document)
    def get(self, doc_id):
        try:
            doc_id = quote(doc_id) # escape potential nasties
            doc = get_handler().documentFromDocumentId(doc_id)
        except DANE.errors.DocumentExistsError:
            logger.debug("Document {} not found.".format(doc_id))
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return doc

    def delete(self, doc_id):
        try:
            doc_id = quote(doc_id) # escape potential nasties
            doc = get_handler().documentFromDocumentId(doc_id)
            doc.delete()
        except DANE.errors.DocumentExistsError:
            logger.debug("Document {} not found.".format(doc_id))
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return ('', 200)

@ns_doc.route('/<doc_id>/tasks')
class DocumentTasksAPI(Resource):

    @ns_doc.marshal_with(_task, as_list=True)
    def get(self, doc_id):
        try:
            doc_id = quote(doc_id) # escape potential nasties
            doc = get_handler().documentFromDocumentId(doc_id)
            tasks = doc.getAssignedTasks()
        except DANE.errors.DocumentExistsError:
            logger.debug("Document {} not found.".format(doc_id))
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return tasks

@ns_docs.route('/')
class BatchDocumentsListAPI(Resource):

    @ns_docs.expect([_document])
    @ns_docs.marshal_with(_batchResultDoc)
    def post(self):
        postData = None
        try:
            postData = request.data.decode('utf-8')
            postData = json.loads(postData)
        except Exception as e:
            logger.exception('Error handling post data')
            abort(500) # TODO handle this nicer

        docs = []
        for pd in postData:
            try:
                if '_id' in pd:
                    raise TypeError
                docs.append(DANE.Document.from_json(pd))
            except (TypeError, json.decoder.JSONDecodeError) as e:
                logger.exception('FormatError')
                failed.append({'invalid': pd, 'error': 'Invalid document format'})
                continue
            except Exception as e:
                logger.exception('Unhandled Error')
                failed.append({'invalid': pd, 'error': 'Unhandled error'})
                continue

        success, failed = get_handler().registerDocuments(docs)

        return {'success': success, 'failed': failed }

    @ns_docs.doc(params={'doc' : { 'description': 'Document ids', 
            'type': 'array', 
            'items' : { 'type': 'string' } 
        }})
    @ns_doc.marshal_with(_document, as_list=True)
    def get(self):
        docs = request.args.getlist('doc[]', type=str) # hacky way to support array notation
        docs += request.args.getlist('doc', type=str) 

        # even accept comma separated lists in a single query value
        # i.e. doc=A,B,C
        docs = [sd for d in docs for sd in d.split(',')]

        output = []
        for doc_id in docs:
            try:
                doc_id = quote(doc_id) # escape potential nasties
                doc = get_handler().documentFromDocumentId(doc_id)
            except DANE.errors.DocumentExistsError:
                logger.debug("Document {} not found.".format(doc_id))
                abort(404) 
            except Exception as e:
                logger.exception('Unhandled Error')
                abort(500)
            else:
                output.append(json.loads(doc.to_json()))

        return Response(json.dumps(output), status=200, mimetype='application/json')

    @ns_docs.doc(params={'doc' : { 'description': 'Document ids', 
            'type': 'array', 
            'items' : { 'type': 'string' } 
        }})
    def delete(self):
        docs = request.args.getlist('docs[]', type=str) 
        docs += request.args.getlist('docs', type=str) 

        # even accept comma separated lists in a single query value
        # i.e. doc=A,B,C
        docs = [sd for d in docs for sd in d.split(',')]

        for doc_id in docs:
            try:
                doc_id = quote(doc_id) # escape potential nasties
                doc = get_handler().documentFromDocumentId(doc_id)
                doc.delete()
            except TypeError as e:
                logger.exception('TypeError')
                abort(500, "{ 'document': {})".format(doc_id))
            except DANE.errors.DocumentExistsError:
                logger.debug("Batch delete document {} not found.".format(doc_id))
                # for batch its OK if the doc_id doesnt exist
                pass
            except ValueError as e:
                logger.exception('ValueError')
                abort(400, "{ 'document': {})".format(doc_id))
            except Exception as e:
                logger.exception('Unhandled Error')
                abort(500, "{ 'document': {})".format(doc_id))

        return ('', 200)

@ns_search.route('/document/')
class SearchAPI(Resource):

    @ns_search.doc(params={'target_id' : { 'description': "ID of document", 
            'type': 'string', 'default': '*', 'required': False },
        'creator_id' : { 'description': "ID of document creator/owner", 
            'type': 'string' , 'default': '*', 'required': False},
        'page' : { 'description': "page number", 
            'type': 'int' , 'default': '1', 'required': False}})
    @ns_doc.marshal_with(_searchResult, as_list=True)
    def get(self):
        target_id = quote(request.args.get('target_id', '*')).replace('%2A', '*')
        creator_id = quote(request.args.get('creator_id', '*')).replace('%2A', '*')
        result, count = get_handler().search(target_id, creator_id, 
                int(request.args.get('page', 1)))
        return { 'total': count, 'hits' : result }

@ns_task.route('/')
class TaskListAPI(Resource):

    @ns_docs.expect(_task)
    def post(self):
        postData = None

        try:
            postData = request.data.decode('utf-8')
        except Exception as e:
            logger.exception('Error handling post data')
            abort(500) # TODO handle this nicer

        try:
            # extract 'document_id' key from postdata
            postData = json.loads(postData)
            docs = postData.pop('document_id')
            if '_id' in postData:
                raise TypeError

            task = DANE.Task.from_json(postData)

        except (TypeError, json.decoder.JSONDecodeError) as e:
            logger.exception('FormatError')
            abort(400, 'Invalid task format')
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)

        try:
            task.set_api(get_handler())

            if isinstance(docs, list):
                resp = {}
                resp['success'], resp['failed'] = task.assignMany(docs)

                # potentially split this to separate call
                return marshal(resp, _batchResultTasks), 200
            else:
                task.assign(docs)    
                return marshal(task, _task), 201

        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500, str(e))

    def get(self): # deviate from spec and return unfinished rather than all tasks
        result = get_handler().getUnfinished()
        return Response(json.dumps(result), status=200, mimetype='application/json')

@ns_task.route('/<task_id>')
class TaskAPI(Resource):

    @ns_doc.marshal_with(_task)
    def get(self, task_id):
        try:
            task_id = quote(task_id) 
            task = get_handler().taskFromTaskId(task_id)
        except DANE.errors.TaskExistsError as e:
            logger.exception('TaskExistsError')
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return task

    def delete(self, task_id):
        try:
            task_id = quote(task_id) 
            task = get_handler().taskFromTaskId(task_id)
            task.delete()
        except DANE.errors.TaskExistsError as e:
            logger.exception('TaskExistsError')
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return ('', 200)

@ns_task.route('/<task_id>/<action>')
class TaskActionAPI(Resource):

    @ns_doc.marshal_with(_task)
    def get(self, task_id, action):
        try:
            task_id = quote(task_id) 
            task = get_handler().taskFromTaskId(task_id)
            if action.lower() == 'retry':
                task.retry(force=False).refresh()
            elif action.lower() == 'forceretry':
                task.retry(force=True).refresh()
            elif action.lower() == 'reset':
                task.reset().refresh()
            else:
                abort(400) 
        except DANE.errors.TaskExistsError as e:
            logger.exception('TaskExistsError')
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return task

@ns_result.route('/<result_id>')
class ResultAPI(Resource):

    @ns_doc.marshal_with(_result)
    def get(self, result_id):
        try:
            result_id = quote(result_id) 
            result = get_handler().resultFromResultId(result_id)
        except DANE.errors.ResultExistsError as e:
            logger.exception('ResultExistsError')
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return result

    def delete(self, result_id):
        try:
            result_id = quote(result_id) 
            result = get_handler().resultFromResultId(result_id)
            result.delete()
        except DANE.errors.ResultExistsError as e:
            logger.exception('ResultExistsError')
            abort(404) 
        except Exception as e:
            logger.exception('Unhandled Error')
            abort(500)
        else:
            return ('', 200)

@ns_workers.route('/')
class WorkersListAPI(Resource):

    @ns_doc.marshal_with(_worker, as_list=True)
    def get(self):
        if not cfg.RABBITMQ.MANAGEMENT:
            # no rabbitmq management plugin, so cant query workers
            abort(405)
        else:
            virtual_host = ''

            url = 'http://%s:%s/api/queues/%s' % (cfg.RABBITMQ.MANAGEMENT_HOST, 
                    cfg.RABBITMQ.MANAGEMENT_PORT, virtual_host)

            response = requests.get(url, auth=(cfg.RABBITMQ.USER, 
                cfg.RABBITMQ.PASSWORD))

            workers = [{'name': q['name'], 
                'active_workers': q['consumers'], 
                'in_queue': q['messages']}
                for q in response.json() 
                    if q['name'] != cfg.RABBITMQ.RESPONSE_QUEUE]

            return workers

@ns_workers.route('/<task_key>')
class WorkersAPI(Resource):

    @ns_doc.marshal_with(_workerTasks)
    def get(self, task_key):

        # Get tasks which are assigned to this worker that errored
        query = {
             "_source": "task",
              "query": {
                "bool": {
                  "must": [
                    {
                      "has_parent": {
                        "parent_type": "document",
                        "query": { 
                          "exists": {
                            "field": "target.id"
                          }
                        }
                      }
                    }
                  ],
                  "must_not": [
                     {
                      "match": {
                        "task.state": 102
                      }
                    }, {
                      "match": {
                        "task.state": 200
                      }
                    }, {
                      "match": {
                        "task.state": 201
                      }
                    }, {
                      "match": {
                        "task.state": 412
                      }
                    }

                  ]
                }
              }
            }

        if task_key is not None:
            query['query']['bool']['must'].append({
                  "match": {
                    "task.key": task_key
                  }
                })
        
        result = get_handler().es.search(index=INDEX, body=query, size=20)
        if result['hits']['total']['value'] > 0:
            tasks = [{'_id': t['_id'], 
                'key': t['_source']['task']['key'],
                'state': t['_source']['task']['state'],
                'msg': t['_source']['task']['msg']} for t \
                    in result['hits']['hits']]
        else:
            tasks = []

        return {'total': result['hits']['total']['value'], 'tasks': tasks}

@ns_workers.route('/<task_key>/reset')
@ns_workers.route('/<task_key>/reset/<task_state>')
class WorkersAPI(Resource):

    @ns_doc.marshal_with(_massResetResult)
    def get(self, task_key, task_state = 500):

        # Get tasks which are assigned to this worker that errored
        query = {
              "query": {
                "bool": {
                  "must": [
                    {
                      "match": {
                        "task.key": task_key
                      }
                    },
                    {
                      "match": {
                        "task.state": task_state
                      }
                    }
                  ]
                }
              },
              "script": {
                "source": "ctx._source['task']['state'] = 205; ctx._source['task']['msg'] = 'Manual reset';"
              }
            }
        
        try:
            result = get_handler().es.update_by_query(index=INDEX, body=query, refresh=True)
            return {'total': result['total'], 'error' : "No tasks affected" if result['total'] == 0 else ""}
        except Exception as e:
            logger.exception("Mass reset error")
            return {'total': 0, 'error': e}

"""------------------------------------------------------------------------------
DevOPs checks
------------------------------------------------------------------------------"""

@app.route('/health', methods=["GET"])
def HealthCheck():
    return ('', 200)

@app.route('/ready', methods=["GET"])
def ReadyCheck():
    states = {}

    try:
        get_handler().es.ping()
    except Exception as e:
        logging.exception('ReadyCheck Exception')
        states['database'] = False
    else:
        states['database'] = True

    states['messagequeue'] = get_queue().connection.is_open

    overall = all(states.values())

    for service, state in states.items():
        if state:
            states[service] = "200 OK"
        else:
            states[service] = "502 Bad Gateway"

    return Response(json.dumps(states), 
            status=200 if overall else 500, mimetype='application/json')

"""------------------------------------------------------------------------------
DANE web admin thingy
------------------------------------------------------------------------------"""

@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('js', path)

@app.route('/manage/')
def manager():
    return app.send_static_file('index.html')

"""------------------------------------------------------------------------------
------------------------------------------------------------------------------"""

app.register_blueprint(bp, url_prefix='/DANE')

def get_queue():
    if 'messageQueue' not in g:
        g.messageQueue = RabbitMQPublisher(cfg)
    return g.messageQueue

def get_handler():
    if 'handler' not in g:
        g.handler = Handler(config=cfg, queue=get_queue())
        get_queue().assign_callback(g.handler.callback)
    return g.handler

def main():
    app.run(port=cfg.DANE.PORT, host=cfg.DANE.HOST, use_reloader=True)

if __name__ == '__main__':
    main()
