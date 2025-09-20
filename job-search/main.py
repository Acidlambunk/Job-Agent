import os
import json
import requests
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

# Gemini config
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# JSearch config
JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY")
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"

app = FastAPI()


# 🔹 Step 1: Query JSearch API
def query_jsearch(query: str, location: str = "us") -> dict:
    """Call JSearch API and return formatted jobs."""
    headers = {
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
        "x-rapidapi-key": JSEARCH_API_KEY,
    }
    params = {"query": query, "page": 1, "num_pages": 1, "country": location, "date_posted": "all"}

    try:
        response = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return {"error": str(e)}

    jobs = []
    for job in data.get("data", []):
        jobs.append({
            "id": job.get("job_id"),
            "title": job.get("job_title"),
            "company": job.get("employer_name"),
            "location": job.get("job_city") or job.get("job_country"),
            "description": (job.get("job_description") or "")[:300],  # truncate to 300 chars
            "apply_link": job.get("job_apply_link"),
        })
    return {"jobs": jobs}


# 🔹 Step 2: Build query with Gemini
def build_query_with_gemini(resume: dict, suggested_titles: list) -> str:
    """Use Gemini to turn resume into a job search query string."""
    model = genai.GenerativeModel("gemini-2.0-flash-exp")

    schema_hint = {"query": "Cloud Engineer jobs requiring Python, AWS, Docker"}

    prompt = (
        "You are a job search query builder. "
        "Given a resume (skills, experience, projects) and suggested titles, "
        "produce a short query string (max 10 words) for searching jobs. "
        "Focus on roles and skills. Respond only with JSON.\n\n"
        "Example:\n" + json.dumps(schema_hint) + "\n\n"
        f"Resume:\n{json.dumps(resume)}\n"
        f"Suggested Titles: {', '.join(suggested_titles)}\n"
        "Output JSON with key 'query'."
    )

    response = model.generate_content([prompt])
    text = getattr(response, "text", "").strip()

    # Extract JSON
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(text[start:end+1])
            return parsed.get("query", "developer jobs")
        except Exception:
            return "developer jobs"
    return "developer jobs"


# 🔹 API Endpoint
@app.post("/match_jobs")
def match_jobs(payload: dict):
    """
    Input: resume analyzer output
    Output: relevant job listings from JSearch (manually formatted)
    """
    resume = payload.get("resume", {})
    suggested_titles = payload.get("suggested_titles", [])

    # Build query with Gemini
    query = build_query_with_gemini(resume, suggested_titles)

    # Search jobs (already formatted manually)
    results = query_jsearch(query)

    return {
        "query": query,
        "results": results
    }
