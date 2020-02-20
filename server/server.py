from flask import Flask
from flask import render_template, redirect, url_for, Blueprint, abort, send_from_directory
from flask import request, Response, make_response
from flask_cors import CORS

from functools import wraps

import json
import os
import sys
import logging

from handlers.SQLHandler import SQLHandler
from util.RabbitMQUtil import RabbitMQUtil
import DANE

bp = Blueprint('DANE', __name__)
app = Flask(__name__, static_url_path='/manage', 
        static_folder="management")
CORS(app)

app.debug = True

import settings as settings

cfg = settings.config

logger = logging.getLogger('DANE-server')
level = logging.getLevelName(cfg['LOGGING']['level'])
logger.setLevel(level)
# create file handler which logs even debug messages
if not os.path.exists(os.path.realpath(cfg['LOGGING']['dir'])):
    os.mkdir(os.path.realpath(cfg['LOGGING']['dir']))

fh = logging.FileHandler(os.path.join(
    os.path.realpath(cfg['LOGGING']['dir']), "DANE-server.log"))
fh.setLevel(level)
# create console handler with a higher log level
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
        abort(500)

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
        job = handler.jobFromJobId(job_id, get_state=True)
        job.retry()
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
        job.refresh()
        return Response(job.to_json(), status=200, mimetype='application/json')

@bp.route('/job/search/<source_id>', methods=["GET"])
def search(source_id):
    result = handler.search(source_id=source_id)
    return Response(json.dumps(result), status=200, mimetype='application/json')

@bp.route('/job/inprogress', methods=["GET"])
def inprogress():
    result = handler.getUnfinished()
    return Response(json.dumps(result), status=200, mimetype='application/json')

@bp.route('/test', methods=["GET"])
def TestJob():
    job = DANE.Job(source_url='http://127.0.0.1/example',
            source_id='ITM123',
            tasks=DANE.taskSequential(['TEST', 
                DANE.taskParallel(['TEST', 'FOO'])]))

    job.set_api(handler)
    job.register()
    job.run()

    job.refresh()
    return Response(job.to_json(), status=201, mimetype='application/json')

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

if __name__ == '__main__':
    if not os.path.exists(cfg['TEMP_FOLDER']):
        os.makedirs(cfg['TEMP_FOLDER'])
    if not os.path.exists(cfg['OUT_FOLDER']):
        os.makedirs(cfg['OUT_FOLDER'])

    # should these be global vars?
    messageQueue = RabbitMQUtil(cfg)
    messageQueue.run()
    handler = SQLHandler(config=cfg, queue=messageQueue)

    app.run(port=cfg['DANE_PORT'], host=cfg['DANE_HOST'], use_reloader=False)
