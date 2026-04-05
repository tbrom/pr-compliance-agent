from .state import SentinelState

def reporter_node(state: SentinelState) -> dict:
    signals = state.get("validator_signals", [])
    decision = "NO-GO" if "SECRET_DETECTED" in signals else "GO"
        
    return {
        "final_decision": decision,
        "comments": state.get("comments", []) + [f"Reporter: Final decision is {decision}."]
    }
