"""
Production-Grade ATS (Applicant Tracking System)
Cluster-Based Matching Engine — No AI, No APIs, Fully Deterministic
"""

import streamlit as st
import re
import io
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Optional

# ─── Third-party imports (graceful fallback) ──────────────────────────────────
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from docx import Document as DocxDocument
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — CONFIGURATION & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# Comprehensive skill dictionary grouped by domain
SKILL_DICTIONARY: Dict[str, List[str]] = {
    # Programming Languages
    "programming": [
        "python", "java", "javascript", "typescript", "c++", "c#", "ruby",
        "go", "rust", "kotlin", "swift", "scala", "r", "matlab", "php",
        "perl", "bash", "shell", "powershell", "vba", "dart", "elixir",
        "haskell", "lua", "groovy",
    ],
    # Web & Frontend
    "web_frontend": [
        "html", "css", "react", "angular", "vue", "svelte", "nextjs",
        "nuxtjs", "gatsby", "webpack", "babel", "sass", "less", "bootstrap",
        "tailwind", "jquery", "redux", "graphql", "rest", "ajax",
        "responsive design", "web design",
    ],
    # Backend & APIs
    "web_backend": [
        "django", "flask", "fastapi", "node", "express", "spring", "laravel",
        "rails", "asp.net", "microservices", "api", "rest api", "soap",
        "grpc", "websocket", "oauth",
    ],
    # Data & Analytics
    "data": [
        "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
        "pandas", "numpy", "scipy", "matplotlib", "seaborn", "plotly",
        "tableau", "power bi", "excel", "google sheets", "looker", "metabase",
        "data analysis", "data visualization", "etl", "data pipeline",
        "data modeling", "data warehouse", "data lake",
    ],
    # Machine Learning & AI
    "ml_ai": [
        "machine learning", "deep learning", "nlp", "computer vision",
        "tensorflow", "pytorch", "keras", "scikit-learn", "xgboost",
        "lightgbm", "neural network", "cnn", "rnn", "lstm", "transformer",
        "bert", "gpt", "llm", "rag", "huggingface", "opencv",
        "reinforcement learning", "feature engineering",
    ],
    # Cloud & DevOps
    "cloud_devops": [
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible",
        "jenkins", "gitlab", "github actions", "ci/cd", "linux", "unix",
        "nginx", "apache", "cloudformation", "lambda", "ec2", "s3", "rds",
        "devops", "sre", "monitoring", "prometheus", "grafana",
    ],
    # Databases
    "database": [
        "oracle", "sql server", "sqlite", "cassandra", "dynamodb", "firebase",
        "neo4j", "influxdb", "snowflake", "bigquery", "redshift",
        "database design", "nosql",
    ],
    # Marketing
    "marketing": [
        "seo", "sem", "ppc", "google ads", "facebook ads", "social media",
        "content marketing", "email marketing", "crm", "hubspot", "salesforce",
        "marketo", "digital marketing", "brand management", "copywriting",
        "marketing strategy", "market research", "analytics", "a/b testing",
        "conversion rate", "lead generation", "affiliate marketing",
    ],
    # Finance & Accounting
    "finance": [
        "accounting", "financial modeling", "valuation", "dcf", "excel",
        "bloomberg", "risk management", "portfolio management", "trading",
        "investment banking", "equity research", "financial analysis",
        "budgeting", "forecasting", "p&l", "balance sheet", "audit",
        "taxation", "ifrs", "gaap", "quickbooks", "tally", "erp", "sap",
    ],
    # Design
    "design": [
        "figma", "sketch", "adobe xd", "photoshop", "illustrator",
        "indesign", "after effects", "ui design", "ux design", "ui/ux",
        "wireframing", "prototyping", "user research", "design thinking",
        "typography", "branding", "graphic design", "motion design",
        "interaction design",
    ],
    # Project Management
    "pm": [
        "agile", "scrum", "kanban", "jira", "confluence", "trello",
        "project management", "product management", "roadmap", "sprint",
        "stakeholder management", "pmp", "prince2", "risk assessment",
        "ms project",
    ],
    # Soft Skills & Business
    "business": [
        "leadership", "communication", "teamwork", "problem solving",
        "critical thinking", "negotiation", "presentation", "business analysis",
        "strategy", "consulting", "client management", "vendor management",
        "operations", "supply chain", "logistics",
    ],
    # HR
    "hr": [
        "recruitment", "talent acquisition", "onboarding", "payroll",
        "performance management", "employee relations", "hris",
        "workday", "successfactors", "hr analytics", "compensation",
        "benefits", "training", "learning development",
    ],
}

