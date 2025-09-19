# Job Agent Toolkit

A collection of services and workflow utilities for turning unstructured resumes into ranked job matches. The repository contains two Machine Control Protocol (MCP) tools—one for resume parsing and one for keyword-based job ranking—plus a FastAPI application that chains them together with LangGraph.

## Repository Layout

- `test/` – **Resume Parser MCP & REST API.** Normalizes free-form resumes via Google Gemini when available, or returns empty structured fields.
- `Keyword-Ranking/` – **Job Ranking MCP & REST API.** Scores job postings against a parsed resume with Gemini or a keyword-overlap fallback.
- `job-agentic-app/` – **Workflow API.** FastAPI app that calls both tools directly or orchestrates them through a LangGraph pipeline.

## Prerequisites

- Python 3.11+ (projects declare 3.13 but run fine on 3.11/3.12 with uv/venv)
- `uv` or `pip` for dependency management
- Google Gemini API key (`GEMINI_API_KEY`) if you want LLM-powered parsing and ranking

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

   # Orchestrator API
   uv pip install -r job-agentic-app/requirements.txt
   ```

4. **Configure environment variables**
   - Copy `.env` templates in `test/` and `Keyword-Ranking/` or set `GEMINI_API_KEY` / `GEMINI_MODEL` in your shell.
   - Without an API key, both services still run but fall back to deterministic keyword extraction/ranking.

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

## Orchestrating with `job-agentic-app`

`job-agentic-app` expects both REST services to be running on ports 9000 and 9090.

```bash
# Start the workflow API (defaults to port 8000)
uvicorn job-agentic-app.app.main:app --reload
```
Available endpoints:
- `POST /parse_resume` – proxy to the resume parser service.
- `POST /rank_jobs` – proxy to the keyword ranking service.
- `POST /process_resume` – LangGraph workflow: parse resume → rank jobs. Returns the `ranked_jobs` payload from the ranking service.

Example workflow call:
```bash
curl -X POST http://127.0.0.1:8000/process_resume \
     -H 'Content-Type: application/json' \
     -d '{"raw_text":"John Doe, Python developer with AWS experience"}'
```

## Development Tips

- Set `MODE=mcp` when the MCP servers need to interact with Coral or Claude; leave unset for REST usage.
- `uv.lock` files exist for reproducible installs. Run `uv pip sync` if you prefer lockfile-driven environments.
- Both services log when Gemini is unavailable and gracefully downgrade to heuristic behavior.
- When Dockerizing, the `test/Dockerfile` builds the resume parser service; mirror its approach for the keyword ranking service if needed.

## Troubleshooting

- **Gemini errors:** ensure the `google-generativeai` package is installed (comes from the requirements) and `GEMINI_API_KEY` is set.
- **HTTP 500 from workflow:** confirms both upstream services are running; the workflow simply forwards their responses.
- **Git warnings about nested repos:** ensure `.git` directories were removed from `test/`, `Keyword-Ranking/`, and `job-agentic-app/` if you copied these projects in from elsewhere.

Happy hacking!
