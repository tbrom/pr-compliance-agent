import logging
import httpx

from .state import SentinelState

logger = logging.getLogger("sentinel")


async def scout_node(state: SentinelState) -> dict:
    pr_id = state.get("pr_id")
    repo_name = state.get("repo_name")
    diff_ref = state.get("diff_content", "")
    github_token = state.get("github_token", "")

    logger.info("🔍 Scout: Fetching diff for PR #%s on %s", pr_id, repo_name)

    if diff_ref.startswith("http"):
        headers = {
            "Accept": "application/vnd.github.v3.diff",
            "User-Agent": "sentinel-sdlc",
        }
        # Authenticated fetch works for private repos; public repos also accept the token.
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        try:
            response = httpx.get(diff_ref, headers=headers, follow_redirects=True, timeout=10.0)
            response.raise_for_status()
            diff_text = response.text
        except httpx.HTTPStatusError as e:
            logger.error("❌ Scout: diff fetch returned %s for %s", e.response.status_code, diff_ref)
            diff_text = f"Error fetching diff: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error("❌ Scout: diff fetch failed: %s", e)
            diff_text = f"Error fetching diff: {str(e)}"
    else:
        # Fallback — diff_content was already the text (push events, tests, etc.)
        diff_text = diff_ref

    return {
        "diff_content": diff_text,
        "comments": state.get("comments", []) + [
            f"Scout: Processed PR diff ({len(diff_text)} chars)."
        ],
    }
