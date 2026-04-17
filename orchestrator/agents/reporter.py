"""
Sentinel Reporter agent.

Consumes the signals emitted by Analyst + Validator and applies a
deterministic policy to produce the final verdict. The Reporter is
intentionally LLM-free: signals carry all the judgement that required
reasoning; the final decision should be auditable and reproducible.

Severity tiers
--------------
CRITICAL  — always blocks (hard-coded secrets in code). Admin cannot override
            because a leaked secret, once committed, must be rotated regardless
            of intent.
HIGH      — blocks by default. ADMIN can override to WARN with an audit trail.
MEDIUM    — produces a WARN verdict but does not block.
INFO      — informational; does not affect verdict.
"""

from __future__ import annotations

import logging
from typing import Iterable

from .state import SentinelState

logger = logging.getLogger("sentinel")

# Signal token -> (severity, human-readable reason)
SIGNAL_POLICY: dict[str, tuple[str, str]] = {
    "SECRET_DETECTED":               ("CRITICAL", "Hard-coded secret detected in diff"),
    "PII_DETECTED":                  ("HIGH",     "Unprotected PII detected in diff"),
    "KNOWLEDGE_VIOLATION_DETECTED":  ("HIGH",     "Diff violates enterprise compliance standards"),
    "ANALYST_MISALIGNMENT":          ("MEDIUM",   "Change is not aligned with the Jira ticket"),
    "ANALYST_ALIGNMENT_INCONCLUSIVE":("INFO",     "Analyst could not determine alignment"),
    "ANALYST_ALIGNMENT_OK":          ("INFO",     "Change aligns with the Jira ticket"),
    "KNOWLEDGE_CHECK_PASSED":        ("INFO",     "No compliance violations found"),
}

SEVERITY_ORDER = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "INFO": 0}


def _classify(signal: str) -> tuple[str, str]:
    """Match a signal token (possibly with suffix like ' (Deterministic)') to a policy entry."""
    for token, (severity, reason) in SIGNAL_POLICY.items():
        if signal.startswith(token):
            return severity, reason
    return "INFO", signal


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def reporter_node(state: SentinelState) -> dict:
    signals = state.get("validator_signals", []) or []
    user_role = (state.get("user_role") or "DEVELOPER").upper()
    requester = state.get("requester_login", "unknown")
    comments = state.get("comments", [])

    blocking: list[str] = []
    warnings: list[str] = []
    reasoning: list[str] = []

    top_severity = "INFO"
    for sig in signals:
        severity, reason = _classify(sig)
        line = f"[{severity}] {reason} (signal: `{sig}`)"
        if severity == "CRITICAL":
            blocking.append(line)
        elif severity == "HIGH":
            blocking.append(line)
        elif severity == "MEDIUM":
            warnings.append(line)
        else:
            reasoning.append(line)
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER[top_severity]:
            top_severity = severity

    # Policy application
    decision = "GO"
    override_applied = False

    has_critical = any(_classify(s)[0] == "CRITICAL" for s in signals)
    has_high = any(_classify(s)[0] == "HIGH" for s in signals)
    has_medium = any(_classify(s)[0] == "MEDIUM" for s in signals)

    if has_critical:
        decision = "NO-GO"
        reasoning.insert(0, "🚫 CRITICAL signal present — hard block (no override possible).")
    elif has_high:
        if user_role == "ADMIN":
            decision = "WARN"
            override_applied = True
            # Move HIGH items from blocking to warnings on override
            warnings = blocking + warnings
            blocking = []
            reasoning.insert(
                0,
                f"⚠️ HIGH severity signals present but overridden by ADMIN `{requester}`. "
                "Entry recorded for audit.",
            )
            logger.warning(
                "⚠️  ADMIN override applied by %s — HIGH signals downgraded to WARN. Signals: %s",
                requester, signals,
            )
        else:
            decision = "NO-GO"
            reasoning.insert(0, "🚫 HIGH severity signals present — blocking (ADMIN can override).")
    elif has_medium:
        decision = "WARN"
        reasoning.insert(0, "⚠️ MEDIUM severity signals present — proceed with caution.")
    else:
        reasoning.insert(0, "✅ No blocking signals — all checks passed.")

    reasoning = _dedupe(reasoning)
    blocking = _dedupe(blocking)
    warnings = _dedupe(warnings)

    summary = f"Reporter: Decision `{decision}` (top severity: {top_severity}"
    if override_applied:
        summary += f", override by {requester}"
    summary += ")."
    comments = comments + [summary]

    return {
        "final_decision": decision,
        "decision_reasoning": reasoning,
        "blocking_issues": blocking,
        "warnings": warnings,
        "comments": comments,
    }
