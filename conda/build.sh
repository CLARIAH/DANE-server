#!/bin/bash

$PYTHON setup.py install     # Python command to install the script.

curl -sS https://downloads.mariadb.com/MariaDB/mariadb_repo_setup | sudo bash
