from langgraph.graph import StateGraph
from typing import Dict
from .mcp_client import call_mcp_tool

# Our shared state
class ResumeState(dict):
    raw_text: str
    parsed_resume: Dict
    ranked_jobs: Dict



# Node 1: Resume Parser MCP
def parse_resume_node(state: ResumeState) -> ResumeState:
    result = call_mcp_tool(
        "http://127.0.0.1:9000/parse_resume",
        {"raw_text": state["raw_text"]}
    )
    state["parsed_resume"] = result
    return state

# Node 2: Keyword Ranking MCP
def rank_jobs_node(state: ResumeState) -> ResumeState:
    result = call_mcp_tool(
        "http://127.0.0.1:9090/rank_jobs",
        {"resume": state["parsed_resume"]}
    )
    state["ranked_jobs"] = result
    return state

# Build graph
graph = StateGraph(ResumeState)
graph.add_node("parse_resume", parse_resume_node)
graph.add_node("rank_jobs", rank_jobs_node)
graph.set_entry_point("parse_resume")
graph.add_edge("parse_resume", "rank_jobs")

workflow = graph.compile()
