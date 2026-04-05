import os
import httpx
import google.auth.transport.requests
import google.oauth2.id_token
from .state import SentinelState

def validator_node(state: SentinelState) -> dict:
    diff = state.get("diff_content", "")
    evaluator_url = os.getenv("EVALUATOR_URL")
    
    if not evaluator_url:
        return {
            "error": "Validator: EVALUATOR_URL not configured.",
            "comments": state.get("comments", []) + ["Validator: Error - EVALUATOR_URL not configured."]
        }
    
    signals = state.get("validator_signals", [])
    
    # 1. Obtain OIDC ID token for Cloud Run service-to-service auth
    try:
        request = google.auth.transport.requests.Request()
        # The audience is the base URL of the service we're calling
        target_audience = evaluator_url.split("/api")[0] 
        token = google.oauth2.id_token.fetch_id_token(request, target_audience)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    except Exception as e:
        return {
            "error": f"Validator: Failed to obtain OIDC token: {str(e)}",
            "comments": state.get("comments", []) + [f"Validator: Auth error - {str(e)}"]
        }

    # 2. Call the Java Evaluator
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{evaluator_url.rstrip('/')}/api/scan", 
                json={"code": diff},
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("has_secrets"):
                signals.append("SECRET_DETECTED")
            if result.get("has_pii"):
                signals.append("PII_DETECTED")
            
            if not result.get("pass"):
                signals.append("SCAN_FAILED")
            else:
                signals.append("SCAN_PASSED")

            return {
                "validator_signals": signals,
                "comments": state.get("comments", []) + [f"Validator: Scanned via Java API (pass={result.get('pass')})"]
            }
    except Exception as e:
        return {
            "error": f"Validator: Java API call failed: {str(e)}",
            "comments": state.get("comments", []) + [f"Validator: API error - {str(e)}"]
        }