# Flatten for quick lookup
ALL_SKILLS: Set[str] = {
    skill for domain_skills in SKILL_DICTIONARY.values()
    for skill in domain_skills
}

# Education keywords with hierarchy weights
EDUCATION_KEYWORDS: Dict[str, float] = {
    "phd": 1.0, "doctorate": 1.0, "d.phil": 1.0,
    "mba": 0.9, "master": 0.85, "m.tech": 0.85, "m.sc": 0.85,
    "m.com": 0.8, "mca": 0.8, "me": 0.8, "ms": 0.8,
    "b.tech": 0.75, "be": 0.75, "btech": 0.75, "b.e": 0.75,
    "bca": 0.7, "b.sc": 0.7, "bsc": 0.7, "bachelor": 0.7,
    "b.com": 0.65, "bcom": 0.65, "bba": 0.65,
    "ca": 0.85, "cpa": 0.85, "cfa": 0.85, "acca": 0.8,
    "diploma": 0.5, "certification": 0.45, "certificate": 0.45,
    "12th": 0.3, "10th": 0.2, "high school": 0.25,
    "design": 0.7, "arts": 0.6, "law": 0.75, "llb": 0.75, "llm": 0.85,
    "mbbs": 0.9, "md": 0.9,
}

# Stopwords to filter out
STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare",
    "ought", "used", "that", "this", "these", "those", "i", "we", "you",
    "he", "she", "it", "they", "me", "him", "her", "us", "them", "my",
    "your", "his", "its", "our", "their", "not", "no", "nor", "so", "yet",
    "both", "either", "neither", "each", "every", "all", "any", "few",
    "more", "most", "other", "some", "such", "than", "too", "very",
    "just", "as", "if", "while", "because", "since", "although", "though",
    "also", "about", "after", "before", "between", "into", "through",
    "during", "above", "below", "up", "down", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "what", "which", "who", "whom", "whose",
    "work", "experience", "years", "year", "role", "position", "company",
    "team", "good", "strong", "knowledge", "understanding", "ability",
    "skills", "skill", "required", "requirement", "qualification",
    "preferred", "plus", "must", "responsible", "responsibility",
    "looking", "seeking", "candidate", "candidates", "applicant",
    "will", "joining", "join", "work", "working",
}

# Similarity weights (must sum to 1.0)
WEIGHTS = {
    "skills": 0.50,
    "keywords": 0.20,
    "education": 0.15,
    "experience": 0.15,
}

# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from a PDF file using pdfplumber."""
    if not PDF_SUPPORT:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except Exception:
        return ""


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from a DOCX file using python-docx."""
    if not DOCX_SUPPORT:
        return ""
    try:
        doc = DocxDocument(io.BytesIO(file_bytes))
        paragraphs = [para.text for para in doc.paragraphs]
        # Also grab table content
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    paragraphs.append(cell.text)
        return "\n".join(paragraphs)
    except Exception:
        return ""


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Route to correct extractor based on file extension."""
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        text = extract_text_from_pdf(file_bytes)
    elif ext in ("docx", "doc"):
        text = extract_text_from_docx(file_bytes)
    else:
        # Attempt decode as plain text
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
    return text


