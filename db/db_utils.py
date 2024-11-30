from sys import exit
from typing import Any

import peewee
from gitlab.v4.objects import ProjectRegistryRepository

from db.models import VCSInstance, Repository, Group, Registry, Image, User, Contributor, RepositoryUser, Repository, database_proxy
from db.models import Finding, ScanRepo
from settings.config import *
from settings.logger import logger

if DEBUG_ENABLED:
    logger.info(f"DEBUG_ENABLED specified, using sqlite3.db...")
    database = peewee.SqliteDatabase("sqlite3.db")
else:
    logger.info(
        f"Connecting to database: '{POSTGRES_USER}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?currentSchema={POSTGRES_SCHEMA}'...")
    database = peewee.PostgresqlDatabase(POSTGRES_DB,
                                         user=POSTGRES_USER,
                                         password=POSTGRES_PASSWORD,
                                         host=POSTGRES_HOST,
                                         port=POSTGRES_PORT, autoconnect=False)


def init_db(db: peewee.Database, models: Any) -> None:
    database_proxy.initialize(db)
    try:
        db.connect()
        db.create_tables(models)
    except Exception as err:
        logger.fatal(str(err))
        exit(-1)


def initialize_database(models: list, vcs_instances=None) -> None:
    logger.info("Database initializing...")
    init_db(database, models)
    if vcs_instances:
        for key in vcs_instances:
            instance = vcs_instances[key]
            with database.atomic():
                instance_obj, created = VCSInstance.get_or_create(url=instance['URL'], type=instance['TYPE'], mnemonic=key)
                if created:
                    logger.info(f"Instance '{instance_obj.url}' added into database...")
    logger.info("Database initialized!")


def insert_data_to_db(model, data, conflict_target, update) -> None:
    if data:
        logger.debug(f"Inserting {model.__name__} ({len(data)})")
        try:
            with database:
                for chunk in peewee.chunked(data.values(), INSERT_CHUNK_SIZE):
                    model.insert_many(chunk).on_conflict(conflict_target=conflict_target, update=update).execute()
        except Exception as e:
            logger.error(f"Error on inserting {model.__name__}: {e}")


def fetch_vcs_instances() -> list[VCSInstance]:
    with database:
        return list(VCSInstance.select())


def fetch_tags(registry: ProjectRegistryRepository, instance_id: int) -> set:
    with database:
        tags_in_db = {
            image.path
            for image in Image.select(Image.path).where(
                Image.vcs_instance_id == instance_id,
                Image.repo_id == registry.project_id,
                Image.registry_id == registry.get_id()
            )
        }

    return tags_in_db


def fetch_last_inventoried_group(instance_id: int):
    with database:
        last_inventoried_group = Group.select(Group.vcs_id).where(Group.vcs_instance_id == instance_id).order_by(
            -Group.vcs_id).limit(1).get_or_none()

    return last_inventoried_group


def fetch_last_inventoried_project(instance_id: int):
    with database:
        last_inventoried_project = Repository.select(Repository.vcs_id).where(
            Repository.vcs_instance_id == instance_id).order_by(
            -Repository.vcs_id).limit(1).get_or_none()

    return last_inventoried_project


def get_scanned_repo_id(instance_id: int) -> list:
    checked_ids = []
    logger.info(f"Getting list of previously checked repositories...")
    with database:
        for row in Repository.select(Repository.vcs_id).where(
                Repository.vcs_instance_id == instance_id).order_by(-Repository.id):
            checked_ids.append(row.vcs_id)

    return checked_ids


def get_inventoried_projects_with_parents(instance_id: int) -> tuple[list, dict]:
    inventoried_projects_in_db = list()
    projects_parents = {}
    with database:
        for repo in Repository.select(Repository.vcs_id, Repository.path, Repository.parents).where(
                Repository.vcs_instance_id == instance_id).order_by(-Repository.vcs_id):
            projects_parents[repo.vcs_id] = {'path': repo.path, 'parents': repo.parents}
            inventoried_projects_in_db.append(repo.vcs_id)

    return inventoried_projects_in_db, projects_parents


def insert_users(users_to_insert: dict) -> None:
    insert_data_to_db(
        User, users_to_insert,
        [User.vcs_instance_id, User.username],
        {User.locked: peewee.EXCLUDED.locked, User.state: peewee.EXCLUDED.state}
    )


