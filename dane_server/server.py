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

from dane_server.handlers.SQLHandler import SQLHandler
from dane_server.util.RabbitMQUtil import RabbitMQUtil
import DANE
from DANE.config import cfg

bp = Blueprint('DANE', __name__)
app = Flask(__name__, static_url_path='/manage', 
        static_folder="web")

app.debug = True

logger = logging.getLogger('DANE-server')
level = logging.getLevelName(cfg.LOGGING.LEVEL)
logger.setLevel(level)
# create file handler which logs to file
if not os.path.exists(os.path.realpath(cfg.LOGGING.DIR)):
    os.mkdir(os.path.realpath(cfg.LOGGING.DIR))

fh = logging.FileHandler(os.path.join(
    os.path.realpath(cfg.LOGGING.DIR), "DANE-server.log"))
fh.setLevel(level)
# create console handler 
ch = logging.StreamHandler()
ch.setLevel(level)
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

@bp.route('/job', methods=["POST"])
def SubmitJob():
    postData = None

    try:
        postData = request.data
    except Exception as e:
        logger.exception('Error handling post data')
        abort(500) # TODO handle this nicer

    try:
        job = DANE.Job.from_json(postData)
    except (TypeError, json.decoder.JSONDecodeError) as e:
        logger.exception('FormatError')
        abort(400, 'Invalid job format')
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500)

    try:
        job.set_api(handler)
        job.register()
        job.run()

        job.refresh()
    except Exception as e:
        logger.exception('Unhandled Error')
        abort(500, str(e))

    return Response(job.to_json(), status=201, mimetype='application/json')

@bp.route('/job/<job_id>', methods=["GET"])
def GetJob(job_id):
    try:
        job_id = int(job_id)
        job = handler.jobFromJobId(job_id, get_state=True)
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
        return Response(job.to_json(), status=200, mimetype='application/json')

@bp.route('/job/<job_id>/retry', methods=["GET"])
def RetryJob(job_id):
    try:
        job_id = int(job_id)
        job = handler.jobFromJobId(job_id, get_state=True)
        job.retry().refresh()
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
        return Response(job.to_json(), status=200, mimetype='application/json')

@bp.route('/job/<job_id>/delete', methods=["GET"])
def DeleteJob(job_id):
    try:
        job_id = int(job_id)
        job = handler.jobFromJobId(job_id, get_state=True)
        job.delete()
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

@bp.route('/job/search/<source_id>', methods=["GET"])
def search(source_id):
    result = handler.search(source_id=source_id)
    return Response(json.dumps(result), status=200, mimetype='application/json')

@bp.route('/job/inprogress', methods=["GET"])
def inprogress():
    result = handler.getUnfinished()
    return Response(json.dumps(result), status=200, mimetype='application/json')

@bp.route('/task/<task_id>', methods=["GET"])
def GetTask(task_id):
    try:
        task_id = int(task_id)
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

@bp.route('/task/<task_id>/forceretry', methods=["GET"])
def RetryTask(task_id):
    try:
        task_id = int(task_id)
        task = handler.taskFromTaskId(task_id)
        task.retry(force=True).refresh()
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

@bp.route('/task/<task_id>/reset', methods=["GET"])
def ResetTask(task_id):
    try:
        task_id = int(task_id)
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

if not os.path.exists(cfg.DANE_SERVER.TEMP_FOLDER):
    os.makedirs(cfg.DANE_SERVER.TEMP_FOLDER)
if not os.path.exists(cfg.DANE_SERVER.OUT_FOLDER):
    os.makedirs(cfg.DANE_SERVER.OUT_FOLDER)

# should these be global vars?
messageQueue = RabbitMQUtil(cfg)
handler = SQLHandler(config=cfg, queue=messageQueue)

def main():
    messageQueue.run()
    app.run(port=cfg.DANE.PORT, host=cfg.DANE.HOST, use_reloader=False)

if __name__ == '__main__':
    main()
