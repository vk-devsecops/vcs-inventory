import argparse
import os
import shutil

from pathlib import Path
from shutil import which
from sys import exit

from db.db_utils import initialize_database, filter_repos, insert_findings
from db.models import VSC, Finding
from utils.scan import clone_repository, scan_project, is_scan_success, parse_report
from utils.exceptions import NoCommandForTool, NoParserForTool
from settings.logger import logger
from settings.yaml_parser import process_yaml


def scan(vsc: VSC, args: argparse.Namespace) -> None:
    repos = filter_repos(args.filter)
    logger.info(f"Got {len(repos)} repositories to scan.")

    for repo in repos:
        clone_dir = f"/tmp/scan/{repo.vcs.url.split('//')[-1]}/{repo.vcs_id}"
        os.makedirs(clone_dir, exist_ok=True)
        try:
            process = clone_repository(vsc, repo, clone_dir, args.key)
            if process.returncode:
                logger.error(f"Error while cloning '{repo.git_url}':\n{process.stderr}")
                raise ChildProcessError
            
            process, report = scan_project(clone_dir, args.tool, args.config)
            if not is_scan_success(process.returncode, args.tool):
                logger.error(f"Error while executing '{args.tool}':\n{process.stderr}")
                raise ChildProcessError
            
            findings = parse_report(clone_dir, report, args.tool, repo)
            insert_findings(findings)
        except NoCommandForTool:
            logger.critical(f"No command to run '{args.tool}'! Cannot proceed, exitting...")
            exit(-1)
        except NoParserForTool:
            logger.critical(f"No parser to process '{args.tool}' results! Cannot proceed, exitting...")
            exit(-1)
        except Exception as e:
            logger.error(
                f"Error on processing repo: {e} {type(e).__name__} {__file__} {e.__traceback__.tb_lineno}")
        finally:
            shutil.rmtree(clone_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-k', '--key', type=str, required=False, help="Path to the SSH key to use)")
    parser.add_argument('-f', '--filter', type=str, choices=['force', 'default'], required=True, help="Filter to apply ('force' or 'default')")
    parser.add_argument('-t', '--tool', type=str, required=True, help='Scanner name')
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to the configuration file')

    args = parser.parse_args()

    if not which(args.tool):
        logger.critical(f"Tool {args.tool} not installed! Exitting...")
        exit(-1)

    if not Path(args.config).exists():
        logger.critical(f"Config '{args.config}' not found! Exitting...")
        exit(-1)
    
    if args.key and not Path(args.key).exists():
        logger.critical(f"Key '{args.key}' not found! Exitting...")
        exit(-1)

    logger.info(f"Running '{args.tool}' with filter '{args.filter}'...")
    initialize_database([Finding])
    vcs_instances = process_yaml()

    for item in vcs_instances.values():
        vcs = VSC(item['TYPE'], item['URL'], item['USERNAME'], item['PAT'])
        scan(vcs, args)
