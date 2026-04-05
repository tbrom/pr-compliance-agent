from langgraph.graph import StateGraph, END
from agents.state import SentinelState
from agents.scout import scout_node
from agents.analyst import analyst_node
from agents.validator import validator_node
from agents.reporter import reporter_node

def build_sentinel_graph():
    workflow = StateGraph(SentinelState)
    
    workflow.add_node("scout", scout_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("reporter", reporter_node)
    
    workflow.set_entry_point("scout")
    workflow.add_edge("scout", "analyst")
    workflow.add_edge("analyst", "validator")
    workflow.add_edge("validator", "reporter")
    workflow.add_edge("reporter", END)
    
    return workflow.compile()
