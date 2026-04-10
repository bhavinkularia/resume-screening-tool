"""
ATS — Applicant Tracking System
Rule-based resume screening. Skills matched ONLY from SKILL_LIBRARY.
No free-form token extraction. No noise. Clean modular design.
"""

import io
import re
from collections import defaultdict

import streamlit as st
import pdfplumber
import docx
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ===========================================================================
# SKILL LIBRARY
# Single source of truth. Only these exact strings will ever match.
# Add domain-specific skills here to extend coverage.
# ===========================================================================

SKILL_LIBRARY: dict[str, list[str]] = {
    "programming": [
        "python", "r", "java", "javascript", "typescript", "c", "c++", "c#",
        "golang", "go", "rust", "scala", "kotlin", "swift", "php", "ruby",
        "perl", "matlab", "bash", "shell", "powershell", "vba", "sas", "stata",
        "julia", "cobol", "assembly",
    ],
    "web": [
        "html", "css", "react", "react.js", "angular", "vue", "vue.js",
        "next.js", "node.js", "express", "django", "flask", "fastapi",
        "spring", "asp.net", "laravel", "rails", "graphql", "rest api",
        "restful api", "soap", "webpack", "tailwind", "bootstrap", "jquery",
        "redux", "svelte",
    ],
    "data": [
        "sql", "mysql", "postgresql", "sqlite", "oracle", "ms sql", "sql server",
        "nosql", "mongodb", "cassandra", "redis", "elasticsearch",
        "excel", "google sheets", "pivot tables", "vlookup", "power query",
        "tableau", "power bi", "looker", "qlikview", "qliksense", "metabase",
        "data analysis", "data analytics", "analytics", "data visualization",
        "data wrangling", "data cleaning", "etl", "data pipeline",
        "data engineering", "data modeling", "data warehousing",
        "big data", "hadoop", "spark", "kafka", "airflow", "dbt",
        "snowflake", "redshift", "bigquery", "databricks", "hive",
        "pandas", "numpy", "matplotlib", "seaborn", "plotly",
        "statistics", "statistical analysis", "hypothesis testing",
        "regression", "time series", "forecasting", "a/b testing",
    ],
    "ml_ai": [
        "machine learning", "deep learning", "neural networks",
        "natural language processing", "nlp", "computer vision",
        "reinforcement learning", "supervised learning", "unsupervised learning",
        "classification", "clustering", "recommendation systems",
        "feature engineering", "model deployment", "mlops",
        "scikit-learn", "sklearn", "tensorflow", "keras", "pytorch",
        "xgboost", "lightgbm", "catboost", "hugging face", "transformers",
        "bert", "gpt", "llm", "generative ai", "langchain", "rag",
        "opencv", "yolo", "object detection",
    ],
    "cloud_devops": [
        "aws", "azure", "gcp", "google cloud", "cloud computing",
        "docker", "kubernetes", "terraform", "ansible", "chef", "puppet",
        "ci/cd", "jenkins", "github actions", "gitlab ci", "circleci",
        "linux", "unix", "nginx", "apache", "microservices",
        "serverless", "lambda", "azure functions", "devops",
        "infrastructure as code", "prometheus", "grafana",
    ],
    "databases": [
        "database design", "database administration", "dba",
        "stored procedures", "indexing", "query optimization",
        "data migration",
    ],
    "finance": [
        "finance", "financial analysis", "financial modeling", "financial reporting",
        "accounting", "bookkeeping", "accounts payable", "accounts receivable",
        "general ledger", "reconciliation",
        "budgeting", "variance analysis", "cost analysis",
        "valuation", "dcf", "discounted cash flow", "equity research",
        "investment banking", "private equity", "venture capital",
        "portfolio management", "risk management", "credit analysis",
        "audit", "taxation", "tax", "gst", "tds",
        "ifrs", "gaap", "us gaap", "ind as",
        "tally", "quickbooks", "sap fico", "oracle financials",
        "ms dynamics", "xero", "zoho books",
        "balance sheet", "income statement", "cash flow statement",
        "working capital", "capex", "ebitda", "irr", "npv",
        "mergers and acquisitions", "m&a",
    ],
    "marketing": [
        "marketing", "digital marketing", "performance marketing",
        "seo", "sem", "search engine optimization", "search engine marketing",
        "google ads", "google adwords", "facebook ads", "meta ads",
        "instagram ads", "linkedin ads", "programmatic advertising",
        "content marketing", "content strategy", "content creation",
        "social media marketing", "social media management",
        "email marketing", "marketing automation", "crm",
        "hubspot", "salesforce", "marketo", "mailchimp", "klaviyo",
        "branding", "brand management", "brand strategy",
        "market research", "consumer insights", "competitive analysis",
        "product marketing", "go to market", "gtm strategy",
        "growth hacking", "growth marketing", "retention marketing",
        "affiliate marketing", "influencer marketing",
        "ahrefs", "semrush", "moz", "google analytics",
        "google tag manager", "mixpanel", "amplitude", "clevertap",
        "conversion rate optimization", "cro",
        "copywriting", "ad copywriting",
    ],
    "sales": [
        "sales", "b2b sales", "b2c sales", "inside sales", "field sales",
        "business development", "lead generation", "prospecting",
        "cold calling", "cold emailing", "outbound sales",
        "account management", "key account management", "kam",
        "client relationship management", "customer success",
        "revenue generation", "deal closing", "negotiation",
        "pipeline management", "crm management",
        "salesforce crm", "zoho crm", "hubspot crm",
    ],
    "product_project": [
        "product management", "product roadmap", "product strategy",
        "agile", "scrum", "kanban", "sprint planning", "backlog grooming",
        "jira", "confluence", "trello", "asana", "notion",
        "project management", "pmp", "prince2",
        "stakeholder management", "requirement gathering",
        "user stories", "mvp", "product launch",
        "ux", "ui", "user experience", "user interface",
        "wireframing", "prototyping", "figma", "sketch", "zeplin",
        "usability testing", "user research",
    ],
    "hr": [
        "human resources", "talent acquisition", "recruitment",
        "sourcing", "talent management", "performance management",
        "learning and development", "training",
        "compensation and benefits", "payroll", "hris",
        "employee engagement", "employee relations",
        "organizational development", "change management",
        "hr analytics", "workforce planning",
        "workday", "successfactors", "bamboohr", "darwinbox",
        "linkedin recruiter",
    ],
    "operations": [
        "operations management", "supply chain", "supply chain management",
        "procurement", "vendor management",
        "inventory management", "warehouse management",
        "logistics", "last mile delivery", "fulfillment",
        "lean", "six sigma", "kaizen", "process improvement",
        "quality assurance", "quality control",
        "erp", "sap", "oracle erp",
    ],
    "soft_skills": [
        "communication", "written communication", "verbal communication",
        "presentation", "public speaking", "leadership", "team leadership",
        "problem solving", "critical thinking", "decision making",
        "time management", "project coordination",
        "client communication", "stakeholder communication",
    ],
    "research": [
        "research", "literature review", "research methodology",
        "quantitative research", "qualitative research",
        "survey design", "data collection", "report writing",
        "academic writing", "peer review",
    ],
    "legal": [
        "legal research", "contract drafting", "contract review",
        "compliance", "regulatory compliance", "gdpr", "data privacy",
        "intellectual property", "corporate law", "litigation",
    ],
    "healthcare": [
        "clinical research", "clinical trials", "pharmacovigilance",
        "medical writing", "regulatory affairs", "gcp", "gmp",
        "healthcare management", "hospital management", "ehr", "emr",
    ],
    "design": [
        "graphic design", "visual design", "ui design", "ux design",
        "adobe photoshop", "photoshop", "illustrator", "adobe illustrator",
        "indesign", "after effects", "premiere pro",
        "canva", "figma", "sketch", "invision",
        "video editing", "motion graphics", "3d modeling",
        "autocad", "solidworks", "catia",
    ],
}

