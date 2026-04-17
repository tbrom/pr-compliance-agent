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
from history_store import build_store
from mcp_client import SentinelMCPClient, set_client
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

import langchain

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

# Enable global LangChain logging for auditable AI traces
langchain.debug = True
langchain.verbose = True
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

    # Boot long-lived MCP client (spawns Jira + Standards MCP subprocesses)
    mcp_client = SentinelMCPClient()
    try:
        await mcp_client.start()
        set_client(mcp_client)
        app.state.mcp_client = mcp_client
    except Exception as e:
        logger.error("❌ MCP client failed to start: %s", e)
        app.state.mcp_client = None

    # Persistent verdict history (used by the Copilot chat endpoint)
    app.state.history = build_store()

    yield  # application runs

    logger.info("🛑 Sentinel shutting down")
    if getattr(app.state, "mcp_client", None) is not None:
        try:
            await app.state.mcp_client.stop()
        except Exception as e:
            logger.warning("MCP client shutdown error: %s", e)
    history = getattr(app.state, "history", None)
    if history is not None and hasattr(history, "close"):
        try:
            history.close()
        except Exception as e:
            logger.warning("History store shutdown error: %s", e)


app = FastAPI(
    title="Sentinel-SDLC Orchestrator",
    description="Multi-agent compliance engine for pull requests",
    lifespan=lifespan,
)

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

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


_DECISION_EMOJI = {"GO": "✅", "WARN": "⚠️", "NO-GO": "🚫"}


def format_report(state: dict) -> str:
    """Format the final agent state into a Markdown PR comment."""
    decision = state.get("final_decision", "UNKNOWN")
    emoji = _DECISION_EMOJI.get(decision, "❔")

    lines = [f"## {emoji} Sentinel-SDLC Verdict: **{decision}**", ""]

    blocking = state.get("blocking_issues", [])
    if blocking:
        lines.append("### 🚫 Blocking Issues")
        for b in blocking:
            lines.append(f"- {b}")
        lines.append("")

    warnings = state.get("warnings", [])
    if warnings:
        lines.append("### ⚠️ Warnings")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    reasoning = state.get("decision_reasoning", [])
    if reasoning:
        lines.append("### Decision Rationale")
        for r in reasoning:
            lines.append(f"- {r}")
        lines.append("")

    findings = state.get("analyst_findings", [])
    if findings:
        lines.append("### Analyst Findings")
        for f in findings:
            lines.append(f"- {f}")
        lines.append("")

    signals = state.get("validator_signals", [])
    if signals:
        lines.append("### Raw Signals")
        for s in signals:
            lines.append(f"- `{s}`")
        lines.append("")

    lines.append("### Agent Trace")
    for comment in state.get("comments", []):
        lines.append(f"- {comment}")

    lines.append("")
    lines.append("---")
    lines.append("*Powered by Sentinel-SDLC • Multi-Agent Compliance Engine*")

    return "\n".join(lines)


