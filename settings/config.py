import os
import threading

import requests
import urllib3
from distutils.util import strtobool
from requests.adapters import HTTPAdapter


inventory_lock = threading.Lock()
fast_inventory_lock = threading.Lock()
# Disable ALL warnings from urllib3
urllib3.disable_warnings()

ENVIRONMENT = os.getenv('ENVIRONMENT', 'DEV')
FAST_INVENTORY_INTERVAL = int(os.getenv('FAST_INVENTORY_INTERVAL', default=1))
START_TIME = os.getenv('START_TIME', '09:45')
CONTAINER_NAME = os.getenv('CONTAINER_NAME', 'sg-images-inventory')
DEBUG_ENABLED = strtobool(os.getenv('DEBUG_ENABLED', default='False'))
DEBUG_LAST_ID = int(os.getenv('DEBUG_LAST_ID', default=0))
LOG_LEVEL = os.getenv('LOG_LEVEL', default='INFO')
INSERT_CHUNK_SIZE = int(os.getenv('INSERT_CHUNK_SIZE', default=50000))

DRY_RUN = strtobool(os.getenv('DRY_RUN', default='False'))

PROCESS_PROJECTS = strtobool(os.getenv('PROCESS_PROJECTS', default='True'))
PROCESS_GROUPS = strtobool(os.getenv('PROCESS_GROUPS', default='True'))
PROCESS_REGISTRIES = strtobool(os.getenv('PROCESS_REGISTRIES', default='False'))
PROCESS_USERS = strtobool(os.getenv('PROCESS_USERS', default='False'))
SKIP_SCANNED = strtobool(os.getenv('SKIP_SCANNED', default='False'))

PROJECT_WORKERS_COUNT = int(os.getenv('PROJECT_WORKERS_COUNT', default=20))
GROUP_WORKERS_COUNT = int(os.getenv('GROUP_WORKERS_COUNT', default=10))
FULL_UPDATE_DAY = int(os.getenv('FULL_UPDATE_DAY', default=6))

SESSION = requests.Session()
SESSION.mount('https://', HTTPAdapter(pool_maxsize=PROJECT_WORKERS_COUNT))

# Database envs
POSTGRES_HOST = os.getenv('POSTGRES_HOST', default='localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', default='5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', default='postgres')
POSTGRES_USER = os.getenv('POSTGRES_USER', default='postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', default='postgres')
POSTGRES_SCHEMA = os.getenv('POSTGRES_SCHEMA', default='public')
