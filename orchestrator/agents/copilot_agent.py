import os
from github import Github
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

def handle_copilot_chat(prompt: str, pr_context: dict) -> str:
    """
    Handles a chat request from GitHub Copilot.
    pr_context contains details about the target PR.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key)
    
    # 1. Construct the context for the LLM
    decision = pr_context.get("decision", "UNKNOWN")
    findings = pr_context.get("findings", [])
    signals = pr_context.get("signals", [])
    
    system_prompt = f"""
    You are Sentinel-SDLC, an autonomous compliance and security assistant.
    You just scanned a Pull Request and issued a verdict of {decision}.
    
    Findings: {", ".join(findings)}
    Security Signals: {", ".join(signals)}
    
    Your goal is to help the developer understand WHY their PR was blocked and HOW to fix it.
    Be professional, helpful, and technically accurate.
    If a secret was found, explain the risk of credential leakage.
    If PII was found, explain compliance requirements like GDPR/CCPA.
    
    Format your response in Markdown.
    """
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    return response.content