def get_user_role(login: str) -> str:
    """
    Map a GitHub login to a Sentinel Role.
    In production, this would query a DB or an IDP.
    """
    admins = os.getenv("SENTINEL_ADMIN_LOGINS", "").split(",")
    if login in admins:
        return "ADMIN"
    return "DEVELOPER"


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

        requester_login = payload.get("sender", {}).get("login", "unknown")

        pr = payload["pull_request"]
        pr_number = pr["number"]
        repo_full_name = payload["repository"]["full_name"]
        installation_id = payload.get("installation", {}).get("id")
        head_sha = pr["head"]["sha"]
        branch_name = pr["head"]["ref"]
        diff_url = pr.get("diff_url", "")
        logger.info("🔍 Processing PR #%d on %s (branch: %s, head_sha=%s)", pr_number, repo_full_name, branch_name, head_sha)

    # 4. Handle push events (to main/master)
    elif event == "push":
        # Only scan if it's the default branch to avoid noise
        ref = payload.get("ref", "")
        if not ref.endswith("/main"):
             return JSONResponse(status_code=200, content={"status": "ignored", "ref": ref})

        repo_full_name = payload["repository"]["full_name"]
        installation_id = payload.get("installation", {}).get("id")
        head_sha = payload.get("after", "")
        branch_name = ref.split("/")[-1]
        pr_number = 0  # Not a PR, but we'll use 0 as a placeholder
        diff_url = ""  # Will be handled by the scout agent

        logger.info("🔍 Processing Push to %s on %s (head_sha=%s)", ref, repo_full_name, head_sha)

    else:
        return JSONResponse(status_code=200, content={"status": "ignored", "event": event})

    user_role = get_user_role(requester_login)
    logger.info("👤 Requester: %s (Role: %s)", requester_login, user_role)

    # 4. Create an initial in-progress Check Run and mint an installation token
    #    so agents (Scout) can authenticate diff fetches for private repos.
    integration = request.app.state.github_integration
    check_run_id = None
    installation_token = ""
    if integration and installation_id:
        try:
            gh = get_github_client(integration, installation_id)
            repo = gh.get_repo(repo_full_name)
            check_run = repo.create_check_run(
                name="Sentinel Compliance Check",
                head_sha=head_sha,
                status="in_progress",
            )
            check_run_id = check_run.id
            logger.info("✅ Created Check Run ID: %s", check_run_id)
        except Exception as e:
            logger.error("❌ Failed to create Check Run: %s", str(e))

        try:
            installation_token = integration.get_access_token(installation_id).token
        except Exception as e:
            logger.warning("⚠️  Could not mint installation access token: %s", e)

    # 5. Run the multi-agent LangGraph pipeline
    initial_state = {
        "pr_id": pr_number,
        "repo_name": repo_full_name,
        "branch_name": branch_name,
        "jira_id": "",
        "installation_id": installation_id,
        "github_token": installation_token,
        "diff_content": diff_url,
        "jira_context": None,
        "analyst_findings": [],
        "validator_signals": [],
        "final_decision": "",
        "decision_reasoning": [],
        "blocking_issues": [],
        "warnings": [],
        "requester_login": requester_login,
        "user_role": user_role,
        "comments": [],
        "error": "",
    }

    try:
        final_state = await request.app.state.sentinel_graph.ainvoke(initial_state)
        logger.info("✅ Graph completed for PR #%d – decision: %s",
                    pr_number, final_state.get("final_decision"))
    except Exception as e:
        logger.error("❌ Graph execution failed for PR #%d: %s", pr_number, str(e))
        if check_run_id:
            try:
                repo.get_check_run(check_run_id).edit(
                    status="completed",
                    conclusion="failure",
                    output={"title": "Sentinel Error", "summary": f"Graph execution failed: {str(e)}"}
                )
            except: pass
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})

    # 6. Post the result back to the PR as a comment and update Check Run
    if integration and installation_id:
        try:
            gh = get_github_client(integration, installation_id)
            comment_body = format_report(final_state)
            post_pr_comment(gh, repo_full_name, pr_number, comment_body)

            if check_run_id:
                decision = final_state.get("final_decision", "UNKNOWN")
                conclusion = {
                    "GO": "success",
                    "WARN": "neutral",
                    "NO-GO": "failure",
                }.get(decision, "failure")

                # Construct detailed output summary
                summary_lines = [f"### Verdict: **{decision}**", ""]
                for item in final_state.get("blocking_issues", []):
                    summary_lines.append(f"- 🚫 {item}")
                for item in final_state.get("warnings", []):
                    summary_lines.append(f"- ⚠️ {item}")
                for item in final_state.get("decision_reasoning", []):
                    summary_lines.append(f"- {item}")

                repo.get_check_run(check_run_id).edit(
                    status="completed",
                    conclusion=conclusion,
                    output={
                        "title": f"Sentinel SDLC: {decision}",
                        "summary": "\n".join(summary_lines),
                        "text": "Detailed traces are available in the Cloud Run logs."
                    }
                )
                logger.info("✅ Updated Check Run ID: %s with conclusion: %s", check_run_id, conclusion)

            # Persist verdict for the Copilot chat endpoint to recall later.
            try:
                request.app.state.history.put(
                    repo_full_name,
                    pr_number,
                    {
                        "decision": final_state.get("final_decision", "UNKNOWN"),
                        "findings": final_state.get("analyst_findings", []),
                        "signals": final_state.get("validator_signals", []),
                        "blocking_issues": final_state.get("blocking_issues", []),
                        "warnings": final_state.get("warnings", []),
                        "decision_reasoning": final_state.get("decision_reasoning", []),
                        "requester_login": final_state.get("requester_login"),
                        "jira_id": final_state.get("jira_id"),
                    },
                )
            except Exception as e:
                logger.error("❌ Failed to persist verdict for %s#%d: %s", repo_full_name, pr_number, e)

        except Exception as e:
            logger.error("❌ Failed to post result back to GitHub: %s", str(e), exc_info=True)

    return JSONResponse(status_code=200, content={
        "status": "completed",
        "decision": final_state.get("final_decision"),
    })


