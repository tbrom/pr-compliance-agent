import os
import json
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'orchestrator'))
from graph import build_sentinel_graph

def run_evaluation():
    dataset_dir = os.path.join(os.path.dirname(__file__), 'dataset', 'golden')
    graph = build_sentinel_graph()
    
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0
    
    for filename in os.listdir(dataset_dir):
        if filename.endswith(".json"):
            with open(os.path.join(dataset_dir, filename), 'r') as f:
                data = json.load(f)
                
            initial_state = {
                "pr_id": data["id"],
                "diff_content": data["diff"],
                "jira_context": None,
                "analyst_findings": [],
                "validator_signals": [],
                "final_decision": "",
                "comments": [],
                "error": ""
            }
            
            result = graph.invoke(initial_state)
            actual_decision = result["final_decision"]
            expected_decision = data["expected_decision"]
            
            if actual_decision == "NO-GO" and expected_decision == "NO-GO":
                true_positives += 1
            elif actual_decision == "NO-GO" and expected_decision == "GO":
                false_positives += 1
            elif actual_decision == "GO" and expected_decision == "NO-GO":
                false_negatives += 1
            elif actual_decision == "GO" and expected_decision == "GO":
                true_negatives += 1

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    print(f"Evaluation complete across {true_positives + false_positives + false_negatives + true_negatives} samples.")
    print(f"Precision: {precision:.2f}")
    print(f"Recall: {recall:.2f}")
    print(f"F1 Score: {f1:.2f}")

if __name__ == "__main__":
    run_evaluation()