# ---------------------------------------------------------------------------
# Pre-computed flat structures derived from SKILL_LIBRARY
# ---------------------------------------------------------------------------

# Flat set of every valid skill (lowercase)
_ALL_SKILLS: set[str] = {
    skill.lower().strip()
    for skills in SKILL_LIBRARY.values()
    for skill in skills
}

# Sorted longest-first so multi-word skills are checked before substrings.
# e.g. "machine learning" is checked before "learning"
_SKILLS_BY_LENGTH: list[str] = sorted(_ALL_SKILLS, key=len, reverse=True)

# Pre-compiled word-boundary-aware patterns keyed by skill string
_SKILL_PATTERNS: dict[str, re.Pattern] = {
    skill: re.compile(
        r"(?<![a-z0-9\-\+\#\.])" + re.escape(skill) + r"(?![a-z0-9\-\+\#\.])",
        re.IGNORECASE,
    )
    for skill in _SKILLS_BY_LENGTH
}


# ===========================================================================
# EDUCATION MAP
# Ordered from highest to lowest so the first match wins.
# ===========================================================================

EDUCATION_DEGREES: list[tuple[list[str], int]] = [
    (["phd", "ph.d", "doctorate", "doctor of philosophy"], 100),
    (["m.tech", "mtech", "master of technology", "master of engineering"], 90),
    (["mba", "master of business administration", "masters in business"], 88),
    (["master", "masters", "m.s.", "m.sc", "msc", "master of science",
      "master of arts", "m.a."], 85),
    (["b.tech", "btech", "b.e.", "bachelor of technology",
      "bachelor of engineering"], 75),
    (["bachelor", "bachelors", "b.sc", "bsc", "bachelor of science",
      "b.com", "bcom", "bachelor of commerce", "b.a.", "bba",
      "bachelor of arts", "bachelor of business"], 70),
    (["diploma", "associate degree", "associate"], 50),
    (["12th", "hsc", "higher secondary", "intermediate", "senior secondary"], 35),
    (["10th", "ssc", "secondary school", "matric"], 20),
]


