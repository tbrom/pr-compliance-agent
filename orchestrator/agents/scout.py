import os
from github import Github, Auth, GithubIntegration
from .state import SentinelState

from .state import SentinelState
import httpx

def scout_node(state: SentinelState) -> dict:
    pr_id = state["pr_id"]
    repo_name = state["repo_name"]
    diff_url = state.get("diff_content", "") # This might be the raw URL if passed from main

    logger_info = f"🔍 Scout: Fetching diff for PR #{pr_id} on {repo_name}"
    
    # If main.py already passed the diff_url, we fetch it
    if diff_url.startswith("http"):
        try:
            # Note: We assume the caller or middleware handled the redirection/auth if needed
            # for the diff_url, or we fetch it via the public URL if it's a public repo.
            # In production, we'd use the installation token passed in the state.
            response = httpx.get(diff_url, follow_redirects=True, timeout=10.0)
            diff_text = response.text
        except Exception as e:
            diff_text = f"Error fetching diff: {str(e)}"
    else:
        # Fallback – if the diff_content was already the text
        diff_text = diff_url

    return {
        "diff_content": diff_text,
        "jira_context": {"ticket_id": "STNL-123", "description": "Derived from PR context"},
        "comments": state.get("comments", []) + [f"Scout: Processed PR diff ({len(diff_text)} chars)."]
    }
