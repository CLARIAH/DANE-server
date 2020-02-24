import mysql.connector as mariadb
import mysql.connector.pooling as mypool
from mysql.connector import errorcode
import json
import os
import logging
from functools import partial

import DANE
import DANE.base_classes
import threading

logger = logging.getLogger('DANE-server')

def createDatabase(cursor, dbname):
    try:
        cursor.execute("CREATE DATABASE `{}` DEFAULT CHARACTER SET 'utf8'".format(dbname))
    except mariadb.Error as err:
        logger.exception("Database creation failed")
        raise err

def createJobsTable(cursor):	
    cursor.execute("SHOW TABLES LIKE 'danejobs'")
    result = cursor.fetchone()
    if not result:
        logging.debug('Jobs table not found. Creating..')
        tableMasterJobs = (
            "CREATE TABLE IF NOT EXISTS `danejobs` ("	
            "  `job_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,"
            "  `source_url` TEXT NOT NULL,"
            "  `source_id` varchar(100) NOT NULL,"
            "  `priority` varchar(10) NOT NULL,"
            "  `tasks` JSON NOT NULL,"
            "  `metadata` JSON NOT NULL,"
            "  `response` JSON NOT NULL,"
            "  PRIMARY KEY (`job_id`)"
            ") ENGINE=InnoDB")
        cursor.execute(tableMasterJobs)

def createTasksTable(cursor):	
    cursor.execute("SHOW TABLES LIKE 'danetasks'")
    result = cursor.fetchone()
    if not result:
        logging.debug('Tasks table not found. Creating..')
        tableTasks = (
            "CREATE TABLE IF NOT EXISTS `danetasks` ("
            "  `task_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,"
            "  `job_id` INT UNSIGNED NOT NULL,"
            "  `task_key` varchar(100) NOT NULL,"
            "  `task_state` varchar(100) NOT NULL,"
            "  `task_msg` TEXT,"
            "  PRIMARY KEY (`task_id`),"
            "  CONSTRAINT `task_jobs_fk` FOREIGN KEY (`job_id`)"
            "    REFERENCES `danejobs` (`job_id`) ON DELETE CASCADE"  
            ") ENGINE=InnoDB")
        cursor.execute(tableTasks)

