import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from atlassian import Bitbucket
from datetime import datetime
from requests.exceptions import HTTPError
from settings.logger import logger
from settings.config import DRY_RUN, PROCESS_PROJECTS, PROCESS_GROUPS, PROCESS_USERS, PROJECT_WORKERS_COUNT, \
    GROUP_WORKERS_COUNT
from utils.utils import get_thread_num
from db.db_utils import insert_repositories, insert_groups, insert_contributors, insert_repository_users

from db.models import VCSInstance, User


class BitbucketParser:
    def __init__(self, vcs_instance: VCSInstance, username: str, password: str):
        self.instance = vcs_instance
        self._conn = Bitbucket(url=self.instance.url, username=username, password=password)

    @staticmethod
    def create_group_dict(group: dict, vcs_instance_id: int) -> dict:
        return {
            "vcs_instance_id": vcs_instance_id,
            "vcs_id": group['id'],
            "parent_id": None,
            "path": group['links']['self'][0]['href'],
            "visibility": "public" if group['public'] else "private"
        }

    @staticmethod
    def create_repo_dict(repo: dict, instance: VCSInstance, last_activity: datetime, default_branch: Optional[str]) -> dict:
        return {
            "vcs_instance_id": instance.id,
            "vcs_id": repo['id'],
            "path": repo['links']['self'][0]['href'].replace(instance.url + '/', ''),
            "group_id": repo['project']['id'],
            "parents": None,
            "web_url": repo['links']['self'][0]['href'],
            "git_url": repo['links']['clone'][0]['href'],
            "forks_count": 0,
            "created": None,
            "default_branch": default_branch,
            "last_time_checked": datetime.now(),
            "is_scanned": False,
            "last_time_scanned": None,
            "visibility": "public" if repo['public'] else "private",
            "last_activity_repo": last_activity,
            "last_commit_at": last_activity,
            "is_archived": False
        }

    @staticmethod
    def create_user_dict(vcs_instance_id: int, repo_id: int, user_id: int, permission: str) -> dict:
        return {
            "vcs_instance_id": vcs_instance_id,
            "repo_id": repo_id,
            "user_id": user_id,
            "access_level": permission
        }

    def _get_projects(self):
        return self._conn.project_list()

    def _get_groups(self):
        return self._conn.get_groups()

    def _process_repository(self, project_key: str, repo: dict) -> None:
        logger.info(f"- [T{get_thread_num()}] Processing repository '{repo['slug']}' (id={repo['id']})")
        try:
            repo_name = repo['slug']
            repo_id = repo['id']
            commits = self._conn.get_commits(project_key, repo_name, limit=1)
            try:
                last_commit = next(commits)
                last_activity = datetime.fromtimestamp(last_commit['authorTimestamp'] / 1000)
            except StopIteration:
                last_activity = datetime.fromtimestamp(0)
            branches = self._conn.get_branches(project_key, repo_name)
            default_branch = None
            for branch in branches:
                if branch['isDefault']:
                    default_branch = branch['id']
                    break
            repo_dict = self.create_repo_dict(repo, self.instance, last_activity, default_branch)
            insert_repositories({repo_id: repo_dict})
        except Exception as err:
            logger.error(
                f"- [T{get_thread_num()}] An unexpected error occurred while processing project '{repo_name}': {err.__class__.__name__} {str(err)}")
            return

    def _process_project(self, project: dict) -> None:
        try:
            project_key = project['key']
            logger.info(f"- [T{get_thread_num()}] Processing project '{project_key}' (id={project['id']})")
            repos = self._conn.repo_list(project_key)
            dry_count = 0
            with ThreadPoolExecutor(max_workers=PROJECT_WORKERS_COUNT) as queue:
                for repo in repos:
                    dry_count += 1
                    queue.submit(self._process_repository, project_key, repo)

                    if DRY_RUN and dry_count > 100:
                        break
                queue.shutdown(wait=True, cancel_futures=False)
        except HTTPError as err:
            print(str(err))
            exit(-1)
        except Exception as err:
            logger.error(
                f"- [T{get_thread_num()}] An unexpected error occurred while processing project '{project_key}' (id={project['id']}): {err.__class__.__name__} {str(err)}")
            exit(-1)

    def _process_group(self, project: dict) -> None:
        logger.debug(f"- [T{get_thread_num()}]: Trying group with id {id}/{project['id']}...")
        while True:
            try:
                logger.info(f"– [T{get_thread_num()}]: Processing group '{project['links']['self'][0]['href']}'")
                group_id = project['id']
                group_obj = self.create_group_dict(project, self.instance.id)
                insert_groups({group_id: group_obj})
                return
            except Exception as e:
                logger.error(
                    f"- [T{get_thread_num()}]: Got exception while trying to get group with id '{id}: '{str(e)}'")
                continue

    def _process_user(self, project_key: str) -> None:
        users = self._conn.project_users(project_key)
        if users:
            repos = self._conn.repo_list(project_key)
            for repo in repos:
                for user in users:
                    user_obj = User.get_or_create(vcs_instance_id=self.instance.id,
                                                  vcs_id=user['user']['id'],
                                                  name=user['user']['displayName'],
                                                  username=user['user']['name'],
                                                  state="active" if user['user']['active'] else "blocked",
                                                  locked=False if user['user']['active'] else True,
                                                  web_url=user['user']['links']['self'][0]['href'])
                    user_id = user_obj[0].vcs_id
                    user_dict = self.create_user_dict(self.instance.id, repo['project']['id'], user_id,
                                                      user['permission'])
                    insert_repository_users({user_id: user_dict})

    def _process_project_contributors(self, project_key: str) -> None:
        """
        Process the contributors of a project and insert their information into a dictionary.

        @param project_key: The key of the project containing the repository contributors.

        @return: None.
        """
        try:
            repos = self._conn.repo_list(project_key)

            for repo in repos:
                repo_slug = repo['slug']
                commits = self._conn.get_commits(project_key, repo_slug)
                contributors = {}

                for commit in commits:
                    author_email = commit['author']['emailAddress']
                    if author_email not in contributors:
                        contributors[author_email] = {
                            "email": author_email,
                            "commits": 0,
                            "additions": 0,
                            "deletions": 0,
                            "vcs_instance_id": self.instance.id,
                            "repo_id": repo['id']
                        }
                    contributors[author_email]["commits"] += 1

                for email, contributor_info in contributors.items():
                    contributor_insert_key = f"{repo['id']}{email}"
                    insert_contributors({contributor_insert_key: contributor_info})

        except Exception as err:
            logger.error(f"- [T{get_thread_num()}] Caught unexpected error: {err}")

    def process_instance(self) -> None:
        start_time = datetime.now()

        projects = self._get_projects()
        if PROCESS_PROJECTS:
            with ThreadPoolExecutor(max_workers=PROJECT_WORKERS_COUNT) as queue:
                dry_count = 0
                for project in projects:
                    dry_count += 1
                    queue.submit(self._process_project, project)

                    if DRY_RUN and dry_count > 100:
                        break
                queue.shutdown(wait=True, cancel_futures=False)

        if PROCESS_GROUPS:
            with ThreadPoolExecutor(max_workers=GROUP_WORKERS_COUNT) as queue:
                dry_count = 0
                for project in projects:
                    dry_count += 1
                    queue.submit(self._process_group, project)

                    if DRY_RUN and dry_count > 100:
                        break
                queue.shutdown(wait=True, cancel_futures=False)

        if PROCESS_USERS:
            with ThreadPoolExecutor(max_workers=PROJECT_WORKERS_COUNT) as queue:
                dry_count = 0
                for project in projects:
                    dry_count += 1
                    project_key = project['key']
                    queue.submit(self._process_user, project_key)
                    queue.submit(self._process_project_contributors, project_key)
                    if DRY_RUN and dry_count > 100:
                        break
                queue.shutdown(wait=True, cancel_futures=False)

        end_time = datetime.now()

        logger.info(
            f"'{self.instance.url}': processed in {end_time - start_time}")
