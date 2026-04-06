import os
import httpx
import google.auth.transport.requests
import google.oauth2.id_token
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from .state import SentinelState

def validator_node(state: SentinelState) -> dict:
    diff = state.get("diff_content", "")
    evaluator_url = os.getenv("EVALUATOR_URL")
    api_key = os.getenv("GOOGLE_API_KEY")
    
    signals = state.get("validator_signals", [])
    comments = state.get("comments", [])

    # 1. Knowledge Retrieval Phase (RAV)
    # We'll use Gemini to reason about which standards apply based on the diff.
    # In a full MCP production setup, this would be an actual tool call to the standards-mcp.
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key)
    
    # 2. Call Java Evaluator (Deterministic Shield)
    if evaluator_url:
        try:
            request = google.auth.transport.requests.Request()
            target_audience = evaluator_url.split("/api")[0] 
            token = google.oauth2.id_token.fetch_id_token(request, target_audience)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(f"{evaluator_url.rstrip('/')}/api/scan", json={"code": diff}, headers=headers)
                result = response.json()
                if result.get("has_secrets"): signals.append("SECRET_DETECTED (Deterministic)")
                if result.get("has_pii"): signals.append("PII_DETECTED (Deterministic)")
        except Exception as e:
            comments.append(f"Validator: Deterministic scan skipped/failed: {str(e)}")

    # 3. AI-Driven Knowledge Validation Phase (RAV)
    # This represents the "retrieved" knowledge from the standards MCP server.
    prompt = f"""
    Evaluate the following Code Diff against Enterprise Standards.
    
    CODE DIFF:
    {diff}
    
    RELEVANT STANDARDS (Retrieved from Knowledge Base):
    - SEC-001 (PII): Raw SSNs and account numbers must be tokenized.
    - SEC-002 (Secrets): Hardcoded AWS_KEY, CLIENT_SECRET, etc. are prohibited. Use Secret Manager.
    - SEC-003 (Containers): Use Alpine/Wolfram base images in Dockerfiles.
    - SEC-004 (Networking): Use mTLS and https:// for internal communication.
    
    Identify any violations. 
    Format: 'VIOLATION: <reason>' or 'COMPLIANT'.
    """
    
    ai_validation = llm.invoke([HumanMessage(content=prompt)])
    res_text = ai_validation.content.upper()
    
    if "VIOLATION" in res_text:
        signals.append("KNOWLEDGE_VIOLATION_DETECTED")
        comments.append(f"Validator: AI Knowledge Check - {ai_validation.content}")
    else:
        signals.append("KNOWLEDGE_CHECK_PASSED")
        comments.append("Validator: AI Knowledge Check - Compliant with enterprise standards.")

    return {
        "validator_signals": signals,
        "comments": state.get("comments", []) + comments
    }
