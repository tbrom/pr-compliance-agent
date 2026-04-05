from graph import build_sentinel_graph

def test_sentinel_graph():
    graph = build_sentinel_graph()
    initial_state = {
        "pr_id": 1,
        "diff_content": "+ apiKey = 'AKIA1234567890ABCDEF'",
        "jira_context": None,
        "analyst_findings": [],
        "validator_signals": [],
        "final_decision": "",
        "comments": [],
        "error": ""
    }
    
    final_state = graph.invoke(initial_state)
    
    assert final_state["final_decision"] == "NO-GO"
    assert "SECRET_DETECTED" in final_state["validator_signals"]
    assert "Scout: Fetched PR diff and Jira context." in final_state["comments"]
