import os
import hmac
import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from github import GithubIntegration, Github, Auth

from graph import build_sentinel_graph
from telemetry import setup_telemetry

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "private-key.pem")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
EVALUATOR_URL = os.getenv("EVALUATOR_URL")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

# ---------------------------------------------------------------------------
# App lifecycle – build the graph once at startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Compile the LangGraph state machine once
    app.state.sentinel_graph = build_sentinel_graph()
    logger.info("✅ Sentinel LangGraph compiled successfully")

    # Initialise the GitHub App integration for authenticating as the app
    app.state.github_integration = None
    private_key = None

    if GITHUB_PRIVATE_KEY:
        private_key = GITHUB_PRIVATE_KEY
        logger.info("✅ GitHub Private Key loaded from environment variable")
    elif os.path.exists(GITHUB_PRIVATE_KEY_PATH):
        with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
            private_key = f.read()
        logger.info("✅ GitHub Private Key loaded from file: %s", GITHUB_PRIVATE_KEY_PATH)

    if private_key:
        auth = Auth.AppAuth(app_id=int(GITHUB_APP_ID), private_key=private_key)
        app.state.github_integration = GithubIntegration(auth=auth)
        logger.info("✅ GitHub App integration initialised (App ID: %s)", GITHUB_APP_ID)
    else:
        logger.warning("⚠️  Private key not found – PR commenting disabled")

    setup_telemetry()
    logger.info("✅ OpenTelemetry tracing initialised")

    yield  # application runs

    logger.info("🛑 Sentinel shutting down")


app = FastAPI(
    title="Sentinel-SDLC Orchestrator",
    description="Multi-agent compliance engine for pull requests",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def verify_webhook_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("No webhook secret configured – skipping verification")
        return True
    if not signature_header:
        return False

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def get_github_client(integration: GithubIntegration, installation_id: int) -> Github:
    """Return an authenticated PyGithub client scoped to an installation."""
    # Authenticate specifically for this installation
    return integration.get_github_for_installation(installation_id)


def post_pr_comment(gh: Github, repo_full_name: str, pr_number: int, body: str):
    """Post a review comment on the pull request."""
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    pr.create_issue_comment(body)
    logger.info("💬 Posted comment on %s#%d", repo_full_name, pr_number)


def format_report(state: dict) -> str:
    """Format the final agent state into a Markdown PR comment."""
    decision = state.get("final_decision", "UNKNOWN")
    emoji = "✅" if decision == "GO" else "🚫"

    lines = [
        f"## {emoji} Sentinel-SDLC Verdict: **{decision}**",
        "",
        "### Agent Trace",
    ]

    for comment in state.get("comments", []):
        lines.append(f"- {comment}")

    findings = state.get("analyst_findings", [])
    if findings:
        lines.append("")
        lines.append("### Analyst Findings")
        for f in findings:
            lines.append(f"- {f}")

    signals = state.get("validator_signals", [])
    if signals:
        lines.append("")
        lines.append("### Validator Signals")
        for s in signals:
            lines.append(f"- `{s}`")

    lines.append("")
    lines.append("---")
    lines.append("*Powered by Sentinel-SDLC • Multi-Agent Compliance Engine*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health(request: Request):
    return {"status": "healthy", "graph_ready": hasattr(request.app.state, "sentinel_graph")}


@app.post("/api/github/webhooks")
async def github_webhook(request: Request):
    payload_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    # 1. Verify the webhook signature
    if not verify_webhook_signature(payload_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()

    # 2. Handle ping (GitHub sends this on app install)
    if event == "ping":
        logger.info("🏓 Ping received from GitHub")
        return JSONResponse(status_code=200, content={"status": "pong"})

    # 3. Handle pull_request events
    if event == "pull_request":
        action = payload.get("action")
        if action not in ("opened", "synchronize", "reopened"):
            return JSONResponse(status_code=200, content={"status": "ignored", "action": action})

        pr = payload["pull_request"]
        pr_number = pr["number"]
        repo_full_name = payload["repository"]["full_name"]
        installation_id = payload.get("installation", {}).get("id")
        diff_url = pr.get("diff_url", "")

        logger.info("🔍 Processing PR #%d on %s (action=%s)", pr_number, repo_full_name, action)

        # 4. Run the multi-agent LangGraph pipeline
        initial_state = {
            "pr_id": pr_number,
            "repo_name": repo_full_name,
            "installation_id": installation_id,
            "diff_content": diff_url,
            "jira_context": None,
            "analyst_findings": [],
            "validator_signals": [],
            "final_decision": "",
            "comments": [],
            "error": "",
        }

        try:
            final_state = request.app.state.sentinel_graph.invoke(initial_state)
            logger.info("✅ Graph completed for PR #%d – decision: %s",
                        pr_number, final_state.get("final_decision"))
        except Exception as e:
            logger.error("❌ Graph execution failed for PR #%d: %s", pr_number, str(e))
            return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})

        # 5. Post the result back to the PR as a comment
        integration = request.app.state.github_integration
        logger.info("📝 Comment path: integration=%s, installation_id=%s", 
                    integration is not None, installation_id)
        
        if integration and installation_id:
            try:
                gh = get_github_client(integration, installation_id)
                comment_body = format_report(final_state)
                post_pr_comment(gh, repo_full_name, pr_number, comment_body)
            except Exception as e:
                logger.error("❌ Failed to post PR comment: %s", str(e), exc_info=True)

        return JSONResponse(status_code=200, content={
            "status": "completed",
            "decision": final_state.get("final_decision"),
        })

    return JSONResponse(status_code=200, content={"status": "ignored", "event": event})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
