import os
import re
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from .state import SentinelState
from mcp_client import get_client

logger = logging.getLogger("sentinel")

_FALLBACK_JIRA_CONTEXT = (
    "No Jira context could be retrieved for {jira_id}. "
    "Proceed with enterprise Data Fabric defaults: authenticated internal endpoints, "
    "tokenized PII, no hardcoded secrets."
)


async def analyst_node(state: SentinelState) -> dict:
    branch_name = state.get("branch_name", "")
    diff_content = state.get("diff_content", "")
    comments = state.get("comments", [])
    findings = state.get("analyst_findings", [])

    # 1. Extract Jira ID from branch name: ticketType/PROJECT-NUMBER (e.g. feat/STNL-123)
    jira_id = "UNKNOWN"
    match = re.search(r"([a-z]+)/([A-Z]+-[0-9]+)", branch_name)
    if match:
        jira_id = match.group(2)
        logger.info("🔍 Analyst: Identified Jira ID %s from branch %s", jira_id, branch_name)

    # 2. Retrieve Jira requirements via the Jira MCP server (real RAV call)
    mcp = get_client()
    jira_requirements: str | None = None
    if mcp is not None and jira_id != "UNKNOWN":
        jira_requirements = await mcp.get_jira_issue(jira_id)

    if jira_requirements:
        comments.append(f"Analyst: Retrieved Jira context for {jira_id} via MCP.")
    else:
        jira_requirements = _FALLBACK_JIRA_CONTEXT.format(jira_id=jira_id)
        comments.append(f"Analyst: Jira MCP unavailable for {jira_id} — using fallback context.")

    # 3. Perform AI reasoning
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("❌ Analyst: GOOGLE_API_KEY not found in environment")
        return {
            "error": "GOOGLE_API_KEY not found",
            "comments": comments + ["Analyst: Failed due to missing AI credentials."],
            "jira_id": jira_id,
            "jira_context": jira_requirements,
        }

    llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key)

    signals = state.get("validator_signals", [])

    prompt = f"""
    You are a Strategic Security Analyst. Verify that the code changes in this PR align with the Jira requirements and enterprise Data Fabric standards.

    Jira Ticket: {jira_id}
    Requirements Context (retrieved from Jira MCP):
    {jira_requirements}

    PR Diff:
    {diff_content[:5000]}

    Analyze the diff against the requirements:
    1. Does the code satisfy the semantic intent of the ticket?
    2. Are there any 'rogue' changes that aren't mentioned in the ticket?
    3. Does the code structure meet basic Data Fabric semantic definitions?

    Respond in EXACTLY this format (two lines):
    VERDICT: <ALIGNED|MISALIGNED|INCONCLUSIVE>
    REASON: <one-sentence explanation>
    """

    try:
        response = await llm.ainvoke(prompt)
        analyst_response = (response.content or "").strip() if isinstance(response.content, str) else str(response.content)
        findings.append(f"Alignment Analysis for {jira_id}: {analyst_response}")

        verdict = _parse_verdict(analyst_response)
        if verdict == "ALIGNED":
            signals.append("ANALYST_ALIGNMENT_OK")
        elif verdict == "MISALIGNED":
            signals.append("ANALYST_MISALIGNMENT")
        else:
            signals.append("ANALYST_ALIGNMENT_INCONCLUSIVE")

        comments.append(
            f"Analyst: Alignment {verdict} for {state.get('requester_login')} "
            f"(Role: {state.get('user_role')})."
        )
    except Exception as e:
        logger.error("❌ Analyst: Reasoning failed for %s: %s", jira_id, str(e))
        signals.append("ANALYST_ALIGNMENT_INCONCLUSIVE")
        comments.append(f"Analyst: Failed to perform semantic reasoning for {jira_id} ({str(e)}).")

    return {
        "jira_id": jira_id,
        "jira_context": jira_requirements,
        "analyst_findings": findings,
        "validator_signals": signals,
        "comments": comments,
    }


def _parse_verdict(text: str) -> str:
    """Extract ALIGNED/MISALIGNED/INCONCLUSIVE from the analyst LLM response.

    Order matters: MISALIGNED contains ALIGNED as a substring, so always test
    for MISALIGNED first.
    """
    upper = text.upper()
    for line in upper.splitlines():
        if line.strip().startswith("VERDICT:"):
            payload = line.split(":", 1)[1]
            if "MISALIGNED" in payload:
                return "MISALIGNED"
            if "INCONCLUSIVE" in payload:
                return "INCONCLUSIVE"
            if "ALIGNED" in payload:
                return "ALIGNED"
    if "MISALIGNED" in upper:
        return "MISALIGNED"
    if "INCONCLUSIVE" in upper:
        return "INCONCLUSIVE"
    if "ALIGNED" in upper:
        return "ALIGNED"
    return "INCONCLUSIVE"
