# agents/cover_letter_agent.py
import os
import json
from datetime import date
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# Optional LLM (Gemini)
try:
    import google.generativeai as genai
except Exception:
    genai = None

# Optional docx output
try:
    from docx import Document
    from docx.shared import Pt, Inches
except Exception:
    Document = None  # docx not installed yet

# ---------- Config ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY and genai:
    genai.configure(api_key=GEMINI_API_KEY)

SAVE_DIR = os.getenv("OUTPUT_DIR", "/mnt/data")  # change if you prefer another path

# ---------- Schemas ----------
class ExperienceItem(BaseModel):
    company: Optional[str] = ""
    role: Optional[str] = ""
    years: Optional[str] = ""
    description: Optional[str] = ""

class EducationItem(BaseModel):
    degree: Optional[str] = ""
    institution: Optional[str] = ""
    years: Optional[str] = ""

class ProjectItem(BaseModel):
    name: Optional[str] = ""
    description: Optional[str] = ""
    tech: Optional[List[str]] = []

class Resume(BaseModel):
    name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    location: Optional[str] = ""
    linkedin: Optional[str] = ""
    summary: Optional[str] = ""
    skills: List[str] = Field(default_factory=list)
    experience: List[Dict[str, Any]] = Field(default_factory=list)
    education: List[Dict[str, Any]] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)

class Job(BaseModel):
    title: Optional[str] = ""
    company: Optional[str] = ""
    location: Optional[str] = ""
    description: Optional[str] = ""
    apply_link: Optional[str] = ""

class CoverLetterRequest(BaseModel):
    resume: Resume
    job: Job
    tone: Optional[str] = "professional"   # "professional", "enthusiastic", etc.
    length: Optional[str] = "medium"        # "short", "medium", "long"
    include_contact_header: bool = True
    include_links: bool = True

class CoverLetterResponse(BaseModel):
    cover_letter_text: str
    docx_path: Optional[str] = None
    used_engine: str

# ---------- Helpers ----------
def _compose_template_letter(payload: CoverLetterRequest) -> str:
    r, j = payload.resume, payload.job
    name = r.name or "Candidate"
    email = r.email or ""
    phone = r.phone or ""
    linkedin = r.linkedin or ""
    today = date.today().strftime("%B %d, %Y")

    # Pick highlights (simple heuristic)
    top_skills = ", ".join(r.skills[:6]) if r.skills else ""
    exp_line = ""
    if r.experience:
        first = r.experience[0]
        role = first.get("role", "")
        company = first.get("company", "")
        years = first.get("years", "")
        exp_line = f"I recently worked as {role} at {company} ({years}). " if role or company else ""

    project_line = ""
    if r.projects:
        p = r.projects[0]
        pname = p.get("name", "")
        pdesc = p.get("description", "")
        project_line = f"Notably, I built {pname}, {pdesc} "

    # Trim length
    extra = ""
    if payload.length == "short":
        extra = ""
    elif payload.length == "long":
        extra = "I value collaborative environments, agile delivery, and clear communication. I’m comfortable owning features end-to-end, writing tests, and documenting decisions.\n\n"

    contact_block = ""
    if payload.include_contact_header:
        contact_items = " | ".join([i for i in [email, phone, linkedin] if i])
        contact_block = f"{name}\n{contact_items}\n\n" if contact_items else f"{name}\n\n"

    company = j.company or "your company"
    title = j.title or "the role"
    location = f" ({j.location})" if j.location else ""

    lines = [
        contact_block,
        today,
        "\n",
        f"Hiring Manager",
        f"{company}{location}",
        "\n",
        f"Dear Hiring Manager,",
        "\n",
        f"I’m excited to apply for the {title} at {company}. {exp_line}"
        f"My core strengths include {top_skills}. {project_line}".strip(),
        "\n",
        "After reviewing the job description, I believe I offer a strong match in:",
    ]

    # Extract simple bullets from job description (naive)
    bullets = []
    if j.description:
        # find lines that look like bullets or key phrases
        for raw in j.description.splitlines():
            s = raw.strip("•-– ").strip()
            if len(s) > 0 and (raw.strip().startswith(("•", "-", "–")) or len(s.split()) > 5):
                bullets.append(s)
            if len(bullets) >= 4:
                break

    if not bullets:
        bullets = [
            "Hands-on experience with cloud platforms and containerization.",
            "Proficiency in Python/Golang and modern CI/CD practices.",
            "Strong understanding of infrastructure as code and DevOps culture.",
        ]

    # turn bullets into a paragraph-friendly dash list
    bullet_block = "\n".join([f"- {b}" for b in bullets])

    closing = (
        f"\n{extra}"
        "I would welcome the opportunity to discuss how my background aligns with your goals. "
        "Thank you for your time and consideration.\n\n"
        "Sincerely,\n"
        f"{name}"
    )

    body = "\n".join(lines) + "\n" + bullet_block + "\n\n" + closing
    return body.strip()


def _compose_llm_letter(payload: CoverLetterRequest) -> str:
    # Use Gemini only if configured
    if not (GEMINI_API_KEY and genai):
        return _compose_template_letter(payload)

    model = genai.GenerativeModel("gemini-2.0-flash-exp")
    schema_hint = {
        "cover_letter_text": "string"
    }
    prompt = (
        "You are a cover-letter writing assistant. Draft a tailored cover letter in clean, readable prose. "
        "Constraints: no hallucinations, incorporate specific overlap between resume and job description, "
        "use a professional but warm tone, and keep it ATS-friendly (no tables/columns). "
        "Do not include markdown. Respond strictly in JSON with key 'cover_letter_text'.\n\n"
        f"Tone: {payload.tone}\n"
        f"Length: {payload.length}\n"
        f"Resume JSON:\n{payload.resume.model_dump_json()}\n\n"
        f"Job JSON:\n{payload.job.model_dump_json()}\n\n"
        f"Example JSON shape:\n{json.dumps(schema_hint)}\n"
        "Now return only the JSON with 'cover_letter_text'."
    )
    try:
        resp = model.generate_content([prompt])
        text = getattr(resp, "text", "") or ""
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            parsed = json.loads(text[start:end+1])
            draft = parsed.get("cover_letter_text")
            if draft and isinstance(draft, str):
                return draft.strip()
    except Exception:
        pass

    # Fallback template
    return _compose_template_letter(payload)


def _save_docx(cover_letter_text: str, name_hint: str = "Cover_Letter") -> Optional[str]:
    if Document is None:
        return None
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        safe_name = "".join(c for c in name_hint if c.isalnum() or c in ("_", "-")) or "Cover_Letter"
        path = os.path.join(SAVE_DIR, f"{safe_name}.docx")
        doc = Document()
        # simple formatting
        for para in cover_letter_text.split("\n"):
            p = doc.add_paragraph(para)
            p.style.font.size = Pt(11)
        doc.save(path)
        return path
    except Exception:
        return None

# ---------- FastAPI ----------
app = FastAPI(title="Cover Letter Agent")

@app.post("/generate_cover_letter", response_model=CoverLetterResponse)
def generate_cover_letter(
    payload: CoverLetterRequest,
    as_docx: bool = Query(default=False, description="If true, also save a .docx and return its path.")
):
    text = _compose_llm_letter(payload)
    used_engine = "gemini" if (GEMINI_API_KEY and genai) else "template"
    docx_path = _save_docx(text, (payload.resume.name or "Cover_Letter").replace(" ", "_")) if as_docx else None
    return CoverLetterResponse(cover_letter_text=text, docx_path=docx_path, used_engine=used_engine)
