from .state import SentinelState

def validator_node(state: SentinelState) -> dict:
    diff = state.get("diff_content", "")
    signals = state.get("validator_signals", [])
    
    if "AKIA" in diff:
        signals.append("SECRET_DETECTED")
    else:
        signals.append("NO_SECRETS_FOUND")
        
    return {
        "validator_signals": signals,
        "comments": state.get("comments", []) + [f"Validator: Run completion with signals {signals}"]
    }