# ===========================================================================
# EXPERIENCE EXTRACTION
# ===========================================================================

_EXP_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp\b)", re.I),
    re.compile(r"experience\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*\+?\s*years?", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*yrs?\s+(?:of\s+)?(?:experience|exp\b)", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?(?:work|industry|relevant|professional)", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+exp", re.I),
]

# Skills section header keywords
_SKILLS_HEADERS: set[str] = {
    "skills", "technical skills", "core competencies",
    "technologies", "tech stack", "tools", "expertise",
    "competencies", "proficiencies", "key skills",
    "areas of expertise", "tools & technologies",
}

# Section headers that end a skills block
_OTHER_SECTIONS: set[str] = {
    "education", "experience", "work experience", "employment history",
    "projects", "certifications", "awards", "publications",
    "interests", "hobbies", "references", "summary", "objective",
    "profile", "about", "achievements", "languages", "extracurricular",
    "volunteering", "training", "courses",
}

_SKILLS_HDR_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(h) for h in _SKILLS_HEADERS) + r")\s*[:\-]?\s*$",
    re.IGNORECASE,
)
_OTHER_HDR_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(h) for h in _OTHER_SECTIONS) + r")\s*[:\-]?\s*$",
    re.IGNORECASE,
)

# Noise removal: currency symbols, salary patterns, standalone numbers, dates
_NOISE_RES: list[re.Pattern] = [
    re.compile(r"[\$₹€£¥]\s*[\d,]+(?:\.\d+)?(?:k|l|lpa|lakh)?", re.I),
    re.compile(r"\d[\d,]*\s*(?:k|lpa|lakh|lac|cr|crore)?(?:/month|/year|per month|p\.m\.?|p\.a\.?)", re.I),
    re.compile(r"(?<![a-zA-Z])\b\d{4}\b"),           # 4-digit years
    re.compile(r"(?<![a-zA-Z\.])\b\d{1,3}\b(?!\s*[a-zA-Z%])"),  # loose small numbers
    re.compile(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,]+\d{4}\b",
        re.I,
    ),
    re.compile(r"stipend|salary|ctc|lpa|per annum|per month", re.I),
    re.compile(r"[^a-zA-Z0-9\s\.\-\+\#/&]"),         # non-skill characters
]


# ===========================================================================
# TEXT CLEANING
# ===========================================================================

