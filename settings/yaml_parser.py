import yaml
import sys
import os.path

from settings.logger import logger

SETTINGS_FILE = 'vcs-instances.yaml'


def parse_yaml(file_path: str) -> dict:
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)
    parsed_data = {}
    for key, value in data.items():
        parsed_data[key] = {k: v for item in value for k, v in item.items()}
    return parsed_data


def process_yaml(settings_file=SETTINGS_FILE) -> dict:
    logger.info(f"Parsing VCS instances from '{settings_file}'...")
    if not os.path.isfile(settings_file):
        logger.critical(f"'{settings_file}' not found! Cannot process, exitting...")
        exit(-1)
    vcs_instances = parse_yaml(settings_file)

    for instance in vcs_instances:
        logger.debug(f"Processing '{instance}'...")
        vcs_instance = vcs_instances[instance]
        for key in ('URL', 'TYPE', 'USERNAME', 'PAT'):
            if key not in vcs_instance:
                logger.critical(f"'{instance}': {key} not provided! Cannot process, exitting...")
                exit(-1)
        if vcs_instance['TYPE'] not in ('gitlab', 'bitbucket'):
            logger.critical(f"'{instance}': unsupported VCS type:'{vcs_instance['TYPE']}'! Cannot process, exitting...")
            exit(-1)
        logger.debug(f"'{instance}': VCS type: {vcs_instance['TYPE']}")
    logger.info(f"'{settings_file}' processed successfully!")

    return vcs_instances
