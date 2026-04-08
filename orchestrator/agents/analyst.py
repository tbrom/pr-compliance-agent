import os
import re
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from .state import SentinelState

logger = logging.getLogger("sentinel")

def analyst_node(state: SentinelState) -> dict:
    branch_name = state.get("branch_name", "")
    diff_content = state.get("diff_content", "")
    comments = state.get("comments", [])
    findings = state.get("analyst_findings", [])
    
    # 1. Extract Jira ID from branch name: ticketType/projectId-storyNumber
    # e.g., feat/STNL-123
    jira_id = "UNKNOWN"
    match = re.search(r"([a-z]+)/([A-Z]+-[0-9]+)", branch_name)
    if match:
        jira_id = match.group(2)
        logger.info("🔍 Analyst: Identified Jira ID %s from branch %s", jira_id, branch_name)
    
    # 2. Simulated call to the Jira MCP Tool (Target State Logic)
    # In a real scenario, we would call the get_jira_issue tool here.
    # For now, we simulate the 'Acceptance Criteria' based on the Jira ID.
    jira_requirements = f"Acceptance Criteria for {jira_id}: Implement semantic alignment with the enterprise Data Fabric schema and ensure all internal endpoints are authenticated."
    
    # 3. Perform AI reasoning
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("❌ Analyst: GOOGLE_API_KEY not found in environment")
        return {
            "error": "GOOGLE_API_KEY not found", 
            "comments": comments + ["Analyst: Failed due to missing AI credentials."]
        }

    llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key)
    
    prompt = f"""
    You are a Strategic Security Analyst. Your task is to verify that the code changes in this PR align with the business requirements defined in Jira and the enterprise Data Fabric standards.
    
    Jira Ticket: {jira_id}
    Requirements Context: {jira_requirements}
    
    PR Diff:
    {diff_content[:5000]}
    
    Analyze the diff against the requirements. 
    1. Does the code satisfy the semantic intent of the ticket?
    2. Are there any 'rogue' changes that aren't mentioned in the ticket?
    3. Does the code structure meet basic Data Fabric semantic definitions?
    
    Provide a one-sentence definitive verdict.
    """
    
    try:
        response = llm.invoke(prompt)
        analyst_response = response.content
        findings.append(f"Alignment Analysis for {jira_id}: {analyst_response}")
        comments.append(f"Analyst: Verified code alignment with branch-derived ticket {jira_id}.")
    except Exception as e:
        logger.error("❌ Analyst: Reasoning failed for %s: %s", jira_id, str(e))
        comments.append(f"Analyst: Failed to perform semantic reasoning for {jira_id} ({str(e)}).")

    return {
        "jira_id": jira_id,
        "analyst_findings": findings,
        "comments": comments
    }
