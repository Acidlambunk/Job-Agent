import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, Body
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    genai = None


mcp = FastMCP(
    name="keyword_ranking",
    host="127.0.0.1",
    port=9090,
)

logger = logging.getLogger("Keyword-Ranking")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        logger.debug("No .env file found at %s", env_path)
        return

    try:
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            cleaned = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, cleaned)
        logger.info("Loaded environment variables from %s", env_path)
    except Exception as exc:
        logger.warning("Failed to load .env file %s: %s", env_path, exc)


_load_env_file()


def _safe_json_loads(data: str) -> Any:
    try:
        return json.loads(data)
    except Exception:
        return None


def _ensure_resume_shape(obj: Dict[str, Any]) -> Dict[str, Any]:
    profile: Dict[str, Any] = {
        "skills": obj.get("skills") or [],
        "experience": obj.get("experience") or [],
        "education": obj.get("education") or [],
        "projects": obj.get("projects") or [],
        "summary": obj.get("summary") or obj.get("headline") or "",
    }

    if not isinstance(profile["skills"], list):
        profile["skills"] = []
    else:
        profile["skills"] = [str(skill) for skill in profile["skills"] if str(skill).strip()]

    normalized_exp: List[Dict[str, str]] = []
    for exp in profile["experience"]:
        if not isinstance(exp, dict):
            continue
        normalized_exp.append(
            {
                "company": str(exp.get("company", "")),
                "role": str(exp.get("role", "")),
                "years": str(exp.get("years", "")),
                "description": str(exp.get("description", "")),
            }
        )
    profile["experience"] = normalized_exp

    normalized_edu: List[Dict[str, str]] = []
    for edu in profile["education"]:
        if not isinstance(edu, dict):
            continue
        normalized_edu.append(
            {
                "degree": str(edu.get("degree", "")),
                "institution": str(edu.get("institution", "")),
                "years": str(edu.get("years", "")),
            }
        )
    profile["education"] = normalized_edu

    normalized_projects: List[Dict[str, Any]] = []
    for proj in profile["projects"]:
        if not isinstance(proj, dict):
            continue
        tech = proj.get("tech") or []
        if not isinstance(tech, list):
            tech = []
        normalized_projects.append(
            {
                "name": str(proj.get("name", "")),
                "description": str(proj.get("description", "")),
                "tech": [str(t) for t in tech if str(t).strip()],
            }
        )
    profile["projects"] = normalized_projects

    return profile


def _resume_textual_view(resume: Dict[str, Any]) -> str:
    parts: List[str] = []

    summary = resume.get("summary")
    if summary:
        parts.append(f"Summary: {summary}")

    skills = resume.get("skills", [])
    if skills:
        parts.append("Skills: " + ", ".join(skills))

    experience = resume.get("experience", [])
    for exp in experience:
        pieces = [exp.get("role"), exp.get("company"), exp.get("years"), exp.get("description")]
        parts.append("Experience: " + ", ".join(filter(None, pieces)))

    education = resume.get("education", [])
    for edu in education:
        pieces = [edu.get("degree"), edu.get("institution"), edu.get("years")]
        parts.append("Education: " + ", ".join(filter(None, pieces)))

    projects = resume.get("projects", [])
    for project in projects:
        tech = project.get("tech")
        tech_str = ", ".join(tech) if tech else ""
        pieces = [project.get("name"), project.get("description"), tech_str]
        parts.append("Project: " + ", ".join(filter(None, pieces)))

    return "\n".join(parts)


