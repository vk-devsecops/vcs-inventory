import peewee

from dataclasses import dataclass
from playhouse.postgres_ext import ArrayField
from playhouse.shortcuts import ThreadSafeDatabaseMetadata

from settings.config import DEBUG_ENABLED, POSTGRES_SCHEMA


database_proxy = peewee.Proxy()


class BaseModel(peewee.Model):
    class Meta:
        model_metadata_class = ThreadSafeDatabaseMetadata
        database = database_proxy
        if not DEBUG_ENABLED:
            schema = POSTGRES_SCHEMA


class VCSInstance(BaseModel):
    id = peewee.PrimaryKeyField()
    url = peewee.TextField(default='')
    type = peewee.TextField(default='')
    mnemonic = peewee.TextField(default='')

    class Meta:
        indexes = ((('url',), True),)
        db_table = 'vcs_instances'


class Repository(BaseModel):
    id = peewee.PrimaryKeyField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='repositories', on_delete='CASCADE')
    vcs_id = peewee.BitField()
    path = peewee.TextField()
    group_id = peewee.BitField()
    if not DEBUG_ENABLED:
        parents = ArrayField(peewee.BitField, null=True)
    else:
        parents = peewee.TextField(null=True)
    web_url = peewee.TextField()
    git_url = peewee.TextField()
    forks_count = peewee.IntegerField(default=0)
    created = peewee.DateTimeField(null=True)
    default_branch = peewee.TextField(null=True)
    last_time_checked = peewee.DateTimeField()
    is_scanned = peewee.BooleanField(default=False)
    last_time_scanned = peewee.DateTimeField(null=True)
    visibility = peewee.TextField(default='')
    last_activity_repo = peewee.DateTimeField()
    last_commit_at = peewee.DateTimeField(null=True)
    is_archived = peewee.BooleanField(default=False)

    class Meta:
        indexes = ((('vcs_instance_id', 'vcs_id'), True),)


class Group(BaseModel):
    id = peewee.PrimaryKeyField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='groups', on_delete='CASCADE')
    vcs_id = peewee.BitField()
    parent_id = peewee.BitField(null=True)
    path = peewee.TextField(default='')
    visibility = peewee.TextField(default='')

    class Meta:
        indexes = ((('vcs_instance_id', 'vcs_id'), True),)


class Registry(BaseModel):
    id = peewee.PrimaryKeyField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='registries', on_delete='CASCADE')
    vcs_id = peewee.TextField()
    repo_id = peewee.BitField()
    path = peewee.TextField()
    name = peewee.TextField()
    web_url = peewee.TextField()
    created_at = peewee.DateTimeField()
    last_time_checked = peewee.DateTimeField()
    is_scanned = peewee.BooleanField(default=False)
    last_time_scanned = peewee.DateTimeField(null=True)

    class Meta:
        indexes = ((('vcs_instance_id', 'vcs_id', 'repo_id'), True),)


class Image(BaseModel):
    id = peewee.PrimaryKeyField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='images', on_delete='CASCADE')
    repo_id = peewee.BitField()
    registry_id = peewee.BitField()
    path = peewee.TextField()
    tag = peewee.TextField()
    image = peewee.TextField()
    created_at = peewee.DateTimeField(null=True)
    digest = peewee.TextField()
    revision = peewee.TextField()
    total_size = peewee.BitField()
    last_time_checked = peewee.DateTimeField(null=True)
    is_scanned = peewee.BooleanField(default=False)
    last_time_scanned = peewee.DateTimeField(null=True)
    last_scan_id = peewee.UUIDField(null=True)

    class Meta:
        indexes = ((('vcs_instance_id', 'image', 'repo_id', 'registry_id'), True),)


class User(BaseModel):
    id = peewee.PrimaryKeyField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='users', on_delete='CASCADE')
    vcs_id = peewee.BitField(unique=True)
    username = peewee.TextField()
    name = peewee.TextField()
    state = peewee.TextField()
    locked = peewee.BooleanField()
    web_url = peewee.TextField()

    class Meta:
        indexes = ((('vcs_instance_id', 'username'), True),)
        db_table = 'users'


class Contributor(BaseModel):
    id = peewee.PrimaryKeyField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='contributors', on_delete='CASCADE')
    repo_id = peewee.BitField()
    email = peewee.TextField()
    commits = peewee.BitField()
    additions = peewee.BitField()
    deletions = peewee.BitField()

    class Meta:
        indexes = ((('vcs_instance_id', 'repo_id', 'email'), True),)
        db_table = 'contributors'


class RepositoryUser(BaseModel):
    id = peewee.PrimaryKeyField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='repository_users', on_delete='CASCADE')
    repo_id = peewee.BitField()
    user_id = peewee.BitField()
    access_level = peewee.TextField()

    class Meta:
        indexes = ((('vcs_instance_id', 'repo_id', 'user_id', 'access_level'), True),)
        db_table = 'repository_users'


class Finding(BaseModel):
    id = peewee.PrimaryKeyField()
    repo_id = peewee.BitField()
    vcs_instance_id = peewee.ForeignKeyField(VCSInstance, backref='findings', on_delete='CASCADE')
    tool = peewee.TextField()
    title = peewee.TextField()
    fingerprint = peewee.TextField()
    cwe = peewee.IntegerField(null=True)
    severity = peewee.TextField()
    author = peewee.TextField(null=True)
    email = peewee.TextField(null=True)
    file_path = peewee.TextField()
    line = peewee.IntegerField()
    commit = peewee.TextField(null=True)
    commit_date = peewee.DateTimeField(null=True)
    commit_message = peewee.TextField(null=True)
    found_date = peewee.DateTimeField()
    rule_id = peewee.TextField()
    entropy = peewee.FloatField(null=True)
    secret = peewee.TextField(null=True)

    class Meta:
        indexes = ((('vcs_instance_id', 'repo_id', 'fingerprint'), True),)
        db_table = 'findings'


@dataclass
class ScanRepo:
    vcs_id: int
    git_url: str
    vcs: str


@dataclass
class VSC:
    type: str
    url: str
    username: str
    token: str


@dataclass
class CompletedProcess:
    stdout: str
    stderr: str
    returncode: int
