#!/bin/python3

from datetime import datetime
from time import sleep

import schedule

from db.db_utils import fetch_vcs_instances, initialize_database
from db.models import VCSInstance, Repository, Group, Registry, Image, User, Contributor, RepositoryUser, Repository, database_proxy
from parsers.gitlab_parser import GitLabParser
from parsers.bitbucket_parser import BitbucketParser
from settings.config import *
from settings.yaml_parser import process_yaml, SETTINGS_FILE
from settings.logger import logger
from utils.exceptions import CantInitParserObject


def process_vcs_instance(instance: VCSInstance) -> None:
    try:
        if instance.type == "gitlab":
            parser = GitLabParser(vcs_instance=instance,
                                  token=vcs_instances[instance.mnemonic]['PAT'])
        elif instance.type == "bitbucket":
            parser = BitbucketParser(vcs_instance=instance,
                                     username=vcs_instances[instance.mnemonic]['USERNAME'],
                                     password=vcs_instances[instance.mnemonic]['PAT'])
        else:
            logger.critical(f"Unsupported instance type: '{instance.type}'!")
            return
        logger.info(f"Start processing {instance.type} instance '{instance.url}'...")
        parser.process_instance()
    except CantInitParserObject as e:
        logger.error(
            f"Error on connecting to {instance.type} instance '{instance.url}': {e} {type(e).__name__} {__file__} {e.__traceback__.tb_lineno}")


def inventory() -> None:
    if inventory_lock.acquire(blocking=False):
        try:
            logger.info(f"Starting an inventory at {datetime.now()}")
            instances = fetch_vcs_instances()

            for instance in instances:
                if instance.mnemonic not in vcs_instances:
                    logger.critical(f"No '{instance.mnemonic}' in '{SETTINGS_FILE}'! Skipping it...")
                    continue
                process_vcs_instance(instance)

        finally:
            inventory_lock.release()
    else:
        logger.warning("Inventory is already running, skipping this execution.")


def fast_inventory() -> None:
    if fast_inventory_lock.acquire(blocking=False):
        try:
            logger.info(f"Running fast inventory...")
            try:
                instances = fetch_vcs_instances()

                for instance in instances:
                    if instance.type == 'gitlab':
                        logger.info(f"Start processing ({instance.url})...")
                        instance_processor = GitLabParser(instance, instance.mnemonic['PAT'])

                        instance_processor.process_new_projects(instance.id)
                        instance_processor.process_new_groups(instance.id)

            except Exception as e:
                logger.error(f"{e} {type(e).__name__} {__file__} {e.__traceback__.tb_lineno}")
        finally:
            fast_inventory_lock.release()
    else:
        logger.warning("Fast inventory is already running, skipping this execution.")


def schedule_inventory() -> None:
    logger.info(f"Next launch scheduled at {START_TIME}. Now chilling...")
    logger.info(f"Fast inventory interval: {FAST_INVENTORY_INTERVAL=} minutes.")
    schedule.every().day.at(START_TIME).do(inventory)
    schedule.every(FAST_INVENTORY_INTERVAL).minutes.do(fast_inventory)


if __name__ == '__main__':
    logger.info("Starting inventory...")
    vcs_instances = process_yaml()
    initialize_database([Repository, Group, Registry, Image, User, Contributor, RepositoryUser, VCSInstance], vcs_instances=vcs_instances)

    if DRY_RUN:
        inventory()
    else:
        schedule_inventory()
        while True:
            schedule.run_pending()
            sleep(10)