def insert_repositories(repos_to_insert: dict) -> None:
    insert_data_to_db(
        Repository, repos_to_insert,
        [Repository.vcs_instance_id, Repository.vcs_id],
        {
            Repository.web_url: peewee.EXCLUDED.web_url,
            Repository.git_url: peewee.EXCLUDED.git_url,
            Repository.visibility: peewee.EXCLUDED.visibility,
            Repository.forks_count: peewee.EXCLUDED.forks_count,
            Repository.last_activity_repo: peewee.EXCLUDED.last_activity_repo,
            Repository.last_commit_at: peewee.EXCLUDED.last_commit_at,
            Repository.last_time_checked: peewee.EXCLUDED.last_time_checked,
            Repository.path: peewee.EXCLUDED.path,
            Repository.group_id: peewee.EXCLUDED.group_id,
            Repository.parents: peewee.EXCLUDED.parents,
            Repository.is_archived: peewee.EXCLUDED.is_archived
        }
    )


def insert_registries(registries_to_insert: dict) -> None:
    insert_data_to_db(
        Registry, registries_to_insert,
        [Registry.vcs_instance_id, Registry.vcs_id, Registry.repo_id],
        {
            Registry.path: peewee.EXCLUDED.path,
            Registry.name: peewee.EXCLUDED.name,
            Registry.last_time_checked: peewee.EXCLUDED.last_time_checked
        }
    )


def insert_images(images_to_insert: dict) -> None:
    insert_data_to_db(
        Image, images_to_insert,
        [Image.vcs_instance_id, Image.image, Image.repo_id, Image.registry_id],
        {
            Image.tag: peewee.EXCLUDED.tag,
            Image.path: peewee.EXCLUDED.path,
            Image.image: peewee.EXCLUDED.image,
            Image.created_at: peewee.EXCLUDED.created_at,
            Image.digest: peewee.EXCLUDED.digest,
            Image.revision: peewee.EXCLUDED.revision,
            Image.total_size: peewee.EXCLUDED.total_size,
            Image.last_time_checked: peewee.EXCLUDED.last_time_checked
        }
    )


def insert_repository_users(repository_users_to_insert: dict) -> None:
    insert_data_to_db(
        RepositoryUser, repository_users_to_insert,
        [RepositoryUser.vcs_instance_id, RepositoryUser.repo_id, RepositoryUser.user_id, RepositoryUser.access_level],
        {RepositoryUser.access_level: peewee.EXCLUDED.access_level}
    )


def insert_contributors(contributors_to_insert: dict) -> None:
    insert_data_to_db(
        Contributor, contributors_to_insert,
        [Contributor.vcs_instance_id, Contributor.repo_id, Contributor.email],
        {
            Contributor.commits: peewee.EXCLUDED.commits,
            Contributor.additions: peewee.EXCLUDED.additions,
            Contributor.deletions: peewee.EXCLUDED.deletions
        }
    )


def insert_groups(groups_to_insert: dict) -> None:
    insert_data_to_db(
        Group, groups_to_insert,
        [Group.vcs_instance_id, Group.vcs_id],
        {
            Group.path: peewee.EXCLUDED.path,
            Group.parent_id: peewee.EXCLUDED.parent_id,
            Group.visibility: peewee.EXCLUDED.visibility
        }
    )


def insert_findings(findings_to_insert: dict) -> None:
    insert_data_to_db(
        Finding, findings_to_insert,
        [Finding.vcs_instance_id, Finding.repo_id, Finding.fingerprint],
        {
            Finding.author: peewee.EXCLUDED.author,
            Finding.commit: peewee.EXCLUDED.commit,
            Finding.commit_date: peewee.EXCLUDED.commit_date,
            Finding.email: peewee.EXCLUDED.email,
            Finding.found_date: peewee.EXCLUDED.found_date
        }
    )


def filter_repos(filter: str) -> list[ScanRepo]:
    with database:
        if filter == "force":
            selection = Repository.select(Repository.vcs_id, Repository.web_url, Repository.git_url, Repository.vcs_instance_id)
        else:
            selection = Repository.select(Repository.vcs_id, Repository.web_url, Repository.git_url, Repository.vcs_instance_id).where(
                                         (Repository.last_time_scanned.is_null()) |
                                         (Repository.last_activity_repo > Repository.last_time_scanned))
        return [ScanRepo(vcs_id=repo.vcs_id,
                         git_url=repo.git_url,
                         vcs=repo.vcs_instance_id) for repo in selection]
