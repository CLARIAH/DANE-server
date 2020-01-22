config = {
        'RABBITMQ': {
            'host': 'localhost',
            'port': '5672', 
            'exchange': 'DANE-exchange',
            'response_queue': 'DANE-response-queue',
            'user': '',
            'password': ''
        },

        'MARIADB': {
            'user': 'root',
            'password': '',
            'host': 'localhost',
            'port': '3306',
            'database': 'DANE-sql-store'
            },

        'LOGGING': {
            "dir": "./LOGS/",
            "level": "DEBUG",
        },

	"TEMP_FOLDER": "/some/folder/DANE-data/TEMP/",
	"OUT_FOLDER": "/some/folder/DANE-data/OUT/"
}