class SQLHandler(DANE.base_classes.base_handler):

    def __init__(self, config, queue):  
        super().__init__(config)
        self.queue = queue
        self.queue.assign_callback(self.callback)
        self.config = config

        self.connect()

        th = threading.Timer(interval=3, function=self._resume_unfinished)
        th.daemon = True
        th.start()
        
    def connect(self):
        myconfig = self.config['MARIADB']
        dbconfig = {
                'pool_name':"dane-pool",
                'pool_size': 5,
                'block': True,
                'timeout': 5,
                'user' : myconfig['user'],
                'password' : myconfig['password'],
                'host' : myconfig['host'],
                'port' : myconfig['port']
            }

	#Check if management DB exists
        try:
            self.pool = BlockingMySQLConnectionPool(
                    database=myconfig['database'],
                    **dbconfig)

            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
        except mariadb.errors.InterfaceError:
            logger.exception("Database unavailable")
            raise DANE.errors.ResourceConnectionError('Database unavailable, '\
                    'refer to logs for more details') 
        except mariadb.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                logger.exception("Invalid login credentials")
                raise DANE.errors.ResourceConnectionError('Invalid login credentials, '\
                    'refer to logs for more details') 
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                conn = mariadb.connect(**dbconfig)
                cursor = conn.cursor(dictionary=True)

                createDatabase(cursor, myconfig['database'])
                self.pool = BlockingMySQLConnectionPool(
                        database=myconfig['database'],
                        **dbconfig)
                cursor.close()
                conn.close()
            else:
                raise err

        #Create table if not exist
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            createJobsTable(cursor)
            createTasksTable(cursor)
        except mariadb.Error as err:
            logger.exception("Table creation failed")
            raise DANE.errors.ResourceConnectionError('DB creation failed, '\
                'refer to logs for more details') 

        cursor.close()
        conn.close()

    def _get_connection(self):
        try:
            conn = self.pool.get_connection()
        except mariadb.errors.InterfaceError as e:
            logger.exception("Database unavailable")
            raise DANE.errors.ResourceConnectionError('Database unavailable, '\
                    'refer to logs for more details')
        except mariadb.errors.PoolError as e:
            logger.exception("ConnectionPool exhausted")
            raise DANE.errors.ResourceConnectionError('ConnectionPool '\
                    'exhausted, '\
                    'refer to logs for more details')
        except Exception as e:
            logger.exception("Unhandled SQL error")
            raise e
        else:
            return conn

    def _resume_unfinished(self):
        unfinished = self.getUnfinished()['jobs']
        if len(unfinished) > 0:
            logger.info("Attempting to resume unfinished jobs")
            for jid in unfinished:
                job = self.jobFromJobId(jid)
                job.retry()

    def get_dirs(self, job):
        # expect that TEMP and OUT folder exist 
        TEMP_SOURCE = self.config['TEMP_FOLDER']
        OUT_SOURCE = self.config['OUT_FOLDER']

        if not os.path.exists(TEMP_SOURCE):
            os.mkdir(TEMP_SOURCE)
        if not os.path.exists(OUT_SOURCE):
            os.mkdir(OUT_SOURCE)

        # Get a more specific path name, by chunking id into (at most)
        # three chunks of 2 characters
        chunks = os.path.join(*[job.source_id[i:2+i] for i in range(0, 
            min(len(job.source_id),6), 2)])
        TEMP_DIR = os.path.join(TEMP_SOURCE, chunks, job.source_id)
        OUT_DIR = os.path.join(OUT_SOURCE, chunks, job.source_id)

        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)
        if not os.path.exists(OUT_DIR):
            os.makedirs(OUT_DIR)

        return {
            'TEMP_FOLDER': TEMP_DIR,
            'OUT_FOLDER': OUT_DIR
        }
 
    def register_job(self, job):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        addJobStatement = ("INSERT INTO `danejobs` "
            "(`source_url`, `source_id`, "
            "`priority`, `tasks`, `metadata`, `response`) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )        
        jobData = (job.source_url, job.source_id, 
                job.priority, job.tasks.to_json(),
                json.dumps(job.metadata), json.dumps(job.response))
        
        cursor.execute(addJobStatement, jobData)
        job_id = cursor.lastrowid
        
        conn.commit()            
        cursor.close()
        conn.close()

        logger.info("Registered new job #{}".format(job_id))
        
        return job_id

    def propagate_task_ids(self, job):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        updateStatement = ("UPDATE `danejobs` "
            "SET `tasks` = %s "
            "WHERE `job_id` = %s"
        )        
        
        cursor.execute(updateStatement, 
                (job.tasks.to_json(), job.job_id))

        conn.commit()            
        cursor.close()
        conn.close()
        
    def register(self, job_id, task):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        addTaskStatement = ("INSERT INTO `danetasks` "
            "(job_id, task_key, task_state, task_msg) "
            "VALUES (%s, %s, %s, %s)"
        )
        taskData = (job_id, task.task_key, 201, 'Created')

        cursor.execute(addTaskStatement, taskData)
        task_id = cursor.lastrowid

        conn.commit()            
        cursor.close()
        conn.close()

        return task_id

    def taskFromTaskId(self, task_id):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = ("""SELECT * FROM `danetasks`
                 WHERE `task_id`=%s""")
        
        cursor.execute(query, (int(task_id),))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result is not None:
            task_str = json.dumps({'Task' : result})
            task = DANE.Task.from_json(task_str)
            task.set_api(self)
            return task
        else:
            logging.error(
                    "No taskFromTaskId result for task_id: {}".format(task_id))
            raise KeyError("No result for given task id")

    def getTaskState(self, task_id):
        return int(self.taskFromTaskId(task_id).task_state)

    def getTaskKey(self, task_id): 
        return self.taskFromTaskId(task_id).task_key

    def _set_task_states(self, states, task):
        tid = task.task_id
        for s in states:
            if s['task_id'] == tid:
                task.task_state = int(s['task_state'])
                task.task_msg = s['task_msg']
                return

    def _jobFromResult(self, result, get_state=False):
        result['tasks'] = json.loads(result['tasks'])

        result['metadata'] = json.loads(result['metadata'])
        result['response'] = json.loads(result['response'])

        job = DANE.Job.from_json(json.dumps(result))
        job.set_api(self)

        if get_state:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            query = ("""SELECT * FROM `danetasks` WHERE job_id=%s""")
            
            cursor.execute(query, (int(job.job_id),))
            
            task_states = cursor.fetchall()
            cursor.close()
            conn.close()

            partf = partial(self._set_task_states, task_states)
            job.apply(partf)

        return job

    def jobFromJobId(self, job_id, get_state=False):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = ("""SELECT * FROM `danejobs` WHERE job_id=%s""")
        
        cursor.execute(query, (int(job_id),))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result is not None:
            return self._jobFromResult(result, get_state)
        else:
            logging.error(
                    "No jobFromJobId result for job_id: {}".format(job_id))
            raise KeyError("No result for given job id")

    def jobFromTaskId(self, task_id):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = ("""SELECT jobs.* FROM `danejobs` as jobs, `danetasks` as tasks
                 WHERE tasks.task_id=%s AND jobs.job_id = tasks.job_id""")
        
        cursor.execute(query, (int(task_id),))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result is not None:
            return self._jobFromResult(result)
        else:
            logging.error(
                    "No jobFromTaskId result for task_id: {}".format(task_id))
            raise KeyError("No result for given task id")

    def _run(self, task_id):
        job = self.jobFromTaskId(task_id)
        
        filetype = 'unknown' 
        # Check if downloader tried to infer the filetype
        if 'DOWNLOAD' in job.response.keys() and \
                'file_type' in job.response['DOWNLOAD'].keys():
            filetype = job.response['DOWNLOAD']['file_type'].lower()

        task_key = self.getTaskKey(task_id)
        routing_key = "{}.{}".format(filetype, task_key)

        if not self.queue.thread.isAlive():
            logger.critical("MessageQueue no longer handling callbacks")
            raise ConnectionError('MessageQueue no longer handling callbacks.')

        logger.info("Queueing task {} ({}) of job {}".format(task_id,
            task_key, job.job_id))
        self._update_state(task_id, 102, 'Queued', None)
        self.queue.publish(routing_key, task_id, job)

    def run(self, task_id):
        task_state = self.getTaskState(task_id)
        if task_state == 201:
            # Fresh of the press task, run it no questions asked
            self._run(task_id)
        elif task_state in [502, 503]:
            # Task that might be worth automatically retrying 
            self._run(task_id)
        else:
            # Requires manual intervention
            # and job resubmission once issue has been resolved
            pass

    def retry(self, task_id, force=False):
        task_state = self.getTaskState(task_id)
        if task_state not in [102, 200] or Force:
            # Unless its already been queued or completed, we can run this again
            # Or we can force it to run again
            self._run(task_id)

    def callback(self, task_id, response):
        task_key = self.getTaskKey(task_id)

        state = int(response.pop('state'))
        message = response.pop('message')

        if state != 200:
            logger.warning("Task {} [{}] failed with msg: #{} {}".format(
                task_key, task_id, state, message))            
        else:
            logger.info("Callback for task {} ({})".format(task_id, task_key))

        resp = { task_key : response } # group response by task_key

        self._update_state(task_id, state, message, resp)

        job = self.jobFromTaskId(task_id)
        job.set_api(self)
        job.run()

    def _update_state(self, task_id, state, message, response):        
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        if response is not None and len(response) > 0:
            updateStatement = ("UPDATE `danejobs` as jobs, `danetasks` as tasks "
                "SET jobs.response = IF("
                        "jobs.response IS NULL OR "
                        "JSON_TYPE(jobs.response) != 'OBJECT', "
                        "JSON_OBJECT(), "
                        "jobs.response), "
                "jobs.response = JSON_MERGE_PRESERVE(jobs.response, %s), "
                "tasks.task_state = %s, "
                "tasks.task_msg = %s "
                "WHERE tasks.task_id=%s AND jobs.job_id = tasks.job_id"
            )        

            cursor.execute(updateStatement, 
                    (json.dumps(response), state, 
                        message, task_id))
        else:
            updateStatement = ("UPDATE `danejobs` as jobs, `danetasks` as tasks "
                "SET tasks.task_state = %s, "
                "tasks.task_msg = %s "
                "WHERE tasks.task_id=%s AND jobs.job_id = tasks.job_id"
            )        

            cursor.execute(updateStatement, 
                    (state, message, task_id))

        conn.commit()            
        cursor.close()
        conn.close()

    def search(self, source_id):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = ("""SELECT job_id FROM `danejobs` WHERE source_id=%s""")
        cursor.execute(query, (source_id,))

        result = cursor.fetchall()
        cursor.close()
        conn.close()

        return {'jobs': [res['job_id'] for res in result]}

    def getUnfinished(self):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = ("SELECT job_id FROM `danejobs` WHERE job_id = "
                "ANY(SELECT job_id FROM `danetasks` "
                "WHERE `task_state` NOT IN (102, 200))")

        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        conn.close()

        return {'jobs': [res['job_id'] for res in result]}

class BlockingMySQLConnectionPool(mypool.MySQLConnectionPool):
    """Class defining a pool of MySQL connections, modified to allow for
    blocking get calls"""
    def __init__(self, block=True, timeout=None, **kwargs):
        self.block = block
        self.timeout = timeout
        super().__init__(**kwargs)

    def get_connection(self):
        """Get a connection from the pool
        This method returns an PooledMySQLConnection instance which
        has a reference to the pool that created it, and the next available
        MySQL connection.
        When the MySQL connection is not connect, a reconnect is attempted.
        Raises PoolError on errors.
        Returns a PooledMySQLConnection instance.
        """
        try:
            cnx = self._cnx_queue.get(block=self.block, 
                    timeout=self.timeout)
        except mypool.queue.Empty:
            raise mypool.errors.PoolError(
                "Failed getting connection; pool exhausted")

        # pylint: disable=W0201,W0212
        if not cnx.is_connected() \
                or self._config_version != cnx._pool_config_version:
            cnx.config(**self._cnx_config)
            try:
                cnx.reconnect()
            except mypool.errors.InterfaceError:
                # Failed to reconnect, give connection back to pool
                self._queue_connection(cnx)
                raise
            cnx._pool_config_version = self._config_version
        # pylint: enable=W0201,W0212

        return mypool.PooledMySQLConnection(self, cnx)
