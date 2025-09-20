# Job Agent Toolkit

A collection of services and workflow utilities for turning unstructured resumes into ranked job matches. The toolkit now includes two Machine Control Protocol (MCP) tools (resume parsing + keyword ranking), a job search aggregator, a cover letter generator, and a FastAPI application that chains everything together with LangGraph.

## Repository Layout

- `test/` – **Resume Parser MCP & REST API.** Normalizes free-form resumes via Google Gemini when available, or returns empty structured fields.
- `Keyword-Ranking/` – **Job Ranking MCP & REST API.** Scores job postings against a parsed resume with Gemini or a keyword-overlap fallback.
- `job-search/` – **Job Fetcher API.** Uses Gemini to craft a search query, hits the JSearch API, and returns curated job listings.
- `cover-letter-generator/` – **Cover Letter API.** Creates tailored cover letters with Gemini (or a template fallback) and optional DOCX export.
- `job-agentic-app/` – **Workflow API.** FastAPI app that proxies each service and orchestrates the end-to-end LangGraph pipeline.

## Prerequisites

- Python 3.11+ (projects declare 3.13 but run fine on 3.11/3.12 with uv/venv)
- `uv` or `pip` for dependency management
- Google Gemini API key (`GEMINI_API_KEY`) for LLM-powered parsing, ranking, job query generation, and cover letter drafting.
- RapidAPI JSearch key (`JSEARCH_API_KEY`) if you want live job listings from the job-search service.

## Setup

1. **Clone and enter the repo**
   ```bash
   git clone <your-fork-url>
   cd test
   ```

2. **Create virtual environments (optional but recommended)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies per service**
   ```bash
   # Resume parser
   uv pip install -r test/requirements.txt

   # Job ranking
   uv pip install -r Keyword-Ranking/requirements.txt

   # Job search (RapidAPI + Gemini)
   uv pip install -r job-search/requirements.txt

   # Cover letter generator
   uv pip install -r cover-letter-generator/requirements.txt

   # Orchestrator API
   uv pip install -r job-agentic-app/requirements.txt
   ```

4. **Configure environment variables**
- Copy `.env` templates in `test/`, `Keyword-Ranking/`, and `job-search/` (plus `cover-letter-generator/` if you want a custom `OUTPUT_DIR`).
- Required environment variables:
  - `GEMINI_API_KEY` (shared by all services using Gemini)
  - `GEMINI_MODEL` (optional, defaults to `gemini-2.0-flash-exp`)
  - `JSEARCH_API_KEY` for the job search microservice
  - `OUTPUT_DIR` (optional) for the cover letter DOCX export location
- Without Gemini/JSearch keys, services stay online but fall back to heuristic behaviour.

## Running the MCP/REST Services

Both tools support MCP mode (for Coral/Claude integrations) and REST mode (for HTTP clients). REST is the default.

### Resume Parser (`test/main.py`)
```bash
# REST (default) – exposes POST http://127.0.0.1:9000/parse_resume
python test/main.py

# MCP mode – run if you need streamable-http
MODE=mcp python test/main.py
```
Example request:
```bash
curl -X POST http://127.0.0.1:9000/parse_resume \
     -H 'Content-Type: application/json' \
     -d '{"raw_text":"John Doe, Python developer..."}'
```

### Keyword Ranking (`Keyword-Ranking/main.py`)
```bash
# REST (default) – exposes POST http://127.0.0.1:9090/rank_jobs
python Keyword-Ranking/main.py

# MCP mode
MODE=mcp python Keyword-Ranking/main.py
```
Example request:
```bash
curl -X POST http://127.0.0.1:9090/rank_jobs \
     -H 'Content-Type: application/json' \
     -d '{"resume":{"skills":["python","aws"]},"jobs":[{"title":"Backend Engineer","description":"Python, AWS"}]}'
```

### Job Search (`job-search/main.py`)
```bash
# REST – exposes POST http://127.0.0.1:9100/match_jobs
uvicorn job-search.main:app --reload --port 9100
```
Example request:
```bash
curl -X POST http://127.0.0.1:9100/match_jobs \
     -H 'Content-Type: application/json' \
     -d '{"resume":{"skills":["python","aws"]},"suggested_titles":["Backend Engineer"]}'
```

### Cover Letter Generator (`cover-letter-generator/main.py`)
```bash
# REST – exposes POST http://127.0.0.1:9200/generate_cover_letter
uvicorn cover-letter-generator.main:app --reload --port 9200
```
Example request:
```bash
curl -X POST http://127.0.0.1:9200/generate_cover_letter \
     -H 'Content-Type: application/json' \
     -d '{"resume":{"name":"Jane"},"job":{"title":"Backend Engineer"}}'
```

## Orchestrating with `job-agentic-app`

`job-agentic-app` expects all four REST services to be running: resume parser (9000), keyword ranking (9090), job search (9100), and cover letter generator (9200). Override URLs with the environment variables `RESUME_PARSER_URL`, `KEYWORD_RANKING_URL`, `JOB_SEARCH_URL`, and `COVER_LETTER_URL` if you change ports.

```bash
# Start the workflow API (defaults to port 8000)
uvicorn job-agentic-app.app.main:app --reload
```
Available endpoints:
- `POST /parse_resume` – proxy to the resume parser service.
- `POST /rank_jobs` – proxy to the keyword ranking service.
- `POST /job_search` – proxy to the job search service.
- `POST /generate_cover_letter` – proxy to the cover letter generator.
- `POST /process_resume` – LangGraph workflow: parse resume → rank jobs → query job search → draft cover letter. Returns all intermediate payloads so you can inspect each stage.

Example workflow call:
```bash
curl -X POST http://127.0.0.1:8000/process_resume \
     -H 'Content-Type: application/json' \
     -d '{"raw_text":"John Doe, Python developer with AWS experience"}'
```
Response includes `parsed_resume`, `ranked_jobs`, `job_search`, and `cover_letter` sections.

## Development Tips

- Set `MODE=mcp` when the MCP servers need to interact with Coral or Claude; leave unset for REST usage.
- `uv.lock` files exist for reproducible installs. Run `uv pip sync` if you prefer lockfile-driven environments.
- Each Gemini-enabled service logs when the model is unavailable and gracefully downgrades to heuristic behavior.
- When Dockerizing, the `test/Dockerfile` builds the resume parser service; mirror its approach for the other services if needed.

## Troubleshooting

- **Gemini errors:** ensure the `google-generativeai` package is installed (comes from the requirements) and `GEMINI_API_KEY` is set.
- **HTTP 500 from workflow:** confirms all upstream services are running; the workflow simply forwards their responses.
- **Git warnings about nested repos:** ensure `.git` directories were removed from `test/`, `Keyword-Ranking/`, and `job-agentic-app/` if you copied these projects in from elsewhere.

Happy hacking!
