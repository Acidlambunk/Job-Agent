from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from .mcp_client import call_mcp_tool
from .workflow import (
    COVER_LETTER_URL,
    JOB_SEARCH_URL,
    KEYWORD_RANKING_URL,
    RESUME_PARSER_URL,
    workflow,
)


app = FastAPI()


class ResumeInput(BaseModel):
    raw_text: str


class RankJobsInput(BaseModel):
    resume: Dict[str, Any]


class JobSearchInput(BaseModel):
    resume: Dict[str, Any]
    suggested_titles: List[str] = []


class CoverLetterInput(BaseModel):
    resume: Dict[str, Any]
    job: Dict[str, Any]
    tone: Optional[str] = "professional"
    length: Optional[str] = "medium"
    include_contact_header: bool = True
    include_links: bool = True


@app.post("/parse_resume")
async def parse_resume(data: ResumeInput):
    """REST passthrough to the resume parser service."""
    return call_mcp_tool(RESUME_PARSER_URL, data.dict())


@app.post("/rank_jobs")
async def rank_jobs(data: RankJobsInput):
    """REST passthrough to the keyword ranking service."""
    return call_mcp_tool(KEYWORD_RANKING_URL, data.dict())


@app.post("/job_search")
async def job_search(data: JobSearchInput):
    """REST passthrough to the job search service."""
    return call_mcp_tool(JOB_SEARCH_URL, data.dict())


@app.post("/generate_cover_letter")
async def generate_cover_letter(data: CoverLetterInput):
    """REST passthrough to the cover letter generator."""
    return call_mcp_tool(COVER_LETTER_URL, data.dict())


@app.post("/process_resume")
async def process_resume(data: ResumeInput):
    """Full LangGraph pipeline: parse resume → rank jobs → search jobs → draft cover letter."""
    state = workflow.invoke({"raw_text": data.raw_text})
    return {
        "parsed_resume": state.get("parsed_resume"),
        "ranked_jobs": state.get("ranked_jobs"),
        "job_search": state.get("job_search"),
        "cover_letter": state.get("cover_letter"),
    }