def normalize_text(text: str) -> str:
    """Lowercase, remove special chars, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s\+\#\./]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — FEATURE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_skills(text: str) -> Set[str]:
    """
    Match skills from the predefined dictionary against the document text.
    Uses word-boundary matching for accuracy.
    """
    found: Set[str] = set()
    for skill in ALL_SKILLS:
        # Build pattern: handle multi-word skills and special chars (c++, c#)
        escaped = re.escape(skill)
        pattern = r"(?<!\w)" + escaped + r"(?!\w)"
        if re.search(pattern, text):
            found.add(skill)
    return found


def extract_keywords(text: str) -> Set[str]:
    """
    Extract meaningful tokens after stopword removal.
    Keep tokens of length ≥ 3.
    """
    tokens = text.split()
    keywords: Set[str] = set()
    for token in tokens:
        clean = re.sub(r"[^\w]", "", token)
        if len(clean) >= 3 and clean not in STOPWORDS and not clean.isdigit():
            keywords.add(clean)
    return keywords


def extract_education(text: str) -> Tuple[float, List[str]]:
    """
    Detect education level from text.
    Returns (highest_weight, list_of_matched_terms).
    """
    matched = []
    max_weight = 0.0
    for edu_key, weight in EDUCATION_KEYWORDS.items():
        # Allow flexible matching (e.g., "btech" matches "b.tech")
        pattern = r"(?<!\w)" + re.escape(edu_key) + r"(?!\w)"
        if re.search(pattern, text):
            matched.append(edu_key)
            if weight > max_weight:
                max_weight = weight
    return max_weight, matched


def extract_experience_years(text: str) -> float:
    """
    Extract years of experience from text using regex patterns.
    Returns maximum found value.
    """
    patterns = [
        r"(\d+)\+?\s*(?:to\s*\d+\s*)?years?\s*(?:of\s*)?(?:experience|exp|work)",
        r"experience\s*(?:of\s*)?(\d+)\+?\s*years?",
        r"(\d+)\+?\s*years?\s*(?:of\s*)?(?:relevant|total|work|industry)",
        r"minimum\s*(?:of\s*)?(\d+)\+?\s*years?",
        r"atleast\s*(\d+)\+?\s*years?",
        r"(\d+)\s*-\s*(\d+)\s*years?",   # range: capture max
    ]
    values: List[float] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            # For range pattern, take the larger value
            groups = [g for g in match.groups() if g is not None]
            for g in groups:
                try:
                    values.append(float(g))
                except ValueError:
                    pass
    return max(values) if values else 0.0


def extract_features(text: str) -> Dict:
    """
    Master feature extractor. Runs all sub-extractors on normalized text.
    Returns a structured feature dict used for similarity computation.
    """
    norm = normalize_text(text)
    skills = extract_skills(norm)
    keywords = extract_keywords(norm)
    edu_weight, edu_matches = extract_education(norm)
    exp_years = extract_experience_years(norm)

    return {
        "raw_text": norm,
        "skills": skills,
        "keywords": keywords - skills,  # avoid double-counting skills in keywords
        "education_weight": edu_weight,
        "education_matches": edu_matches,
        "experience_years": exp_years,
    }

# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — SIMILARITY COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

def skill_similarity(jd_skills: Set[str], resume_skills: Set[str]) -> float:
    """
    Jaccard-style: intersection / |JD skills|.
    Rewards covering what the JD needs rather than raw overlap.
    """
    if not jd_skills:
        return 0.0
    intersection = jd_skills & resume_skills
    return len(intersection) / len(jd_skills)


def keyword_similarity(jd_kw: Set[str], resume_kw: Set[str]) -> float:
    """
    Overlap ratio: how many JD keywords appear in the resume.
    """
    if not jd_kw:
        return 0.0
    intersection = jd_kw & resume_kw
    return len(intersection) / len(jd_kw)


def education_similarity(jd_edu: float, resume_edu: float) -> float:
    """
    Compare education level weights.
    Full mark if resume >= JD level, partial if within 0.2, else 0.
    """
    if jd_edu == 0.0:
        return 1.0  # JD doesn't specify — no penalty
    if resume_edu >= jd_edu:
        return 1.0
    gap = jd_edu - resume_edu
    if gap <= 0.2:
        return 0.5
    return 0.0


def experience_similarity(jd_exp: float, resume_exp: float) -> float:
    """
    Normalized difference score.
    score = max(0, 1 - |JD_exp - Resume_exp| / JD_exp)
    If JD requires 0 years, full score for everyone.
    """
    if jd_exp == 0.0:
        return 1.0
    diff = abs(jd_exp - resume_exp)
    score = max(0.0, 1.0 - diff / jd_exp)
    return score


def compute_similarity(jd_features: Dict, resume_features: Dict) -> Dict:
    """
    Compute weighted similarity between a resume and a JD.
    Returns individual component scores and final weighted score.
    """
    s_skill = skill_similarity(jd_features["skills"], resume_features["skills"])
    s_kw = keyword_similarity(jd_features["keywords"], resume_features["keywords"])
    s_edu = education_similarity(
        jd_features["education_weight"], resume_features["education_weight"]
    )
    s_exp = experience_similarity(
        jd_features["experience_years"], resume_features["experience_years"]
    )

    final = (
        WEIGHTS["skills"] * s_skill
        + WEIGHTS["keywords"] * s_kw
        + WEIGHTS["education"] * s_edu
        + WEIGHTS["experience"] * s_exp
    )

    return {
        "final": round(final * 100, 2),
        "skill_score": round(s_skill * 100, 2),
        "keyword_score": round(s_kw * 100, 2),
        "education_score": round(s_edu * 100, 2),
        "experience_score": round(s_exp * 100, 2),
        "matched_skills": list(jd_features["skills"] & resume_features["skills"]),
        "missing_skills": list(jd_features["skills"] - resume_features["skills"]),
    }

# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — CLUSTER-BASED MATCHING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def build_match_matrix(
    jd_features_list: List[Dict],
    resume_features_list: List[Dict],
) -> List[List[Dict]]:
    """
    Build NxM matrix: matrix[i][j] = similarity(resume_i, jd_j).
    Precomputed once for efficiency.
    """
    matrix = []
    for res_feat in resume_features_list:
        row = [compute_similarity(jd_feat, res_feat) for jd_feat in jd_features_list]
        matrix.append(row)
    return matrix


def assign_clusters(
    match_matrix: List[List[Dict]],
    resume_names: List[str],
    jd_names: List[str],
) -> Dict[str, List[Dict]]:
    """
    CLUSTER ASSIGNMENT:
    Each resume is assigned to exactly one JD (the one with max score).
    Returns a dict: { jd_name -> list of {candidate, scores, breakdown} }
    """
    clusters: Dict[str, List[Dict]] = defaultdict(list)

    for i, res_name in enumerate(resume_names):
        scores_per_jd = match_matrix[i]
        # Find JD index with maximum final score
        best_jd_idx = max(range(len(jd_names)), key=lambda j: scores_per_jd[j]["final"])
        best_score_detail = scores_per_jd[best_jd_idx]

        clusters[jd_names[best_jd_idx]].append({
            "candidate": res_name,
            "final_score": best_score_detail["final"],
            "skill_score": best_score_detail["skill_score"],
            "keyword_score": best_score_detail["keyword_score"],
            "education_score": best_score_detail["education_score"],
            "experience_score": best_score_detail["experience_score"],
            "matched_skills": best_score_detail["matched_skills"],
            "missing_skills": best_score_detail["missing_skills"],
            # Store all JD scores for the matrix display
            "all_scores": {
                jd_names[j]: scores_per_jd[j]["final"]
                for j in range(len(jd_names))
            },
        })

    # Sort each cluster by final score descending
    for jd_name in clusters:
        clusters[jd_name].sort(key=lambda x: x["final_score"], reverse=True)

    return dict(clusters)

# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

def setup_page():
    """Configure Streamlit page with custom styling."""
    st.set_page_config(
        page_title="ATS Cluster Engine",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600;700&display=swap');

    :root {
        --bg: #0d0f14;
        --surface: #161921;
        --surface2: #1e222d;
        --border: #2a2f3d;
        --accent: #00d4ff;
        --accent2: #7c3aed;
        --accent3: #10b981;
        --warn: #f59e0b;
        --danger: #ef4444;
        --text: #e2e8f0;
        --muted: #64748b;
        --mono: 'Space Mono', monospace;
        --sans: 'DM Sans', sans-serif;
    }

    html, body, [class*="css"] {
        font-family: var(--sans);
        background: var(--bg);
        color: var(--text);
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
    }
    [data-testid="stSidebar"] * { color: var(--text) !important; }

    /* Hide default Streamlit chrome */
    #MainMenu, footer, header { visibility: hidden; }

    /* Uploader */
    [data-testid="stFileUploader"] {
        background: var(--surface2);
        border: 1px dashed var(--border);
        border-radius: 10px;
        padding: 10px;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: var(--accent);
    }

    /* Buttons */
    .stButton > button {
        font-family: var(--mono) !important;
        background: linear-gradient(135deg, var(--accent2), var(--accent)) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 12px 32px !important;
        font-size: 0.9rem !important;
        letter-spacing: 0.05em !important;
        font-weight: 700 !important;
        transition: all 0.2s !important;
        width: 100%;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0, 212, 255, 0.25) !important;
    }

    /* Sliders */
    [data-testid="stSlider"] > div > div {
        color: var(--accent) !important;
    }

    /* Score cards */
    .score-card {
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
        transition: border-color 0.2s;
    }
    .score-card:hover { border-color: var(--accent); }

    .rank-badge {
        font-family: var(--mono);
        background: var(--accent2);
        color: white;
        border-radius: 50%;
        width: 28px; height: 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 700;
        margin-right: 8px;
    }

    .jd-header {
        font-family: var(--mono);
        background: linear-gradient(90deg, var(--surface2), transparent);
        border-left: 3px solid var(--accent);
        padding: 12px 16px;
        border-radius: 4px;
        margin: 20px 0 12px 0;
        font-size: 0.95rem;
        letter-spacing: 0.08em;
        color: var(--accent);
    }

    .metric-pill {
        display: inline-block;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 0.72rem;
        font-family: var(--mono);
        margin: 2px;
        color: var(--muted);
    }

    .skill-tag {
        display: inline-block;
        background: rgba(0, 212, 255, 0.1);
        border: 1px solid rgba(0, 212, 255, 0.3);
        color: var(--accent);
        border-radius: 4px;
        padding: 1px 8px;
        font-size: 0.7rem;
        font-family: var(--mono);
        margin: 2px;
    }

    .missing-tag {
        display: inline-block;
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.25);
        color: #f87171;
        border-radius: 4px;
        padding: 1px 8px;
        font-size: 0.7rem;
        font-family: var(--mono);
        margin: 2px;
    }

    .progress-bar-outer {
        background: var(--border);
        border-radius: 4px;
        height: 6px;
        width: 100%;
        overflow: hidden;
    }
    .progress-bar-inner {
        height: 100%;
        border-radius: 4px;
        background: linear-gradient(90deg, var(--accent2), var(--accent));
        transition: width 0.4s ease;
    }

    /* Matrix table */
    .matrix-table {
        width: 100%;
        border-collapse: collapse;
        font-family: var(--mono);
        font-size: 0.78rem;
    }
    .matrix-table th {
        background: var(--surface2);
        color: var(--accent);
        padding: 8px 12px;
        text-align: left;
        border-bottom: 2px solid var(--border);
    }
    .matrix-table td {
        padding: 7px 12px;
        border-bottom: 1px solid var(--border);
        color: var(--text);
    }
    .matrix-table tr:hover td { background: var(--surface2); }
    .cell-high { color: var(--accent3) !important; font-weight: 700; }
    .cell-mid { color: var(--warn) !important; }
    .cell-low { color: var(--muted) !important; }

    .hero-title {
        font-family: var(--mono);
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #ffffff 0%, var(--accent) 60%, var(--accent2) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.02em;
        line-height: 1.1;
    }

    .stat-box {
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
    .stat-val {
        font-family: var(--mono);
        font-size: 2rem;
        font-weight: 700;
        color: var(--accent);
    }
    .stat-label {
        font-size: 0.75rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    div[data-testid="stExpander"] {
        background: var(--surface2) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
    }

    </style>
    """, unsafe_allow_html=True)


