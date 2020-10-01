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

from flask import Flask
from flask import render_template, redirect, url_for, Blueprint, abort, send_from_directory
from flask import request, Response, make_response

from functools import wraps

import json
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import quote
import requests

from dane_server.handler import Handler, INDEX
from dane_server.RabbitMQListener import RabbitMQListener
import DANE
from DANE.config import cfg

bp = Blueprint('DANE', __name__)
app = Flask(__name__, static_url_path='/manage', 
        static_folder="web")

app.debug = True

logger = logging.getLogger('DANE')
logger.setLevel(cfg.LOGGING.LEVEL)
# create file handler which logs to file
if not os.path.exists(os.path.realpath(cfg.LOGGING.DIR)):
    os.mkdir(os.path.realpath(cfg.LOGGING.DIR))

fh = TimedRotatingFileHandler(os.path.join(
    os.path.realpath(cfg.LOGGING.DIR), "DANE-server.log"), 
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

"""------------------------------------------------------------------------------
AUTHENTICATION (unused)
------------------------------------------------------------------------------"""

def check_auth(username, password):
	return username == 'admin' and password == '1234'

def authenticate():
	return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def isLoggedIn(request):
	if request.authorization:
		return True
	return False

def requires_auth(f):
	@wraps(f)
	def decorated(*args, **kwargs):
		auth = request.authorization
		if not auth or not check_auth(auth.username, auth.password):
			return authenticate()
		return f(*args, **kwargs)
	return decorated

"""------------------------------------------------------------------------------
REGULAR ROUTING 
------------------------------------------------------------------------------"""

@bp.route('/document', methods=["POST"])
def SubmitDocument():
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
        doc.set_api(handler)
        doc.register()

    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500, str(e))

    return Response(doc.to_json(), status=201, mimetype='application/json')

@bp.route('/document/<doc_id>', methods=["GET"])
def GetDocument(doc_id):
    try:
        doc_id = quote(doc_id) # escape potential nasties
        doc = handler.documentFromDocumentId(doc_id)
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return Response(doc.to_json(), status=200, mimetype='application/json')

@bp.route('/document/<doc_id>/tasks', methods=["GET"])
def GetDocumentTasks(doc_id):
    try:
        doc_id = quote(doc_id) # escape potential nasties
        doc = handler.documentFromDocumentId(doc_id)
        tasks = doc.getAssignedTasks()
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return Response(json.dumps(tasks), status=200, mimetype='application/json')

@bp.route('/document/<doc_id>/delete', methods=["GET"])
def DeleteDocument(doc_id):
    try:
        doc_id = quote(doc_id) # escape potential nasties
        doc = handler.documentFromDocumentId(doc_id)
        doc.delete()
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return ('', 200)

@bp.route('/document/search/<target_id>/<creator_id>', methods=["GET"])
def search(target_id, creator_id):
    target_id = quote(target_id).replace('%2A', '*')
    creator_id = quote(creator_id).replace('%2A', '*')
    result = handler.search(target_id, creator_id)
    return Response(json.dumps(result), status=200, mimetype='application/json')

@bp.route('/task', methods=["POST"])
def SubmitTask():
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
        task.set_api(handler)

        if isinstance(docs, list):
            tasks = task.assignMany(docs)
            resp = {}
            resp['success'] = []
            resp['failed'] = []
            for d,t in tasks.items():
                if isinstance(t, str):
                    resp['failed'].append((d, t))
                else:
                    resp['success'].append((d, t._id))

            return Response(json.dumps(resp), status=201, mimetype='application/json')
        else:
            task.assign(docs)    
            return Response(task.to_json(), status=201, mimetype='application/json')

    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500, str(e))

@bp.route('/task/<task_id>/delete', methods=["GET"])
def DeleteTask(task_id):
    try:
        task_id = quote(task_id) 
        task = handler.taskFromTaskId(task_id)
        task.delete()
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return ('', 200)

@bp.route('/task/<task_id>', methods=["GET"])
def GetTask(task_id):
    try:
        task_id = quote(task_id) 
        task = handler.taskFromTaskId(task_id)
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return Response(task.to_json(), status=200, mimetype='application/json')

@bp.route('/task/<task_id>/retry', methods=["GET"])
def RetryTask(task_id, force=False):
    try:
        task_id = quote(task_id) 
        task = handler.taskFromTaskId(task_id)
        task.retry(force=force).refresh()
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return Response(task.to_json(), status=200, mimetype='application/json')

@bp.route('/task/<task_id>/forceretry', methods=["GET"])
def ForceRetryTask(task_id):
    task_id = quote(task_id) 
    return RetryTask(task_id, True)

@bp.route('/task/<task_id>/reset', methods=["GET"])
def ResetTask(task_id):
    try:
        task_id = quote(task_id) 
        task = handler.taskFromTaskId(task_id)
        task.reset().refresh()
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return Response(task.to_json(), status=200, mimetype='application/json')

@bp.route('/task/inprogress', methods=["GET"])
def inprogress():
    result = handler.getUnfinished()
    return Response(json.dumps(result), status=200, mimetype='application/json')

@bp.route('/result/<result_id>', methods=["GET"])
def GetResult(result_id):
    try:
        result_id = quote(result_id) 
        result = handler.resultFromResultId(result_id)
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return Response(result.to_json(), status=200, mimetype='application/json')

@bp.route('/result/<result_id>/delete', methods=["GET"])
def DeleteResult(result_id):
    try:
        result_id = quote(result_id) 
        result = handler.resultFromResultId(result_id)
        result.delete()
    except TypeError as e:
        logger.exception('TypeError')
        abort(500)
    except KeyError as e:
        logger.exception('KeyError')
        abort(404) 
    except ValueError as e:
        logger.exception('ValueError')
        abort(400)
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)
    else:
        return ('', 200)

@bp.route('/workers', methods=["GET"])
def getWorkers():
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

        return Response(json.dumps(workers), status=200, mimetype='application/json')

@bp.route('/workers/<task_key>', methods=["GET"])
def getWorkerTasks(task_key):

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
                },
                {
                  "match": {
                    "task.key": task_key
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
    
    result = handler.es.search(index=INDEX, body=query, size=20)
    if result['hits']['total']['value'] > 0:
        tasks = [{'_id': t['_id'], 
            'key': t['_source']['task']['key'],
            'state': t['_source']['task']['state'],
            'msg': t['_source']['task']['msg']} for t \
                in result['hits']['hits']]
    else:
        tasks = []

    return Response(json.dumps(tasks), status=200, mimetype='application/json')


"""------------------------------------------------------------------------------
DevOPs checks
------------------------------------------------------------------------------"""

@bp.route('/health', methods=["GET"])
def HealthCheck():
    return ('', 200)

@bp.route('/ready', methods=["GET"])
def ReadyCheck():
    states = {}

    try:
        conn = handler._get_connection()
    except DANE.errors.ResourceConnectionError as e:
        logging.exception('ReadyCheck ResourceConnectionError')
        states['database'] = False
    except Exception as e:
        logging.exception('Unhandled readyCheck error')
        raise e
    else:
        states['database'] = conn.is_connected()
        conn.close()

    states['messagequeue'] = messageQueue.connection.is_open

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

# should these be global vars?
messageQueue = RabbitMQListener(cfg)
handler = Handler(config=cfg, queue=messageQueue)
messageQueue.run()

def main():
    app.run(port=cfg.DANE.PORT, host=cfg.DANE.HOST, use_reloader=True)

if __name__ == '__main__':
    main()