def clean_text(text: str) -> str:
    """
    Remove salary figures, dates, bare numbers, and special characters
    that would otherwise create false skill matches.
    """
    for pat in _NOISE_RES:
        text = pat.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# ===========================================================================
# TEXT EXTRACTION
# ===========================================================================

def _read_pdf(file_bytes: bytes) -> str:
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                pt = page.extract_text()
                if pt:
                    text += pt + "\n"
    except Exception:
        pass
    return text


def _read_docx(file_bytes: bytes) -> str:
    text = ""
    try:
        d = docx.Document(io.BytesIO(file_bytes))
        for para in d.paragraphs:
            text += para.text + "\n"
    except Exception:
        pass
    return text


def _read_txt(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_text(uploaded_file) -> str:
    """Extract raw text from an uploaded file (PDF / DOCX / TXT)."""
    uploaded_file.seek(0)
    data = uploaded_file.read()
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        return _read_pdf(data)
    if name.endswith(".docx"):
        return _read_docx(data)
    if name.endswith(".txt"):
        return _read_txt(data)
    return ""


# ===========================================================================
# SKILL EXTRACTION  (library-only, no free-form tokens)
# ===========================================================================

def find_skills_in_text(text: str) -> set[str]:
    """
    Return the subset of SKILL_LIBRARY entries found in `text`.
    Checks longest phrases first to prevent partial matches.
    ONLY skills in _ALL_SKILLS can ever be returned.
    """
    tl = text.lower()
    found: set[str] = set()
    for skill in _SKILLS_BY_LENGTH:
        if _SKILL_PATTERNS[skill].search(tl):
            found.add(skill)
    return found


def _skills_section_bounds(lines: list[str]) -> tuple[int, int]:
    """
    Find the line range [start, end) of the skills section.
    Returns (-1, -1) if no skills section detected.
    """
    start = -1
    for i, line in enumerate(lines):
        if _SKILLS_HDR_RE.match(line.strip()):
            start = i
            break
    if start == -1:
        return -1, -1

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped and _OTHER_HDR_RE.match(stripped):
            end = i
            break
    return start, end


def extract_skills_weighted(raw_text: str, target_skills: set[str]) -> dict[str, float]:
    """
    For each skill in `target_skills`, search the resume and assign weight:
      - Found in dedicated skills section → 1.0
      - Found elsewhere in the document   → 0.6
      - Not found                         → excluded from result

    Returns {skill: weight}.
    """
    lines = raw_text.split("\n")
    s, e = _skills_section_bounds(lines)

    sec_lower = " ".join(lines[s:e]).lower() if s != -1 else ""
    full_lower = raw_text.lower()

    matched: dict[str, float] = {}
    for skill in target_skills:
        pat = _SKILL_PATTERNS[skill]
        if sec_lower and pat.search(sec_lower):
            matched[skill] = 1.0
        elif pat.search(full_lower):
            matched[skill] = 0.6
    return matched


# ===========================================================================
# JD FEATURE EXTRACTION  (called once per JD)
# ===========================================================================

def extract_jd_features(raw_text: str) -> dict:
    """
    Parse a JD once. Returns:
      skills         – set of SKILL_LIBRARY skills present in the JD
      required_exp   – years of experience required (0 if unspecified)
    """
    cleaned = clean_text(raw_text)
    skills = find_skills_in_text(cleaned)
    required_exp = _max_years(raw_text)
    return {"skills": skills, "required_exp": required_exp}


def _max_years(text: str) -> float:
    """Return the largest years-of-experience figure found in text."""
    tl = text.lower()
    hits: list[float] = []
    for pat in _EXP_PATTERNS:
        for m in pat.findall(tl):
            try:
                hits.append(float(m))
            except ValueError:
                pass
    return max(hits) if hits else 0.0


# ===========================================================================
# RESUME PARSING
# ===========================================================================

def parse_resume(raw_text: str) -> dict:
    """
    Parse a resume into structured fields.
    Returns: cleaned_text, raw_text, skills (set), experience_years (float).
    """
    cleaned = clean_text(raw_text)
    return {
        "raw_text": raw_text,
        "cleaned_text": cleaned,
        "skills": find_skills_in_text(cleaned),
        "experience_years": _max_years(raw_text),
    }


# ===========================================================================
# SCORING
# ===========================================================================

def compute_skill_score(
    raw_text: str, jd_skills: set[str]
) -> tuple[float, list[str], list[str]]:
    """
    Skill Score = sum(section-aware weights for matched JD skills)
                  ─────────────────────────────────────────────── × 100
                         total number of JD skills

    Returns (score_0_100, matched_list, missing_list).
    """
    if not jd_skills:
        return 0.0, [], []

    weighted = extract_skills_weighted(raw_text, jd_skills)
    raw_score = sum(weighted.values()) / len(jd_skills)
    score = round(min(raw_score * 100, 100.0), 1)
    matched = sorted(weighted.keys())
    missing = sorted(jd_skills - weighted.keys())
    return score, matched, missing


def compute_education_score(raw_text: str) -> float:
    """
    Scan text for education keywords (highest-level first).
    Return mapped score (0–100); first match wins.
    """
    tl = raw_text.lower()
    for keywords, pts in EDUCATION_DEGREES:
        for kw in keywords:
            # whole-word match to avoid "master" matching "mastercard"
            pat = r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])"
            if re.search(pat, tl):
                return float(pts)
    return 0.0


