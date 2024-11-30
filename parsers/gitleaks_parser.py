import json
from datetime import datetime
from pathlib import Path

from db.models import ScanRepo


class GitleaksParser:
    def __init__(self, repo: ScanRepo):
        self.repo = repo

    def get_findings(self, report: str) -> list[dict]:
        """Converts a Gitleaks report to a dict of findings"""
        findings = json.load(report)
        # empty report are just null object
        if not findings:
            return []
        result_dict = {}
        report_dir = str(Path(report.name).parent)
        for finding in findings:
            rule_id = finding.get("RuleID")
            file_path = finding.get("File").replace(report_dir, '')
            line = finding.get("StartLine")
            if line:
                line = int(line)
            else:
                line = 0
            fingerprint = finding.get("Fingerprint")
            if not fingerprint:
                fingerprint=f"{file_path}:{rule_id}:{line}"
            finding_dict = {
                    "repo_id": self.repo.vcs_id,
                    "vcs_instance_id": self.repo.vcs.id,
                    "tool": "gitleaks",
                    "title": finding.get("Description"),
                    "fingerprint": f"{rule_id}:{file_path}:{line}",
                    "cwe": 798,
                    "severity": "High",
                    "author": finding.get('Author'),
                    "email": finding.get('Email'),
                    "file_path": file_path,
                    "line": line,
                    "commit": finding.get("Commit"),
                    "commit_date": finding.get("Date"),
                    "commit_message": finding.get("Message"),
                    "found_date": datetime.now(),
                    "rule_id": finding.get("RuleID"),
                    "entropy": finding.get("Entropy"),
                    "secret": finding.get("Secret")
            }
            result_dict[fingerprint] = finding_dict
        return result_dict
