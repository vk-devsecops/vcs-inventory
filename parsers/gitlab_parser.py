from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import dateutil.parser
from typing import Optional, Any

import gitlab
import gitlab.const
from gitlab.base import RESTObject
from gitlab.v4.objects import Project, ProjectRegistryRepository, ProjectRegistryTag

from db.db_utils import get_inventoried_projects_with_parents, fetch_tags, fetch_last_inventoried_group, \
    insert_repositories, insert_registries, insert_images, insert_contributors, insert_users, insert_repository_users, \
    insert_groups
from db.models import VCSInstance
from utils.exceptions import NoExistedRegistryTag, CantProcessGitlabRegistry, CantProcessProjectUsers, \
    CantInitParserObject
from settings.config import SESSION, GROUP_WORKERS_COUNT, PROJECT_WORKERS_COUNT, PROCESS_REGISTRIES, PROCESS_USERS, \
    DEBUG_LAST_ID, FULL_UPDATE_DAY, DRY_RUN, PROCESS_PROJECTS, PROCESS_GROUPS
from settings.logger import logger
from utils.utils import get_thread_num


class GitLabParser:
    def __init__(self, vcs_instance: VCSInstance, token: str):
        """
        Authenticates with a Gitlab instance using the provided URL and token.

        @param: url: The URL of the Gitlab instance.
        @param: token: The private token for authentication.

        @return: Optional[Gitlab]: The Gitlab instance if authentication is successful, None otherwise.
        """
        self.instance = vcs_instance
        try:
            self.gl = gitlab.Gitlab(session=SESSION, url=self.instance.url, private_token=token, ssl_verify=False,
                                    retry_transient_errors=True)
            self.gl.auth()
        except Exception as e:
            raise CantInitParserObject

    @staticmethod
    def _create_image_tag_dict(tag: ProjectRegistryTag, instance_id: int) -> dict:
        return {
                "vcs_instance_id": instance_id,
                "repo_id": tag.project_id,
                "registry_id": tag.repository_id,
                "path": tag.path,
                "tag": tag.name,
                "image": tag.location,
                "created_at": tag.created_at,
                "digest": tag.digest,
                "revision": tag.revision,
                "total_size": tag.total_size,
                "last_time_checked": datetime.now(),
                "is_scanned": False,
                "last_time_scanned": None,
                "last_scan_id": None
            }

    @staticmethod
    def _create_group_dict(group: ProjectRegistryRepository, vcs_instance_id: Optional[int]) -> dict:
        return {
            "vcs_instance_id": vcs_instance_id,
            "vcs_id": group.get_id(),
            "parent_id": group.parent_id,
            "path": group.full_path,
            "visibility": group.visibility
            }

    @staticmethod
    def _create_image_dict(registry: ProjectRegistryRepository, instance_id: int) -> dict:
        return {
            "vcs_instance_id": instance_id,
            "vcs_id": registry.get_id(),
            "repo_id": registry.project_id,
            "name": registry.path.split("/")[-1] if "/" in registry.path else registry.path,
            "path": registry.path,
            "web_url": registry.location,
            "created_at": registry.created_at,
            "last_time_checked": datetime.now(),
            "is_scanned": False,
            "last_time_scanned": None
        }

    @staticmethod
    def _create_project_dict(project: Project, project_parents: list, instance_id: int, last_commit_at: Optional[Any] = None) -> dict:
        return {
                "vcs_instance_id": instance_id,
                "vcs_id": project.get_id(),
                "path": project.path_with_namespace,
                "group_id": project.namespace['id'],
                "parents": project_parents,
                "web_url": project.web_url,
                "git_url": project.http_url_to_repo,
                "forks_count": len(project.forks.list(all=True)),
                "created": project.created_at,
                "default_branch": None,
                "last_time_checked": datetime.now(),
                "is_scanned": False,
                "last_time_scanned": None,
                "visibility": project.visibility,
                "last_activity_repo": dateutil.parser.isoparse(project.last_activity_at),
                "last_commit_at": last_commit_at,
                "is_archived": project.archived
            }

    def _process_groups(self, vcs_instance: VCSInstance, start_time: datetime, last_group_id: int) -> None:
        """
        Process groups from Gitlab instance.
    
        @param vcs_instance: VCSInstance object.
        @param start_time: Start time of the process.
        @param last_group_id: ID of the last group.
    
        @return: None.
        """
        logger.info(f"- Last group id is '{last_group_id}', using {GROUP_WORKERS_COUNT} workers... ")
        with ThreadPoolExecutor(max_workers=GROUP_WORKERS_COUNT) as groups_queue:
            dry_count = 0
            for group in self.gl.groups.list(order_by='id', sort='desc', iterator=True):
                dry_count += 1
                groups_queue.submit(self._process_group, start_time, group, last_group_id, vcs_instance.id)
                if DRY_RUN and dry_count > 100:
                    break
            groups_queue.shutdown(wait=True, cancel_futures=False)

    def process_new_groups(self, instance_id: int) -> None:
        """
        Process new Gitlab groups that have not been inventoried yet.
    
        @param instance_id: ID of the current instance
    
        @return: None
        """
        groups = self.gl.groups.list(get_all=False, per_page=1, order_by='id', sort='desc')
        last_gitlab_group_id = groups[0].id
        last_inventoried_group = fetch_last_inventoried_group(instance_id)

        last_inventoried_group_id = last_inventoried_group.vcs_id if last_inventoried_group else 0

        start_time = datetime.now()

        if last_gitlab_group_id > last_inventoried_group_id:
            new_groups_id = range(last_inventoried_group_id + 1, last_gitlab_group_id + 1)

            logger.info(
                f"Processing new gitlab groups "
                f"({last_gitlab_group_id - last_inventoried_group_id}) | "
                f"{last_inventoried_group_id=} | "
                f"{last_gitlab_group_id=}"
            )

            with ThreadPoolExecutor(max_workers=GROUP_WORKERS_COUNT) as groups_queue:
                for gr_id in new_groups_id:
                    try:
                        group = self.gl.groups.get(gr_id)
                        groups_queue.submit(self._process_group, start_time, group, last_gitlab_group_id, instance_id)
                    except Exception as e:
                        logger.error(f"Error processing group {gr_id}: {e}")

    def process_new_projects(self, instance_id: int) -> None:
        """
        Process new GitLab projects and update related data.
    
        @param instance_id: Instance ID
    
        @return: None
        """
        projects = self.gl.projects.list(get_all=False, per_page=1, order_by='id', sort='desc')
        last_gitlab_project_id = projects[0].id
        inventoried_projects_in_db, projects_parents = get_inventoried_projects_with_parents(instance_id)
        last_inventoried_project_id = inventoried_projects_in_db[0] if inventoried_projects_in_db else 0

        if last_gitlab_project_id > last_inventoried_project_id:
            new_projects_id = range(last_inventoried_project_id + 1, last_gitlab_project_id + 1)

            logger.info(
                f"Processing new gitlab projects "
                f"({last_gitlab_project_id - last_inventoried_project_id}) | "
                f"{last_inventoried_project_id=} | "
                f"{last_gitlab_project_id=}"
            )

            with ThreadPoolExecutor(max_workers=PROJECT_WORKERS_COUNT) as queue:
                for pr_id in new_projects_id:
                    try:
                        project = self.gl.projects.get(pr_id)

                        queue.submit(self._process_project, project, projects_parents, instance_id)
                        queue.submit(self._process_project_registry, project, instance_id)
                        queue.submit(self._process_project_users, project, instance_id)
                        queue.submit(self._process_project_contributors, project, instance_id)
                    except Exception as e:
                        logger.error(f"Error processing project {pr_id}: {e}")
                queue.shutdown(wait=True, cancel_futures=False)

    def _process_projects(self, vcs_instance: VCSInstance, last_project_id: int) -> None:
        """
           Process projects from Gitlab.
    
           @param vcs_instance: VCSInstance object containing information about the version control system.
           @param last_project_id: Integer representing the ID of the last project that was processed.
    
           @return: None
           """
        inventoried_projects_in_db, projects_parents = get_inventoried_projects_with_parents(vcs_instance.id)
        last_inventoried_project_in_db = max(inventoried_projects_in_db, default=0)
        if last_inventoried_project_in_db > last_project_id:
            last_inventoried_project_in_db = 0
            inventoried_projects_in_db = []

        logger.info(f"- Last project id in GT: '{last_project_id}'")
        logger.info(f"- Last project id in DB: '{last_inventoried_project_in_db}'")
        logger.info(f"- Will be processed using {PROJECT_WORKERS_COUNT} workers... ")
        with ThreadPoolExecutor(max_workers=PROJECT_WORKERS_COUNT) as queue:
            dry_count = 0
            for project in self.gl.projects.list(order_by='id', sort='desc', iterator=True):
                dry_count += 1
                is_inventoried = project.id in inventoried_projects_in_db
                queue.submit(self._process_project, project, projects_parents, vcs_instance.id)
                if PROCESS_REGISTRIES:
                    queue.submit(self._process_project_registry, project, vcs_instance.id)
                if PROCESS_USERS and (not is_inventoried or datetime.now().isoweekday() == FULL_UPDATE_DAY):
                    queue.submit(self._process_project_users, project, vcs_instance.id)
                    queue.submit(self._process_project_contributors, project, vcs_instance.id)
                if DRY_RUN and dry_count > 100:
                    break
            queue.shutdown(wait=True, cancel_futures=False)

    def _process_project_registry(self, project: Project, instance_id: int) -> None:
        """
        Process the GitLab project registry. This function retrieves the registries associated with the project,
        and for each registry, it calls the process_registry function. The results are then added to the
        registries_to_insert and images_to_insert dictionaries.
    
        @param project: An instance of the Project class.
        @param instance_id: An integer representing the ID of the instance.
    
        @return: None.
        """
        registries = self._get_registries(project)
        if not registries:
            logger.debug(f"- [T{get_thread_num()}] No registries in '{project.path}'")
            return

        for registry in registries:
            try:
                self._process_registry(registry, instance_id)
            except (NoExistedRegistryTag, CantProcessGitlabRegistry):
                continue

    def _get_last_project_id(self) -> int:
        """
        Retrieve the ID of the last project from the Gitlab instance.

        @return: The ID of the last project if it exists, otherwise 0.
        """
        try:
            last_project_id = DEBUG_LAST_ID if DEBUG_LAST_ID else \
                self.gl.projects.list(get_all=False, per_page=1, order_by='id', sort='desc')[0].id
            return last_project_id
        except Exception as e:
            logger.error(f"Error retrieving last project ID from Gitlab: {e}")
            return 0

    def _process_group(self, start_time: datetime, group, last_id: int, instance_id: Optional[int]) -> None:
        """
        Process a group and add it to a dictionary of groups to insert.
    
        @param start_time: The start time of the process.
        @param group: The group to process.
        @param last_id: The last ID of the group.
        @param instance_id: The ID of the instance (optional).
    
        @return: None
        """
        logger.debug(f"- [T{get_thread_num()}]: Trying group with id {id}/{last_id}...")
        while True:
            try:
                time_passed = str(datetime.now() - start_time).split(".")[0]
                logger.info(f"<{time_passed}> – [T{get_thread_num()}]: Processing group '{group.full_path}'")
                group_id = group.get_id()
                group_obj = self._create_group_dict(group, instance_id)
                insert_groups({group_id: group_obj})
                return
            except Exception as e:
                logger.error(
                    f"- [T{get_thread_num()}]: Got exception while trying to get group with id '{id}: '{str(e)}'")
                continue
    
    def _process_image(self, registry: ProjectRegistryRepository, tag: RESTObject, instance_id: int) -> None:
        """
        Process a GitLab image from the provided registry and tag, and return a dictionary of images to insert.
    
        @param registry: The project registry repository.
        @param tag: The RESTObject representing the image tag.
        @param instance_id: The ID of the instance.
    
        @return: None.
        """
        logger.debug(f"--- [T{get_thread_num()}] Processing image '{tag.location}'")
        try:
            tag = registry.tags.get(id=tag.name)
            image = self._create_image_tag_dict(tag, instance_id)
            insert_images({tag.location: image})
        except Exception as err:
            logger.error(
                f"--- [T{get_thread_num()}] Caught unexpected error while processing image '{tag.location['path']}': {err}")

    def _process_registry_tags(self, registry: ProjectRegistryRepository, instance_id: int) -> None:
        """
        Process registry tags, fetching and updating images based on the day of the week.
    
        @param registry: The project registry repository.
        @param instance_id: The ID of the instance.
    
        @return: None.
        """
        tags = registry.tags.list(iterator=True)
        if not tags:
            logger.debug(f"-- [T{get_thread_num()}] No tags in registry {registry.location}")
            raise NoExistedRegistryTag

        tags_in_db = fetch_tags(registry, instance_id)

        day_of_week = datetime.now().isoweekday()
        for tag in tags:
            if tag.path in tags_in_db and day_of_week != FULL_UPDATE_DAY:
                continue
            self._process_image(registry, tag, instance_id)

    def _process_registry(self, registry: ProjectRegistryRepository, instance_id: int) -> None:
        """
        Process a given registry and extract image and registry data.
    
        @param registry: An instance of ProjectRegistryRepository representing the registry to process.
        @param instance_id: An integer representing the ID of the instance.
    
        @return: None.
        """
        logger.debug(f"-- [T{get_thread_num()}] Processing registry '{registry.location}'")
        try:
            image = self._create_image_dict(registry, instance_id)
            insert_registries({registry.get_id(): image})
            self._process_registry_tags(registry, instance_id)
        except Exception as err:
            logger.error(
                f"-- [T{get_thread_num()}] Caught unexpected error while processing registry '{registry.path}': {err}")
            raise CantProcessGitlabRegistry

    def _process_project_users(self, project: Project, instance_id: int) -> None:
        """
        Process users associated with a project in a version control system.
    
        It retrieves all members of the project, processes each member's data, and stores it in the provided dictionaries.
        The function also handles exceptions and logs any errors that occur.
    
        @param project: The project object to process users for.
        @param instance_id: The ID of the version control system instance.
    
        @return: None.
        """
        members = project.members_all.list(get_all=True)
        try:
            processed = set()
            access_levels = {gitlab.const.AccessLevel.GUEST: 'guest',
                             gitlab.const.AccessLevel.REPORTER: 'reporter',
                             gitlab.const.AccessLevel.DEVELOPER: 'developer',
                             gitlab.const.AccessLevel.MAINTAINER: 'maintainer',
                             gitlab.const.AccessLevel.OWNER: 'owner'}
            for member in members:
                if member.id in processed:
                    continue
                processed.add(member.id)
                user = {key: getattr(member, attr) for key, attr in
                        [("vcs_id", "id"), ("username", "username"), ("name", "name"), ("state", "state"),
                         ("locked", "locked"), ("web_url", "web_url")]}
                user["vcs_instance_id"] = instance_id

                insert_users({member.id: user})
                access_level = access_levels.get(member.access_level)

                user = {"repo_id": project.id, "user_id": member.id, "access_level": access_level,
                        "vcs_instance_id": instance_id}

                insert_user_key = f"{project.id}{member.id}"
                insert_repository_users({insert_user_key: user})
        except Exception as err:
            logger.error(f"- [T{get_thread_num()}] Caught unexpected error: {err}")
            raise CantProcessProjectUsers

    def _process_project_contributors(self, project: Project, instance_id: int) -> None:
        """
        Process the contributors of a project and insert their information into a dictionary.
    
        @param project: The project object containing the repository contributors.
        @param instance_id: The ID of the VCS instance.
        
        @return: None.
        """
        contributors = project.repository_contributors(get_all=True)
        for contributor in contributors:
            contributor_info = {key: contributor.get(value) for key, value in
                                [("email", "email"), ("commits", "commits"), ("additions", "additions"),
                                 ("deletions", "deletions")]}
            contributor_info["vcs_instance_id"] = instance_id
            contributor_info['repo_id'] = project.id
            contributor_insert_key = f"{project.id}{contributor['email']}"
            insert_contributors({contributor_insert_key: contributor_info})

    def _get_parents(self, project_parents: dict, project: Project, repo_id: int) -> list[Any] | Any:
        """
        Retrieves parent projects for a given repository.
    
        @param project_parents: A dictionary containing parent information for multiple projects.
        @param project: The project object for which parents are being retrieved.
        @param repo_id: The repository ID for which parents are being retrieved.
    
        @return: A list of parent project IDs if the project's path matches the path in project_parents.
                 Otherwise, returns a list of group IDs associated with the project.
        """
        if project_parents.get(repo_id, {}).get('path', '') == project.path_with_namespace:
            return project_parents[repo_id]['parents']
        return [group.id for group in project.groups.list()]

    def _process_project(self, project: Project, project_parents: Optional[dict], instance_id: int) -> None:
        """
        Process a GitLab project and prepare its data for insertion into a database.
    
        @param project: The GitLab project to process.
        @param project_parents: A dictionary of parent projects, if any.
        @param instance_id: The ID of the GitLab instance.
    
        @return: None
        """
        debug_var = {}
        logger.info(f"[T{get_thread_num()}]: Processing project '{project.path}' ({project.id=})")
        try:
            repo_id = project.get_id()
            project_parents = self._get_parents(project_parents, project, repo_id)

            last_commit = project.commits.list(get_all=False, per_page=1, order_by='id', sort='desc')
            last_commit_at = last_commit[0].committed_date if len(last_commit) > 0 else None
            repo = self._create_project_dict(project, project_parents, instance_id, last_commit_at)

            if 'default_branch' in project.attributes:
                repo["default_branch"] = project.default_branch

            debug_var[repo_id] = repo
            insert_repositories({repo_id: repo})
        except Exception as err:
            logger.error(
                f"- [T{get_thread_num()}] Caught unexpected error while inserting repository into database: {err}")

    def _get_registries(self, project: Project) -> Optional[list]:
        """
        Attempts to retrieve a list of registries for the given project.

        @param project: The project for which to retrieve the registries.

        @return Optional[list]: A list of registries if successful, None if a 403 Forbidden error occurs, or None if an unexpected error occurs.
        """
        try:
            registries = project.repositories.list(get_all=True, retry_transient_errors=False)
            return registries
        except Exception as err:
            if str(err) == "403: 403 Forbidden":
                logger.debug(f"- [T{get_thread_num()}] Got 403 while processing '{project.path}'")
                return None
            else:
                logger.error(
                    f"- [T{get_thread_num()}] Caught unexpected error while requesting registries of '{project.path}': {err}")
                return None

    def process_instance(self):
        start_time = datetime.now()

        last_project_id = self._get_last_project_id()
        groups = self.gl.groups.list(get_all=False, per_page=1, order_by='id', sort='desc')
        last_group_id = groups[0].id

        if PROCESS_PROJECTS:
            self._process_projects(self.instance, last_project_id)
        if PROCESS_GROUPS:
            self._process_groups(self.instance, start_time, last_group_id)

        end_time = datetime.now()

        logger.info(
            f"'{self.instance.url}': {PROJECT_WORKERS_COUNT} workers processed {last_project_id} projects and {last_group_id} groups in {end_time - start_time}")