def compute_experience_score(resume_years: float, required_years: float) -> float:
    """
    resume_years >= required_years → 100
    resume_years < required_years  → proportional (resume / required × 100)
    required_years == 0            → 100 (no requirement specified)
    """
    if required_years <= 0:
        return 100.0
    if resume_years >= required_years:
        return 100.0
    return round((resume_years / required_years) * 100, 1)


def score_resume_against_jd(
    resume: dict, jd_features: dict, weights: dict
) -> dict:
    """
    Composite weighted score for a single (resume, JD) pair.
    All sub-scores are on a 0–100 scale.
    """
    skill_score, matched, missing = compute_skill_score(
        resume["raw_text"], jd_features["skills"]
    )
    edu_score = compute_education_score(resume["raw_text"])
    exp_score = compute_experience_score(
        resume["experience_years"], jd_features["required_exp"]
    )

    total = (
        skill_score * (weights["skills"]     / 100)
        + edu_score  * (weights["education"]  / 100)
        + exp_score  * (weights["experience"] / 100)
    )

    return {
        "total":            round(total, 1),
        "skill_score":      round(skill_score, 1),
        "education_score":  round(edu_score, 1),
        "experience_score": round(exp_score, 1),
        "matched_skills":   matched,
        "missing_skills":   missing,
    }


# ===========================================================================
# CLUSTERING  — one resume → one JD, no duplicates
# ===========================================================================

def cluster_resumes_to_jds(
    resumes: list[dict],
    jd_list: list[dict],
    weights: dict,
    top_n: int,
) -> dict[str, list[dict]]:
    """
    Greedy assignment:
    1. Score every (resume, JD) pair.
    2. Sort all pairs descending by score.
    3. Walk the list: assign each resume to its best available JD.
       Each resume is assigned exactly once.
       Each JD accepts at most `top_n` candidates.

    Returns {jd_name: [{"name": str, "score_data": dict}, ...]} sorted desc.
    """
    # Build full score matrix
    matrix: list[tuple[int, int, float, dict]] = []
    for r_idx, resume in enumerate(resumes):
        for j_idx, jd in enumerate(jd_list):
            sd = score_resume_against_jd(resume, jd["features"], weights)
            matrix.append((r_idx, j_idx, sd["total"], sd))

    matrix.sort(key=lambda x: x[2], reverse=True)

    assigned: set[int] = set()
    slots: dict[str, int] = defaultdict(int)
    result: dict[str, list[dict]] = defaultdict(list)

    for r_idx, j_idx, _, sd in matrix:
        if r_idx in assigned:
            continue
        jd_name = jd_list[j_idx]["name"]
        if slots[jd_name] >= top_n:
            continue
        result[jd_name].append({"name": resumes[r_idx]["name"], "score_data": sd})
        assigned.add(r_idx)
        slots[jd_name] += 1
        if len(assigned) == len(resumes):
            break

    # Sort each bucket descending
    for name in result:
        result[name].sort(key=lambda x: x["score_data"]["total"], reverse=True)

    return dict(result)


