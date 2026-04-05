from .state import SentinelState

def scout_node(state: SentinelState) -> dict:
    return {
        "jira_context": {"ticket_id": "STNL-123", "description": "Mock PR for Sentinel compliance"},
        "comments": state.get("comments", []) + ["Scout: Fetched PR diff and Jira context."]
    }
