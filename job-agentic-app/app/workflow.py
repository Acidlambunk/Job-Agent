import os
from typing import Any, Dict, List

from langgraph.graph import StateGraph

from .mcp_client import call_mcp_tool

# Our shared state
class ResumeState(dict):
    raw_text: str
    parsed_resume: Dict
    ranked_jobs: Dict
    job_search: Dict
    cover_letter: Dict


RESUME_PARSER_URL = os.getenv("RESUME_PARSER_URL", "http://127.0.0.1:9000/parse_resume")
KEYWORD_RANKING_URL = os.getenv("KEYWORD_RANKING_URL", "http://127.0.0.1:9090/rank_jobs")
JOB_SEARCH_URL = os.getenv("JOB_SEARCH_URL", "http://127.0.0.1:9100/match_jobs")
COVER_LETTER_URL = os.getenv("COVER_LETTER_URL", "http://127.0.0.1:9200/generate_cover_letter")



# Node 1: Resume Parser MCP
def parse_resume_node(state: ResumeState) -> ResumeState:
    result = call_mcp_tool(
        RESUME_PARSER_URL,
        {"raw_text": state["raw_text"]}
    )
    state["parsed_resume"] = result
    return state


# Node 2: Keyword Ranking MCP
def rank_jobs_node(state: ResumeState) -> ResumeState:
    result = call_mcp_tool(
        KEYWORD_RANKING_URL,
        {"resume": state.get("parsed_resume", {})}
    )
    state["ranked_jobs"] = result
    return state


# Node 3: Job Search service
def job_search_node(state: ResumeState) -> ResumeState:
    resume_payload = state.get("parsed_resume", {})
    ranking_payload = state.get("ranked_jobs", {})

    suggested_titles: List[str] = []
    if isinstance(ranking_payload, dict):
        titles = ranking_payload.get("suggested_titles", [])
        if isinstance(titles, list):
            suggested_titles = [str(title) for title in titles if str(title).strip()]

    search_request = {
        "resume": resume_payload,
        "suggested_titles": suggested_titles,
    }

    result = call_mcp_tool(JOB_SEARCH_URL, search_request)
    state["job_search"] = result
    return state


# Node 4: Cover Letter generator
def cover_letter_node(state: ResumeState) -> ResumeState:
    resume_payload = state.get("parsed_resume", {})
    job_search_result = state.get("job_search", {})

    job_candidates: List[Dict[str, Any]] = []
    if isinstance(job_search_result, dict):
        results = job_search_result.get("results")
        if isinstance(results, dict):
            jobs = results.get("jobs")
            if isinstance(jobs, list):
                job_candidates = [job for job in jobs if isinstance(job, dict)]

    if not job_candidates:
        ranked_jobs = state.get("ranked_jobs", {})
        if isinstance(ranked_jobs, dict):
            raw_ranked = ranked_jobs.get("ranked_jobs")
            if isinstance(raw_ranked, list):
                job_candidates = [job for job in raw_ranked if isinstance(job, dict)]

    target_job = job_candidates[0] if job_candidates else None
    if not target_job:
        state["cover_letter"] = {"error": "No job data available for cover letter generation."}
        return state

    letter_payload = {
        "resume": resume_payload,
        "job": target_job,
    }

    result = call_mcp_tool(COVER_LETTER_URL, letter_payload)
    state["cover_letter"] = result
    return state


# Build graph
graph = StateGraph(ResumeState)
graph.add_node("parse_resume", parse_resume_node)
graph.add_node("rank_jobs", rank_jobs_node)
graph.add_node("job_search", job_search_node)
graph.add_node("cover_letter", cover_letter_node)
graph.set_entry_point("parse_resume")
graph.add_edge("parse_resume", "rank_jobs")
graph.add_edge("rank_jobs", "job_search")
graph.add_edge("job_search", "cover_letter")

workflow = graph.compile()
