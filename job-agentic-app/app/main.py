from fastapi import FastAPI
from pydantic import BaseModel
from .workflow import workflow
from .mcp_client import call_mcp_tool

app = FastAPI()

class ResumeInput(BaseModel):
    raw_text: str

class RankJobsInput(BaseModel):
    resume: dict

@app.post("/parse_resume")
async def parse_resume(data: ResumeInput):
    """Directly call resume_parser MCP"""
    return call_mcp_tool("http://127.0.0.1:9000/parse_resume", data.dict())

@app.post("/rank_jobs")
async def rank_jobs(data: RankJobsInput):
    """Directly call keyword_ranking MCP"""
    return call_mcp_tool("http://127.0.0.1:9090/rank_jobs", data.dict())

@app.post("/process_resume")
async def process_resume(data: ResumeInput):
    """Full LangGraph pipeline: Resume Parser → Keyword Ranking"""
    state = workflow.invoke({"raw_text": data.raw_text})
    return state["ranked_jobs"]