def render_score_bar(score: float, label: str, color: str = "var(--accent)"):
    """Render a labeled progress bar for a score component."""
    bar_style = f"width:{score:.1f}%; background: linear-gradient(90deg, {color}88, {color});"
    st.markdown(f"""
    <div style="margin:4px 0;">
      <div style="display:flex; justify-content:space-between; font-size:0.72rem; margin-bottom:3px;">
        <span style="color:var(--muted); font-family:var(--mono);">{label}</span>
        <span style="color:{color}; font-family:var(--mono); font-weight:700;">{score:.1f}%</span>
      </div>
      <div class="progress-bar-outer">
        <div class="progress-bar-inner" style="{bar_style}"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_candidate_card(rank: int, candidate: Dict, show_details: bool):
    """Render a single candidate result card."""
    score = candidate["final_score"]
    color = (
        "var(--accent3)" if score >= 70
        else "var(--warn)" if score >= 40
        else "var(--danger)"
    )

    with st.container():
        col_a, col_b = st.columns([4, 1])
        with col_a:
            st.markdown(
                f'<span class="rank-badge">#{rank}</span>'
                f'<span style="font-weight:600; font-size:0.95rem;">{candidate["candidate"]}</span>',
                unsafe_allow_html=True,
            )
        with col_b:
            st.markdown(
                f'<div style="text-align:right; font-family:var(--mono); font-size:1.3rem;'
                f'font-weight:700; color:{color};">{score:.1f}%</div>',
                unsafe_allow_html=True,
            )

        render_score_bar(candidate["skill_score"], "Skills (50%)", "var(--accent)")
        render_score_bar(candidate["keyword_score"], "Keywords (20%)", "var(--accent2)")
        render_score_bar(candidate["education_score"], "Education (15%)", "var(--accent3)")
        render_score_bar(candidate["experience_score"], "Experience (15%)", "var(--warn)")

        if show_details:
            # Matched skills
            if candidate["matched_skills"]:
                tags = " ".join(
                    f'<span class="skill-tag">{s}</span>'
                    for s in sorted(candidate["matched_skills"])
                )
                st.markdown(
                    f'<div style="margin-top:8px;"><span style="font-size:0.7rem;'
                    f'color:var(--muted); font-family:var(--mono);">✓ MATCHED </span>{tags}</div>',
                    unsafe_allow_html=True,
                )
            # Missing skills
            if candidate["missing_skills"]:
                tags = " ".join(
                    f'<span class="missing-tag">{s}</span>'
                    for s in sorted(candidate["missing_skills"])[:8]
                )
                st.markdown(
                    f'<div style="margin-top:4px;"><span style="font-size:0.7rem;'
                    f'color:var(--muted); font-family:var(--mono);">✗ MISSING </span>{tags}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<hr style='border-color:var(--border); margin:10px 0;'>", unsafe_allow_html=True)


def render_match_matrix(
    match_matrix: List[List[Dict]],
    resume_names: List[str],
    jd_names: List[str],
):
    """Render the full similarity matrix as an HTML table."""
    header_cells = "".join(
        f'<th title="{jd}">{jd[:18]}{"…" if len(jd) > 18 else ""}</th>'
        for jd in jd_names
    )
    header = f"<tr><th>Candidate</th>{header_cells}<th>Best JD</th></tr>"

    rows = []
    for i, res_name in enumerate(resume_names):
        scores = [match_matrix[i][j]["final"] for j in range(len(jd_names))]
        best_j = scores.index(max(scores))
        cells = ""
        for j, sc in enumerate(scores):
            css = "cell-high" if j == best_j else ("cell-mid" if sc >= 40 else "cell-low")
            bold = "font-weight:700;" if j == best_j else ""
            cells += f'<td class="{css}" style="{bold}">{sc:.0f}%</td>'
        short_name = res_name[:30] + ("…" if len(res_name) > 30 else "")
        best_jd_short = jd_names[best_j][:20]
        rows.append(
            f"<tr><td>{short_name}</td>{cells}"
            f'<td style="color:var(--accent);font-weight:700;">{best_jd_short}</td></tr>'
        )

    html = f"""
    <div style="overflow-x:auto; background:var(--surface); border-radius:10px;
                border:1px solid var(--border); padding:16px; margin-top:12px;">
        <table class="matrix-table">
            <thead>{header}</thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def main():
    setup_page()

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="padding: 32px 0 24px 0;">
        <div class="hero-title">ATS CLUSTER ENGINE</div>
        <div style="color:var(--muted); font-family:var(--mono); font-size:0.8rem;
                    letter-spacing:0.15em; margin-top:6px;">
            DETERMINISTIC · CLUSTER-BASED · EXPLAINABLE MATCHING
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar Controls ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="font-family:var(--mono); font-size:0.7rem; color:var(--accent);
                    letter-spacing:0.15em; margin-bottom:16px;">⚙ CONFIGURATION</div>
        """, unsafe_allow_html=True)

        top_n = st.slider("Top N candidates per JD", min_value=1, max_value=20, value=5)
        show_details = st.toggle("Show skill breakdown", value=True)
        show_matrix = st.toggle("Show match matrix", value=True)

        st.markdown("---")
        st.markdown("""
        <div style="font-family:var(--mono); font-size:0.7rem; color:var(--muted);
                    letter-spacing:0.1em;">SCORE WEIGHTS</div>
        """, unsafe_allow_html=True)

        for k, v in WEIGHTS.items():
            st.markdown(
                f'<div style="display:flex; justify-content:space-between; '
                f'font-size:0.75rem; padding:3px 0;">'
                f'<span style="color:var(--muted);">{k.capitalize()}</span>'
                f'<span style="font-family:var(--mono); color:var(--accent);">{int(v*100)}%</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("""
        <div style="font-size:0.7rem; color:var(--muted); font-family:var(--mono);">
        Supported: PDF · DOCX<br>
        Algorithm: Cluster-Based Jaccard<br>
        No AI · No APIs · Deterministic
        </div>
        """, unsafe_allow_html=True)

    # ── File Upload Area ──────────────────────────────────────────────────────
    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
        <div style="font-family:var(--mono); font-size:0.75rem; color:var(--accent);
                    letter-spacing:0.12em; margin-bottom:8px;">📋 JOB DESCRIPTIONS</div>
        """, unsafe_allow_html=True)
        jd_files = st.file_uploader(
            "Upload JD files",
            type=["pdf", "docx"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="jd_upload",
        )
        if jd_files:
            st.markdown(
                f'<div style="font-size:0.75rem; color:var(--accent3); '
                f'font-family:var(--mono);">✓ {len(jd_files)} JD(s) loaded</div>',
                unsafe_allow_html=True,
            )

    with col2:
        st.markdown("""
        <div style="font-family:var(--mono); font-size:0.75rem; color:var(--accent);
                    letter-spacing:0.12em; margin-bottom:8px;">📄 RESUMES</div>
        """, unsafe_allow_html=True)
        resume_files = st.file_uploader(
            "Upload Resume files",
            type=["pdf", "docx"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="resume_upload",
        )
        if resume_files:
            st.markdown(
                f'<div style="font-size:0.75rem; color:var(--accent3); '
                f'font-family:var(--mono);">✓ {len(resume_files)} resume(s) loaded</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    analyze_clicked = st.button("⚡ RUN CLUSTER ANALYSIS", use_container_width=True)

    # ── Analysis ──────────────────────────────────────────────────────────────
    if analyze_clicked:
        if not jd_files:
            st.error("Please upload at least one Job Description.")
            return
        if not resume_files:
            st.error("Please upload at least one Resume.")
            return

        # ── Step 1: Extract & Preprocess JDs ──────────────────────────────
        with st.spinner("Parsing Job Descriptions…"):
            jd_features_list: List[Dict] = []
            jd_names: List[str] = []
            jd_raw_texts: List[str] = []

            for jd_file in jd_files:
                raw = extract_text(jd_file.read(), jd_file.name)
                jd_raw_texts.append(raw)
                feats = extract_features(raw)
                jd_features_list.append(feats)
                # Use filename (without extension) as JD label
                label = jd_file.name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
                jd_names.append(label)

        # ── Step 2: Extract & Preprocess Resumes ──────────────────────────
        with st.spinner("Parsing Resumes…"):
            resume_features_list: List[Dict] = []
            resume_names: List[str] = []

            for res_file in resume_files:
                raw = extract_text(res_file.read(), res_file.name)
                feats = extract_features(raw)
                resume_features_list.append(feats)
                resume_names.append(res_file.name)

        # ── Step 3: Build Match Matrix ─────────────────────────────────────
        with st.spinner("Computing similarity matrix…"):
            match_matrix = build_match_matrix(jd_features_list, resume_features_list)

        # ── Step 4: Cluster Assignment ─────────────────────────────────────
        clusters = assign_clusters(match_matrix, resume_names, jd_names)

        # ── Summary Stats ──────────────────────────────────────────────────
        total_assigned = sum(len(v) for v in clusters.values())
        jds_with_candidates = len([v for v in clusters.values() if v])
        avg_top_score = (
            sum(v[0]["final_score"] for v in clusters.values() if v) / jds_with_candidates
            if jds_with_candidates else 0
        )

        st.markdown("<br>", unsafe_allow_html=True)
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.markdown(
                f'<div class="stat-box"><div class="stat-val">{len(jd_names)}</div>'
                f'<div class="stat-label">Job Descriptions</div></div>',
                unsafe_allow_html=True,
            )
        with sc2:
            st.markdown(
                f'<div class="stat-box"><div class="stat-val">{len(resume_names)}</div>'
                f'<div class="stat-label">Resumes Analyzed</div></div>',
                unsafe_allow_html=True,
            )
        with sc3:
            st.markdown(
                f'<div class="stat-box"><div class="stat-val">{jds_with_candidates}</div>'
                f'<div class="stat-label">JDs With Matches</div></div>',
                unsafe_allow_html=True,
            )
        with sc4:
            st.markdown(
                f'<div class="stat-box"><div class="stat-val">{avg_top_score:.0f}%</div>'
                f'<div class="stat-label">Avg Top Score</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Match Matrix ───────────────────────────────────────────────────
        if show_matrix:
            with st.expander("📊 Full Match Matrix (All Resumes × All JDs)", expanded=False):
                render_match_matrix(match_matrix, resume_names, jd_names)

        # ── JD-wise Results ────────────────────────────────────────────────
        st.markdown("""
        <div style="font-family:var(--mono); font-size:0.75rem; color:var(--accent);
                    letter-spacing:0.15em; margin:24px 0 8px 0;">
        ── CLUSTER RESULTS ─────────────────────────────────
        </div>
        """, unsafe_allow_html=True)

        for jd_name in jd_names:
            candidates = clusters.get(jd_name, [])

            # JD header
            count_label = f"{len(candidates)} candidate(s) assigned"
            st.markdown(
                f'<div class="jd-header">🎯 {jd_name.upper()}'
                f'<span style="color:var(--muted); font-size:0.75rem; margin-left:16px;">'
                f'{count_label}</span></div>',
                unsafe_allow_html=True,
            )

            # JD feature summary
            jd_idx = jd_names.index(jd_name)
            jd_feat = jd_features_list[jd_idx]

            col_feat1, col_feat2 = st.columns(2)
            with col_feat1:
                if jd_feat["skills"]:
                    skill_tags = " ".join(
                        f'<span class="metric-pill">{s}</span>'
                        for s in sorted(jd_feat["skills"])[:12]
                    )
                    st.markdown(
                        f'<div style="font-size:0.7rem; color:var(--muted); '
                        f'font-family:var(--mono); margin-bottom:4px;">JD SKILLS DETECTED</div>'
                        f'{skill_tags}',
                        unsafe_allow_html=True,
                    )
            with col_feat2:
                edu = jd_feat["education_matches"]
                exp = jd_feat["experience_years"]
                st.markdown(
                    f'<span class="metric-pill">Education: {", ".join(edu[:3]) if edu else "Not specified"}</span>'
                    f'<span class="metric-pill">Experience: {exp:.0f}+ yrs</span>',
                    unsafe_allow_html=True,
                )

            if not candidates:
                st.markdown(
                    '<div style="color:var(--muted); font-size:0.8rem; padding:12px 0; '
                    'font-family:var(--mono);">No candidates were assigned to this JD cluster.</div>',
                    unsafe_allow_html=True,
                )
            else:
                top_candidates = candidates[:top_n]
                for rank, cand in enumerate(top_candidates, 1):
                    render_candidate_card(rank, cand, show_details)

            st.markdown("<br>", unsafe_allow_html=True)

        # ── Unmatched JDs ──────────────────────────────────────────────────
        empty_jds = [jd for jd in jd_names if not clusters.get(jd)]
        if empty_jds:
            st.warning(
                f"⚠ {len(empty_jds)} JD(s) received no candidates: "
                + ", ".join(empty_jds)
            )

        # ── JD Feature Inspector ───────────────────────────────────────────
        with st.expander("🔍 JD Feature Inspector", expanded=False):
            for jd_name, jd_feat in zip(jd_names, jd_features_list):
                st.markdown(f"**{jd_name}**")
                ic1, ic2, ic3, ic4 = st.columns(4)
                ic1.metric("Skills Found", len(jd_feat["skills"]))
                ic2.metric("Keywords", len(jd_feat["keywords"]))
                ic3.metric(
                    "Education",
                    jd_feat["education_matches"][0] if jd_feat["education_matches"] else "—",
                )
                ic4.metric("Exp Required", f"{jd_feat['experience_years']:.0f} yrs")
                st.markdown("---")

    else:
        # Landing state
        st.markdown("""
        <div style="text-align:center; padding:60px 0; color:var(--muted);">
            <div style="font-size:3rem; margin-bottom:16px;">🎯</div>
            <div style="font-family:var(--mono); font-size:0.85rem; letter-spacing:0.1em;">
                Upload JDs and Resumes, then click RUN CLUSTER ANALYSIS
            </div>
            <div style="font-size:0.75rem; margin-top:12px; max-width:480px;
                        margin-left:auto; margin-right:auto; line-height:1.6;">
                Each resume is assigned to exactly one JD using cluster-based
                similarity. Scoring uses Skills (50%), Keywords (20%),
                Education (15%), and Experience (15%).
            </div>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
