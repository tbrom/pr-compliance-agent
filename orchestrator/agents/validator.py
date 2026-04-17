import os
import logging
import httpx
import google.auth.transport.requests
import google.oauth2.id_token
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from .state import SentinelState
from mcp_client import get_client

logger = logging.getLogger("sentinel")

_FALLBACK_STANDARDS = (
    "SEC-001 (PII): Raw SSNs and account numbers must be tokenized.\n"
    "SEC-002 (Secrets): Hardcoded AWS_KEY, CLIENT_SECRET, etc. are prohibited. Use Secret Manager.\n"
    "SEC-003 (Containers): Use hardened base images in Dockerfiles.\n"
    "SEC-004 (Networking): Use mTLS and https:// for internal communication."
)


async def validator_node(state: SentinelState) -> dict:
    diff = state.get("diff_content", "")
    evaluator_url = os.getenv("EVALUATOR_URL")
    api_key = os.getenv("GOOGLE_API_KEY")

    signals = state.get("validator_signals", [])
    comments = state.get("comments", [])

    # 1. Call Java Evaluator (Deterministic Shield)
    if evaluator_url:
        try:
            request = google.auth.transport.requests.Request()
            target_audience = evaluator_url.split("/api")[0]
            token = google.oauth2.id_token.fetch_id_token(request, target_audience)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{evaluator_url.rstrip('/')}/api/scan",
                    json={"code": diff},
                    headers=headers,
                )
                result = response.json()
                if result.get("has_secrets"):
                    signals.append("SECRET_DETECTED (Deterministic)")
                if result.get("has_pii"):
                    signals.append("PII_DETECTED (Deterministic)")
        except Exception as e:
            comments.append(f"Validator: Deterministic scan skipped/failed: {str(e)}")

    # 2. Knowledge Retrieval Phase (RAV) — pull relevant standards from the Standards MCP
    mcp = get_client()
    standards_context: str | None = None
    if mcp is not None:
        standards_context = await mcp.search_compliance_standards(diff)

    if standards_context:
        comments.append("Validator: Retrieved applicable standards via Standards MCP.")
    else:
        standards_context = _FALLBACK_STANDARDS
        comments.append("Validator: Standards MCP unavailable — using fallback rule set.")

    # 3. AI-Driven Knowledge Validation Phase (RAV)
    llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key)
    prompt = f"""
    Evaluate the following Code Diff against the enterprise compliance standards retrieved for this change.

    CODE DIFF:
    {diff}

    RELEVANT STANDARDS (retrieved from knowledge base):
    {standards_context}

    Identify any violations.
    Format: 'VIOLATION: <reason>' (one per line) or 'COMPLIANT'.
    """

    try:
        ai_validation = await llm.ainvoke([HumanMessage(content=prompt)])
        res_content = ai_validation.content
        if isinstance(res_content, list):
            res_text = "".join([str(c) for c in res_content])
        else:
            res_text = str(res_content)

        if "VIOLATION" in res_text.upper():
            signals.append("KNOWLEDGE_VIOLATION_DETECTED")
            comments.append(f"Validator: AI Knowledge Check - {res_text}")
        else:
            signals.append("KNOWLEDGE_CHECK_PASSED")
            comments.append("Validator: AI Knowledge Check - Compliant with enterprise standards.")
    except Exception as e:
        logger.error("❌ Validator: AI knowledge check failed: %s", str(e))
        comments.append(f"Validator: AI knowledge check failed ({str(e)}).")

    return {
        "validator_signals": signals,
        "comments": comments,
    }
