class NoExistedRegistryTag(Exception):
    """Cannot find any tags in registry"""


class CantProcessGitlabRegistry(Exception):
    """Cannot process specific Gitlab registry"""


class CantProcessProjectUsers(Exception):
    """Cannot process users in specific project"""


class CantInitParserObject(Exception):
    """Cannot init Instance Parser"""

class NoCommandForTool(Exception):
    """Command to run tool does not exist"""
    
class NoParserForTool(Exception):
    """Parser to process tool's result does not exist"""