# ===========================================================================
# WORD REPORT GENERATION
# ===========================================================================

def _rgb(run, r: int, g: int, b: int) -> None:
    run.font.color.rgb = RGBColor(r, g, b)


def _hr(doc: Document) -> None:
    """Thin grey horizontal rule between candidate blocks."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), "6")
    bot.set(qn("w:space"), "1")
    bot.set(qn("w:color"), "CCCCCC")
    pBdr.append(bot)
    pPr.append(pBdr)


def _label_value(doc: Document, label: str, value: str) -> None:
    p = doc.add_paragraph()
    p.add_run(f"{label}: ").bold = True
    p.add_run(value)
    p.paragraph_format.space_after = Pt(2)


def _bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        try:
            doc.add_paragraph(item, style="List Bullet")
        except Exception:
            p = doc.add_paragraph()
            p.add_run(f"  \u2022 {item}")


def generate_jd_report(jd_name: str, candidates: list[dict]) -> bytes:
    """Build and return a Word (.docx) report for one JD as raw bytes."""
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Inches(1)
        sec.bottom_margin = Inches(1)
        sec.left_margin = Inches(1.2)
        sec.right_margin = Inches(1.2)

    # Title
    title = doc.add_heading(f"Hiring Report \u2014 {jd_name}", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if title.runs:
        _rgb(title.runs[0], 0x1F, 0x45, 0x7C)
    doc.add_paragraph()

    if not candidates:
        p = doc.add_paragraph("No suitable candidates found for this role.")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        s = doc.add_paragraph()
        s.add_run("Total Candidates Selected: ").bold = True
        s.add_run(str(len(candidates)))
        doc.add_paragraph()

        for idx, cand in enumerate(candidates, 1):
            sd = cand["score_data"]

            h = doc.add_heading(f"{idx}. {cand['name']}", level=2)
            if h.runs:
                _rgb(h.runs[0], 0x2E, 0x74, 0xB5)

            sp = doc.add_paragraph()
            sr = sp.add_run(f"Match Score: {sd['total']}%")
            sr.bold = True
            sr.font.size = Pt(13)
            _rgb(sr, 0x37, 0x86, 0x3C)

            doc.add_paragraph().add_run("Score Breakdown:").bold = True
            _label_value(doc, "  Skills",     f"{sd['skill_score']}%")
            _label_value(doc, "  Education",  f"{sd['education_score']}%")
            _label_value(doc, "  Experience", f"{sd['experience_score']}%")
            doc.add_paragraph()

            doc.add_paragraph().add_run("Matched Skills:").bold = True
            if sd["matched_skills"]:
                _bullets(doc, sd["matched_skills"][:30])
            else:
                doc.add_paragraph("  None detected")

            doc.add_paragraph().add_run("Missing Skills:").bold = True
            if sd["missing_skills"]:
                _bullets(doc, sd["missing_skills"][:30])
            else:
                doc.add_paragraph("  None \u2014 all JD skills matched")

            _hr(doc)
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ===========================================================================
# STREAMLIT UI
# ===========================================================================

def main() -> None:
    st.set_page_config(
        page_title="ATS \u2014 Resume Screener",
        page_icon="\U0001f4cb",
        layout="centered",
    )
    st.markdown(
        """
        <style>
        .block-container { max-width: 780px; padding-top: 2rem; padding-bottom: 3rem; }
        h1 { color: #1F457C; margin-bottom: 0.1rem; }
        .upload-label { font-size: 0.85rem; color: #666; margin-bottom: 0.25rem; }
        .section-gap { margin-top: 1.5rem; }
        [data-testid="stSidebar"] { background-color: #f8f9fb; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # SIDEBAR — all configuration controls
    # -----------------------------------------------------------------------
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        st.markdown("---")

        top_n = st.slider("Top N candidates per JD", min_value=1, max_value=20, value=5)

        st.markdown("#### Scoring Weights")
        w_skills = st.slider("Skills %", 0, 100, 60, step=5)
        w_edu    = st.slider("Education %", 0, 100, 20, step=5)
        w_exp    = st.slider("Experience %", 0, 100, 20, step=5)

        total_w = w_skills + w_edu + w_exp
        if total_w != 100:
            st.warning(f"⚠️ Weights total {total_w}% — must sum to 100%.")
        else:
            st.success("✅ Weights sum to 100%")

    # -----------------------------------------------------------------------
    # MAIN PAGE
    # -----------------------------------------------------------------------
    st.title("📄 ATS Resume Screener")
    st.caption("Upload job descriptions and resumes, then generate ranked hiring reports.")

    st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)

    # Upload section — two columns
    col_jd, col_res = st.columns(2)

    with col_jd:
        st.markdown("**Job Descriptions**")
        jd_files = st.file_uploader(
            "Upload JDs (PDF, DOCX, TXT)",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="jd_uploader",
            label_visibility="collapsed",
        )
        if jd_files:
            st.caption(f"✅ {len(jd_files)} JD{'s' if len(jd_files) != 1 else ''} uploaded")

    with col_res:
        st.markdown("**Resumes**")
        resume_files = st.file_uploader(
            "Upload Resumes (PDF, DOCX, TXT)",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="resume_uploader",
            label_visibility="collapsed",
        )
        if resume_files:
            st.caption(f"✅ {len(resume_files)} resume{'s' if len(resume_files) != 1 else ''} uploaded")

    st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)

    # Primary action button
    if st.button("📄 Generate Reports", type="primary", use_container_width=True):
        errors = []
        if not jd_files:
            errors.append("Upload at least one Job Description.")
        if not resume_files:
            errors.append("Upload at least one Resume.")
        if total_w != 100:
            errors.append("Scoring weights in the sidebar must sum to 100%.")
        for e in errors:
            st.error(e)
        if errors:
            return

        weights = {"skills": w_skills, "education": w_edu, "experience": w_exp}

        # Parse JDs
        with st.spinner("Parsing job descriptions…"):
            jd_list = []
            for f in jd_files:
                raw = extract_text(f)
                if not raw.strip():
                    st.warning(f"⚠️ Could not read: {f.name}")
                    continue
                jd_list.append({
                    "name": f.name.rsplit(".", 1)[0],
                    "features": extract_jd_features(raw),
                })

        if not jd_list:
            st.error("No valid JDs parsed.")
            return

        # Parse resumes
        with st.spinner("Parsing resumes…"):
            resume_list = []
            for f in resume_files:
                raw = extract_text(f)
                if not raw.strip():
                    st.warning(f"⚠️ Could not read: {f.name}")
                    continue
                parsed = parse_resume(raw)
                resume_list.append({"name": f.name.rsplit(".", 1)[0], **parsed})

        if not resume_list:
            st.error("No valid resumes parsed.")
            return

        # Score and cluster
        with st.spinner("Scoring and assigning candidates…"):
            assignments = cluster_resumes_to_jds(resume_list, jd_list, weights, top_n)

        # Results Summary
        st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
        st.markdown("### Results Summary")

        for jd in jd_list:
            candidates = assignments.get(jd["name"], [])
            if candidates:
                st.success(f"**{jd['name']}** → {len(candidates)} candidate(s) selected")
            else:
                st.warning(f"**{jd['name']}** → No suitable candidates found")

        # Download section
        any_dl = any(assignments.get(jd["name"]) for jd in jd_list)
        if any_dl:
            st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
            st.markdown("### Download Reports")

            for jd in jd_list:
                candidates = assignments.get(jd["name"], [])
                if not candidates:
                    continue
                report = generate_jd_report(jd["name"], candidates)
                safe = re.sub(r"[^\w\-_]", "_", jd["name"])
                st.download_button(
                    label=f"⬇ Download — {jd['name']}",
                    data=report,
                    file_name=f"{safe}_report.docx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                    use_container_width=True,
                )
        else:
            st.warning("No candidates were assigned to any JD.")


if __name__ == "__main__":
    main()
