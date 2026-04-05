import os
from github import Github, Auth, GithubIntegration
from .state import SentinelState

def scout_node(state: SentinelState) -> dict:
    pr_id = state["pr_id"]
    repo_name = state["repo_name"]
    installation_id = state["installation_id"]

    # Initialize GitHub client
    app_id = os.getenv("GITHUB_APP_ID")
    private_key = os.getenv("GITHUB_PRIVATE_KEY")
    
    if not private_key and os.path.exists("private-key.pem"):
        with open("private-key.pem", "r") as f:
            private_key = f.read()

    auth = Auth.AppAuth(app_id=int(app_id), private_key=private_key)
    gi = GithubIntegration(auth=auth)
    installation = gi.get_github_for_installation(installation_id)
    
    repo = installation.get_repo(repo_name)
    pr = repo.get_pull(pr_id)
    
    # Fetch the diff
    diff_content = pr.get_files() # Or get the actual diff text
    # Actually, pr.get_pull(pr_id).diff_url is what we want to fetch as text
    import httpx
    response = httpx.get(pr.diff_url, headers={"Authorization": f"token {gi.get_access_token(installation_id).token}"})
    diff_text = response.text

    return {
        "diff_content": diff_text,
        "jira_context": {"ticket_id": "STNL-123", "description": "Fetched from GitHub Actions context"},
        "comments": state.get("comments", []) + [f"Scout: Fetched actual PR diff ({len(diff_text)} chars)."]
    }