def _normalize_jobs(jobs: List[Any]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for job in jobs:
        if isinstance(job, str):
            parsed = _safe_json_loads(job)
            if isinstance(parsed, dict):
                job = parsed
            else:
                job = {"title": job, "description": job}

        if not isinstance(job, dict):
            continue

        identifier = job.get("id") or job.get("job_id") or job.get("slug") or job.get("title")
        title = job.get("title") or job.get("role") or ""
        company = job.get("company") or job.get("employer") or ""
        description = job.get("description") or job.get("summary") or ""
        requirements = job.get("requirements") or job.get("responsibilities") or job.get("skills") or ""
        location = job.get("location") or ""

        normalized.append(
            {
                "id": str(identifier) if identifier else title[:40],
                "title": str(title),
                "company": str(company),
                "description": str(description),
                "requirements": str(requirements),
                "location": str(location),
            }
        )
    return [job for job in normalized if job.get("title") or job.get("description")]


def _resume_signal_text(resume: Dict[str, Any]) -> str:
    """Aggregate resume fields into a lowercase blob for keyword matching."""

    pieces: List[str] = []

    skills = resume.get("skills") or []
    if isinstance(skills, list):
        pieces.extend([str(skill) for skill in skills])

    for exp in resume.get("experience", []) or []:
        if not isinstance(exp, dict):
            continue
        pieces.extend(
            [
                str(exp.get("role", "")),
                str(exp.get("company", "")),
                str(exp.get("years", "")),
                str(exp.get("description", "")),
            ]
        )

    for project in resume.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        pieces.extend(
            [
                str(project.get("name", "")),
                str(project.get("description", "")),
            ]
        )
        tech_stack = project.get("tech") or []
        if isinstance(tech_stack, list):
            pieces.extend([str(item) for item in tech_stack])

    for edu in resume.get("education", []) or []:
        if not isinstance(edu, dict):
            continue
        pieces.extend(
            [
                str(edu.get("degree", "")),
                str(edu.get("institution", "")),
            ]
        )

    return " ".join(filter(None, pieces)).lower()


SuggestionRule = Dict[str, Any]


SUGGESTION_RULES: List[SuggestionRule] = [
    {"keywords": {"cloud", "azure", "aws", "gcp", "terraform"}, "title": "Cloud Engineer"},
    {"keywords": {"kubernetes", "docker", "devops", "ci/cd"}, "title": "DevOps Engineer"},
    {"keywords": {"machine learning", "ml", "tensorflow", "pytorch"}, "title": "Machine Learning Engineer"},
    {"keywords": {"ai", "rag", "langchain", "llm"}, "title": "AI Engineer"},
    {"keywords": {"data", "analytics", "sql", "etl", "warehouse"}, "title": "Data Engineer"},
    {"keywords": {"backend", "fastapi", "django", "golang", "go", "python", "api"}, "title": "Backend Engineer"},
    {"keywords": {"full stack", "react", "next.js", "typescript", "javascript"}, "title": "Full Stack Engineer"},
    {"keywords": {"frontend", "ui", "ux", "react", "javascript"}, "title": "Frontend Engineer"},
    {"keywords": {"web3", "blockchain", "solidity", "polygon", "nft"}, "title": "Blockchain Engineer"},
    {"keywords": {"security", "iam", "cybersecurity"}, "title": "Security Engineer"},
    {"keywords": {"product", "manager", "roadmap"}, "title": "Product Manager"},
]


def _suggest_job_titles(resume: Dict[str, Any], limit: int = 5) -> List[str]:
    """Generate suggested role titles based on resume content heuristics."""

    blob = _resume_signal_text(resume)
    if not blob:
        return ["Software Engineer"]

    suggestions: List[str] = []
    for rule in SUGGESTION_RULES:
        keywords = rule.get("keywords") or set()
        if not isinstance(keywords, set):
            keywords = set(keywords)

        if any(keyword in blob for keyword in keywords):
            title = str(rule.get("title", "")).strip()
            if title and title not in suggestions:
                suggestions.append(title)
        if len(suggestions) >= limit:
            break

    if not suggestions:
        suggestions.append("Software Engineer")

    return suggestions[:limit]


def _fallback_rank(
    resume: Dict[str, Any],
    jobs: List[Dict[str, str]],
    suggested_titles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    skills = {skill.lower() for skill in resume.get("skills", [])}
    ranked: List[Dict[str, Any]] = []

    for job in jobs:
        job_text = " ".join(
            filter(
                None,
                [job.get("title"), job.get("description"), job.get("requirements")],
            )
        ).lower()

        overlap = [skill for skill in skills if skill and skill in job_text]
        score = round(len(overlap) / max(len(skills), 1), 2) if skills else 0.0
        ranked.append(
            {
                "id": job.get("id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "score": score,
                "fit_summary": "Keyword overlap heuristic",
                "skill_alignment": overlap,
                "gaps": [],
            }
        )

    ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
    return {
        "engine": "fallback-keyword",
        "ranked_jobs": ranked,
        "suggested_titles": suggested_titles or _suggest_job_titles(resume),
    }


def _call_gemini_job_ranking(
    resume: Dict[str, Any],
    resume_text: str,
    jobs: List[Dict[str, str]],
) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_id = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

    if not api_key:
        logger.info("Gemini unavailable: missing GEMINI_API_KEY/GOOGLE_API_KEY")
        return {"missing": "gemini"}
    if genai is None:
        logger.info("Gemini unavailable: google-generativeai package not installed")
        return {"missing": "gemini"}

    try:
        logger.info("Gemini available: using model %s", model_id)
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_id)

        schema_hint = {
            "engine": "gemini",
            "suggested_titles": ["Cloud Engineer", "AI Engineer", "Backend Engineer"],
            "candidate_observations": {
                "strengths": ["Cloud infrastructure", "API development"],
                "risks": ["Limited fintech experience"],
            },
        }

        prompt = (
            "You evaluate candidate -> job fit. "
            "Given structured resume data and job listings, respond with STRICT JSON only. "
            "Rank jobs by fit score between 0 and 1. Always include all provided jobs. "
            "For each ranked job, copy the exact title and company text from the input list and do not invent new roles. "
            "Provide concise reasoning and highlight skills that align or are missing. "
            "Also produce a `suggested_titles` list (3-5 items) of role titles that match the candidate's experience."
        )

        request_payload = {
            "resume": resume,
            "resume_text": resume_text,
        }

        request = (
            "Return JSON matching this shape (fields optional but keep data types):\n"
            + json.dumps(schema_hint)
            + "\nNever include commentary outside JSON."
        )

        response = model.generate_content([
            prompt,
            request,
            "Structured Input:\n" + json.dumps(request_payload, ensure_ascii=False, indent=2),
            "Output JSON:",
        ])

        text = getattr(response, "text", "")
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            data = _safe_json_loads(candidate)
            if isinstance(data, dict) and data.get("ranked_jobs"):
                logger.info("Gemini ranking succeeded")
                return data

        logger.info("Gemini response missing JSON payload; falling back")
    except Exception as exc:  # pragma: no cover - network/LLM issues
        logger.exception("Gemini ranking call failed: %s", exc)

    return {"missing": "gemini"}


@mcp.tool()
def rank_jobs(payload: Any) -> Dict[str, Any]:
    """Rank supplied job listings for a candidate using Gemini when available.
       If no jobs are provided, just return the normalized resume and suggested titles.
    """

    if payload is None:
        return {"error": "Expected JSON payload with resume (and optional jobs)."}

    parsed = payload if isinstance(payload, dict) else _safe_json_loads(str(payload))
    if not isinstance(parsed, dict):
        return {"error": "Payload must be JSON object with resume (and optional jobs)."}
    
    resume_raw: Optional[Any] = parsed.get("resume", parsed)  # support top-level resume
    jobs = parsed.get("jobs", [])  # default empty list ✅

    
    resume_dict: Dict[str, Any] = {
        "skills": [],
        "experience": [],
        "education": [],
        "projects": [],
        "summary": "",
    }
    resume_text = ""
    if isinstance(resume_raw, dict):
        resume_dict = _ensure_resume_shape(resume_raw)
        resume_text = _resume_textual_view(resume_dict)
    elif isinstance(resume_raw, str):
        maybe = _safe_json_loads(resume_raw)
        if isinstance(maybe, dict):
            resume_dict = _ensure_resume_shape(maybe)
            resume_text = _resume_textual_view(resume_dict)
        else:
            resume_text = resume_raw
    else:
        resume_text = str(resume_raw)

    if not resume_text:
        resume_text = _resume_textual_view(resume_dict)

    suggested_titles = _suggest_job_titles(resume_dict)

    
    if jobs:
        jobs = _normalize_jobs(jobs)
        if jobs:
            gemini_result = _call_gemini_job_ranking(resume_dict, resume_text, jobs)
            if gemini_result.get("ranked_jobs"):
                gemini_result.setdefault("engine", "gemini")
                gemini_result.setdefault("suggested_titles", suggested_titles)
                return gemini_result

            fallback = _fallback_rank(resume_dict, jobs, suggested_titles)
            return fallback

    
    return {
        "engine": "resume-analyzer",
        "resume": resume_dict,
        "suggested_titles": suggested_titles,
    }




# ----------------------------
# FastAPI Setup
# ----------------------------
app = FastAPI()

class RankJobsInput(BaseModel):
    payload: dict

@app.post("/rank_jobs")
async def rank_jobs_api(data: dict = Body(...)):
    """
    REST wrapper around the MCP tool.
    Now you can hit this endpoint with curl/Postman/frontend.
    """
    return rank_jobs(data)

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    mode = os.getenv("MODE", "rest")  # switch easily: MCP or REST
    if mode == "mcp":
        mcp.run("streamable-http")   # MCP mode for Coral/Claude
    else:
        uvicorn.run(app, host="127.0.0.1", port=9090)