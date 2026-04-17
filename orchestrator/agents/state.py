from typing import TypedDict, List, Any

class SentinelState(TypedDict):
    pr_id: int
    repo_name: str
    branch_name: str
    jira_id: str
    installation_id: int
    github_token: str
    diff_content: str
    jira_context: Any
    analyst_findings: List[str]
    validator_signals: List[str]
    final_decision: str  # GO | NO-GO | WARN
    decision_reasoning: List[str]
    blocking_issues: List[str]
    warnings: List[str]
    requester_login: str
    user_role: str
    comments: List[str]
    error: str
