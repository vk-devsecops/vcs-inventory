import argparse
import requests
import os
import urllib.parse

from peewee import SQL
from time import sleep


from settings.logger import logger
from settings.yaml_parser import process_yaml
from db.models import VSC, VCSInstance, Repository
from db.db_utils import initialize_database


def search(vsc: VSC, args: argparse.Namespace) -> None:
    keyword = urllib.parse.quote(args.keyword.strip("\""))
    
    result_dir = f"search/{vcs.url.split('//')[-1]}"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    repos = Repository.select(VCSInstance.url, Repository.vcs_id, Repository.path).join(VCSInstance).where(VCSInstance.url == vcs.url)
    if args.filter:
        logger.info(f"# Filter set to {args.filter}")
        repos = repos.where(SQL(args.filter.strip("\"")))

    repos_count = repos.count()
    logger.info(f"# {repos_count} repositories match in '{vcs.url}'. Searching '{keyword}' in them...")
    counter = 0
    for repo in repos:
        counter += 1
        logger.info(f"[{counter}/{repos_count}] # Searching '{keyword}' in '{vcs.url}/{repo.path}' (id:{repo.vcs_id})")
        try:
            while True:
                response = requests.get(f"{vcs.url}/api/v4/projects/{repo.vcs_id}/search?scope=blobs&search={keyword}",
                                        headers={'PRIVATE-TOKEN': vcs.token},
                                        timeout=40)
                if not response.ok:
                    logger.info(f"Got bad response while initing: {response}")
                    if response.status_code == 429:
                        logger.info("Got 429, retrying...")
                        sleep(1)
                        continue
                    response = []
                    break
                break
            response = response.json()
            if response == []:
                logger.info(f"[{counter}/{repos_count}] # Not found")
            else:
                file_name = f"{result_dir}/{repo.path.replace("/", "_")}.log"
                logger.info(f"[{counter}/{repos_count}] # Found! Writing result into {file_name}")
                with open(f"{file_name}", 'w') as file:
                    for item in response:
                        # Example: https://gitlab.mycompany.com/test_group/test_project/blob/master/README.md#L1
                        line_number = item['startline']+2 if item['startline']!=0 else item['startline']
                        link = f"{vcs.url}/{repo.path}/blob/{item['ref']}/{item['path']}#L{line_number}"
                        file.write(f"{link} :\n")
                        result = item['data'].replace("\n\n","\n")
                        file.write(f"{result}")
                        file.write(f"\n------------------------------------------------------\n\n")
        except Exception as e:
            logger.info(f"{e} {type(e).__name__} {__file__} {e.__traceback__.tb_lineno}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-k', '--keyword', type=str, required=False, help="Search keyword")
    parser.add_argument('-f', '--filter', type=str, required=False, help="SQL filter (in AND format)")
    args = parser.parse_args()
    
    if not args.keyword:
        logger.critical(f"Keyword (--keyword) not set! Exitting...")
        exit(-1)

    initialize_database([])

    vcs_instances = process_yaml()
    
    for item in vcs_instances.values():
        vcs = VSC(item['TYPE'], item['URL'], item['USERNAME'], item['PAT'])
        if vcs.type == 'gitlab':
            search(vcs, args)