# ---------------------------------------------------------------------------
# GitHub Copilot Extension Endpoint
# ---------------------------------------------------------------------------
from agents.copilot_agent import handle_copilot_chat

@app.post("/api/copilot")
async def copilot_chat(request: Request):
    """
    Endpoint for GitHub Copilot Chat Extension.
    """
    # 1. Signature Verification (Simplified for Demo)
    # real production would use gcloud / k8s secrets to store GH Public Key
    signature = request.headers.get("x-github-public-key-signature")
    if not signature:
         logger.warning("⚠️ Received Copilot request without signature (ignoring for demo).")

    try:
        payload = await request.json()
        messages = payload.get("messages", [])
        last_message = messages[-1]["content"] if messages else "Hello"

        # Identity
        requester_login = payload.get("sender", {}).get("login", "unknown")
        user_role = get_user_role(requester_login)
        logger.info("👤 Copilot Requester: %s (Role: %s)", requester_login, user_role)

        # Resolve PR context: prefer an explicit PR reference in the Copilot
        # payload, fall back to the latest verdict for the repo in scope.
        repo_name, pr_number = _extract_pr_reference(payload, messages)
        history = request.app.state.history

        pr_context = None
        if repo_name and pr_number is not None:
            pr_context = history.get(repo_name, pr_number)
        if pr_context is None and repo_name:
            pr_context = history.get_latest(repo_name)
        if pr_context is None:
            pr_context = {"decision": "No recent scan found."}

        response_text = handle_copilot_chat(last_message, pr_context)

        return JSONResponse(status_code=200, content={
            "content": response_text,
            "role": "assistant"
        })
    except Exception as e:
        logger.error("❌ Copilot Chat Error: %s", str(e), exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


def _extract_pr_reference(payload: dict, messages: list) -> tuple[str | None, int | None]:
    """Best-effort extraction of (repo_full_name, pr_number) from a Copilot payload.

    GitHub Copilot Extensions attach attachments as `copilot_references` on the
    most recent message. A pull-request reference has:
        { "type": "github.pull-request",
          "data": { "number": <int>, "repository": { "full_name": "owner/repo" } } }

    If no explicit reference is present we fall back to the top-level
    `repository.full_name` field (if any), leaving pr_number as None so the
    caller can resolve the latest verdict for the repo.
    """
    repo_name: str | None = None
    pr_number: int | None = None

    if messages:
        for ref in messages[-1].get("copilot_references", []) or []:
            if ref.get("type") in ("github.pull-request", "github.pull_request"):
                data = ref.get("data") or {}
                num = data.get("number")
                repo = (data.get("repository") or {}).get("full_name")
                if num is not None and repo:
                    return repo, int(num)

    repo_name = payload.get("repository", {}).get("full_name") or None
    return repo_name, pr_number


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
