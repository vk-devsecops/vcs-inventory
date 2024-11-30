import subprocess
import shlex
import shutil
from pathlib import Path

from db.models import ScanRepo, VSC, CompletedProcess, Finding, ScanRepo
from parsers.gitleaks_parser import GitleaksParser
from settings.logger import logger
from utils.exceptions import NoCommandForTool, NoParserForTool


PARSERS = {
    'gitleaks': GitleaksParser,
}

TOOL_CMD = {
        "gitleaks": {
                    "cmd": "gitleaks -c {config_path} detect -s {scan_folder} --exit-code 2 -f json -r {report_folder}/{report_name}",
                    "report": "report-gitleaks-nogit.json",
                    },
            }

RETURN_CODES = {
        'gitleaks': {0: {'success': True,
                         'description': 'gitleaks ran successfully and found no errors'},
                     1: {'success': False,
                         'description': 'gitleaks ran with errors'},
                     2: {'success': True,
                        'description': 'gitleaks ran successfully and found issues in your code'}
                     },
}

SCAN_TIMEOUT = 300


def clone_repository(vcs: VSC, repository: ScanRepo, dirname: str, key: str=None) -> CompletedProcess:
    logger.info(f"Cloning '{repository.git_url}'...")
    if repository.git_url.startswith('ssh://'):
        if not key:
            logger.error(f"Protocol is 'ssh://' and no 'key' passed, skipping repository...")
            return
        git_ssh_command = f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
        env = {"GIT_SSH_COMMAND": git_ssh_command}
        run_command = [
            "git", "clone", "--depth", "2", "-q", repository.git_url, dirname
            ]
    elif repository.git_url.startswith('http://') or repository.git_url.startswith('https://'):
        run_command = [
            "git", "clone", "--depth", "2", "-q", f"https://{vcs.username}:{vcs.token}@{repository.git_url[8:]}", dirname
        ]
        env = {}

    return subprocess.run(run_command, env=env, stdout=subprocess.DEVNULL, check=True)


def get_cmd_for_scan(tool: str, source_folder: str, report_name: str, config: Path) -> list[str]:
    command_template = TOOL_CMD[tool]["cmd"]
    command = command_template.format(config_path=config, scan_folder=source_folder,
                                      report_folder=source_folder, report_name=report_name)

    return shlex.split(command)


def is_scan_success(rc: int, tool_name: str) -> bool:
    return True if (tool_name in RETURN_CODES) and (RETURN_CODES[tool_name].get(rc)) and \
            (RETURN_CODES[tool_name][rc].get('success') is True) else False


def run_instrument_scan(run_scan_cmd: list[str]) -> CompletedProcess:
    try:
        process = subprocess.Popen(run_scan_cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f"Running '{run_scan_cmd}'...")
        stdout, stderr = process.communicate(timeout=SCAN_TIMEOUT)
        return CompletedProcess(stdout.decode(), stderr.decode(), process.returncode)

    except Exception as e:
        logger.error(f"Error on instrument scan {e} {type(e).__name__} {__file__} {e.__traceback__.tb_lineno}")
        raise ChildProcessError


def scan_project(folder: str, tool: str, config: Path) -> tuple[CompletedProcess, str]:
    if tool not in TOOL_CMD:
        raise NoCommandForTool
    report_name = TOOL_CMD[tool]["report"]
    run_scan_cmd = get_cmd_for_scan(tool, folder, report_name, config)
    completed_process = run_instrument_scan(run_scan_cmd)

    return completed_process, report_name


def parse_report(scan_folder: str, report: str, tool: str, repo: ScanRepo) -> list[Finding]:
    if tool not in PARSERS:
        raise NoParserForTool
    parser = PARSERS[tool](repo)
    path_to_report = Path(scan_folder) / Path(report)
    logger.info(f"Parsing '{path_to_report}'...")
    with open(path_to_report, 'r') as file:
        all_findings = parser.get_findings(file)
    logger.info(f"Got {len(all_findings)} findings")

    return all_findings
