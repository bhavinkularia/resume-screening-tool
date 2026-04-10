"""
ATS - Applicant Tracking System
Production-ready, rule-based resume screening with Word report generation.
"""

import io
import re
import zipfile
from collections import defaultdict

import streamlit as st
import pdfplumber
import docx
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILLS_SECTION_KEYWORDS = {
    "skills", "technical skills", "core competencies",
    "technologies", "tech stack", "tools", "expertise",
    "competencies", "proficiencies"
}

EDUCATION_KEYWORDS = {
    "b.tech", "b.e", "be ", "btech", "bachelor", "b.sc", "bsc",
    "m.tech", "mtech", "m.e", "me ", "master", "mba", "m.sc", "msc",
    "phd", "ph.d", "doctorate", "diploma", "associate",
    "10th", "12th", "ssc", "hsc", "intermediate", "matric",
    "computer science", "information technology", "engineering",
    "mathematics", "statistics", "data science", "machine learning",
}

EDUCATION_SCORE_MAP = {
    "phd": 100, "ph.d": 100, "doctorate": 100,
    "m.tech": 90, "mtech": 90, "m.e": 90, "master": 90,
    "mba": 85, "m.sc": 85, "msc": 85,
    "b.tech": 75, "btech": 75, "b.e": 75, "be ": 75, "bachelor": 75,
    "b.sc": 70, "bsc": 70,
    "diploma": 55, "associate": 55,
    "12th": 40, "hsc": 40, "intermediate": 40,
    "10th": 25, "ssc": 25, "matric": 25,
}

EXPERIENCE_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp)",
    r"experience\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*\+?\s*years?",
    r"(\d+(?:\.\d+)?)\s*\+?\s*yrs?\s+(?:of\s+)?(?:experience|exp)",
    r"(\d+(?:\.\d+)?)\s*\+?\s*years?",
]

# ---------------------------------------------------------------------------
# Text Extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from a PDF file."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception:
        pass
    return text


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from a DOCX file."""
    text = ""
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception:
        pass
    return text


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Decode plain text file."""
    try:
        return file_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_text(uploaded_file) -> str:
    """Route to appropriate extractor based on file type."""
    file_bytes = uploaded_file.read()
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    elif name.endswith(".txt"):
        return extract_text_from_txt(file_bytes)
    return ""


# ---------------------------------------------------------------------------
# Parsing Helpers
# ---------------------------------------------------------------------------

def tokenize_skills(text: str) -> set:
    """
    Extract candidate skill tokens from free-form text.
    Returns lowercase stripped tokens (1–4 words each).
    """
    tokens = set()
    text_lower = text.lower()

    # Multi-word phrases (2–4 words) using sliding window over words
    words = re.findall(r"[a-z0-9#+.\-/]+", text_lower)
    for n in range(1, 5):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i : i + n])
            if len(phrase) > 1:
                tokens.add(phrase)

    return tokens


def detect_skills_section_bounds(lines: list[str]) -> tuple[int, int]:
    """
    Return (start_line, end_line) of the skills section, or (-1, -1) if absent.
    The section ends when another section header is detected.
    """
    section_header_re = re.compile(
        r"^\s*(skills|technical skills|core competencies|technologies|"
        r"tech stack|tools|expertise|competencies|proficiencies)\s*[:\-]?\s*$",
        re.IGNORECASE,
    )
    # Detect any generic section header (ALL CAPS or Title Case short lines)
    generic_header_re = re.compile(r"^\s*[A-Z][A-Za-z\s]{2,30}\s*[:\-]?\s*$")

    start = -1
    for i, line in enumerate(lines):
        if section_header_re.match(line):
            start = i
            break

    if start == -1:
        return -1, -1

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if generic_header_re.match(stripped) and not section_header_re.match(stripped):
            end = i
            break

    return start, end


def extract_skills_with_weights(text: str, jd_skills: set) -> dict[str, float]:
    """
    For each JD skill, determine if it appears in the resume and at what weight.
    Skills section → weight 1.0; elsewhere → weight 0.6.
    Returns {skill: weight} for matched skills only.
    """
    lines = text.split("\n")
    sec_start, sec_end = detect_skills_section_bounds(lines)

    skills_section_text = ""
    if sec_start != -1:
        skills_section_text = " ".join(lines[sec_start:sec_end]).lower()

    full_text_lower = text.lower()
    matched = {}

    for skill in jd_skills:
        skill_lower = skill.lower()
        # Check skills section first (higher weight)
        if skills_section_text and skill_lower in skills_section_text:
            matched[skill] = 1.0
        elif skill_lower in full_text_lower:
            matched[skill] = 0.6

    return matched


def score_education(text: str) -> float:
    """
    Rule-based education score (0–100).
    Takes the highest matching qualification found in text.
    """
    text_lower = text.lower()
    best = 0
    for keyword, score in EDUCATION_SCORE_MAP.items():
        if keyword in text_lower:
            best = max(best, score)
    return best


def score_experience(text: str) -> float:
    """
    Extract years of experience from text and map to 0–100 score.
    """
    text_lower = text.lower()
    years_found = []

    for pattern in EXPERIENCE_PATTERNS:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            try:
                years_found.append(float(m))
            except ValueError:
                pass

    if not years_found:
        return 0.0

    years = max(years_found)

    # Map years → score (capped at 15 years = 100)
    if years >= 15:
        return 100.0
    elif years >= 10:
        return 90.0
    elif years >= 7:
        return 80.0
    elif years >= 5:
        return 70.0
    elif years >= 3:
        return 55.0
    elif years >= 1:
        return 35.0
    else:
        return 10.0


# ---------------------------------------------------------------------------
# JD Feature Extraction
# ---------------------------------------------------------------------------

def extract_jd_features(jd_text: str) -> dict:
    """
    Extract skills required by a JD.
    Returns a dict with 'skills' (set of strings).
    """
    tokens = tokenize_skills(jd_text)
    # Filter to plausible skill tokens (remove very short/generic ones)
    skills = {t for t in tokens if 2 < len(t) <= 40}
    return {"skills": skills}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_resume_against_jd(
    resume_text: str,
    jd_features: dict,
    weights: dict,
) -> dict:
    """
    Compute the composite score of a resume against a JD.

    Returns:
        {
            "total": float (0–100),
            "skill_score": float,
            "education_score": float,
            "experience_score": float,
            "matched_skills": list[str],
            "missing_skills": list[str],
        }
    """
    jd_skills = jd_features["skills"]

    # --- Skill scoring with section-aware weighting ---
    matched_weighted = extract_skills_with_weights(resume_text, jd_skills)

    if jd_skills:
        # Each skill contributes proportionally; max possible = len(jd_skills) * 1.0
        raw_skill_score = sum(matched_weighted.values()) / len(jd_skills)
        skill_score = min(raw_skill_score * 100, 100.0)
    else:
        skill_score = 0.0

    matched_skills = sorted(matched_weighted.keys())
    missing_skills = sorted(jd_skills - set(matched_weighted.keys()))

    # --- Education & Experience ---
    education_score = score_education(resume_text)
    experience_score = score_experience(resume_text)

    # --- Weighted total ---
    w_skill = weights["skills"] / 100
    w_edu = weights["education"] / 100
    w_exp = weights["experience"] / 100

    total = (
        skill_score * w_skill
        + education_score * w_edu
        + experience_score * w_exp
    )

    return {
        "total": round(total, 1),
        "skill_score": round(skill_score, 1),
        "education_score": round(education_score, 1),
        "experience_score": round(experience_score, 1),
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
    }


# ---------------------------------------------------------------------------
# Clustering: assign each resume to its best-fit JD
# ---------------------------------------------------------------------------

def cluster_resumes_to_jds(
    resumes: list[dict],
    jd_list: list[dict],
    weights: dict,
    top_n: int,
) -> dict[str, list[dict]]:
    """
    Assign each resume to exactly one JD (best match, no duplication).
    Returns {jd_name: [candidate_result, ...]} sorted by score desc, capped at top_n.

    Each candidate_result = {
        "name": str,
        "score_data": dict,
    }
    """
    # Step 1: Score every resume against every JD
    all_scores = []  # (resume_idx, jd_idx, score)
    for r_idx, resume in enumerate(resumes):
        for j_idx, jd in enumerate(jd_list):
            score_data = score_resume_against_jd(
                resume["text"], jd["features"], weights
            )
            all_scores.append((r_idx, j_idx, score_data["total"], score_data))

    # Step 2: Sort by score descending for greedy assignment
    all_scores.sort(key=lambda x: x[2], reverse=True)

    assigned_resumes = set()
    jd_assignments = defaultdict(list)

    for r_idx, j_idx, score, score_data in all_scores:
        if r_idx in assigned_resumes:
            continue
        jd_name = jd_list[j_idx]["name"]
        # Only assign if this JD still has capacity
        if len(jd_assignments[jd_name]) < top_n:
            jd_assignments[jd_name].append({
                "name": resumes[r_idx]["name"],
                "score_data": score_data,
            })
            assigned_resumes.add(r_idx)

        if len(assigned_resumes) == len(resumes):
            break

    # Sort each JD's candidates by score descending
    for jd_name in jd_assignments:
        jd_assignments[jd_name].sort(
            key=lambda x: x["score_data"]["total"], reverse=True
        )

    return dict(jd_assignments)


# ---------------------------------------------------------------------------
# Word Report Generation
# ---------------------------------------------------------------------------

def _add_heading(doc: Document, text: str, level: int = 1, color=None):
    """Add a styled heading paragraph."""
    heading = doc.add_heading(text, level=level)
    run = heading.runs[0] if heading.runs else heading.add_run(text)
    if color:
        run.font.color.rgb = RGBColor(*color)
    return heading


def _add_horizontal_rule(doc: Document):
    """Add a thin horizontal line using paragraph border."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "CCCCCC")
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


def _add_score_row(doc: Document, label: str, value: str):
    """Add a label: value line in a paragraph."""
    p = doc.add_paragraph()
    run_label = p.add_run(f"{label}: ")
    run_label.bold = True
    p.add_run(value)
    return p


def _add_bullet_list(doc: Document, items: list[str], style: str = "List Bullet"):
    """Add items as bullet list paragraphs."""
    for item in items:
        try:
            doc.add_paragraph(item, style=style)
        except Exception:
            p = doc.add_paragraph()
            p.add_run(f"• {item}")


def generate_jd_report(jd_name: str, candidates: list[dict]) -> bytes:
    """
    Generate a Word document report for a single JD.
    Returns bytes of the .docx file.
    """
    doc = Document()

    # --- Page margins ---
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    # --- Document title ---
    title = doc.add_heading(f"Hiring Report — {jd_name}", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if title.runs:
        title.runs[0].font.color.rgb = RGBColor(0x1F, 0x45, 0x7C)

    doc.add_paragraph()  # spacer

    if not candidates:
        p = doc.add_paragraph("No suitable candidates found for this role.")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        summary_para = doc.add_paragraph()
        summary_para.add_run(f"Total Candidates Selected: ").bold = True
        summary_para.add_run(str(len(candidates)))
        doc.add_paragraph()

        for idx, candidate in enumerate(candidates, 1):
            name = candidate["name"]
            sd = candidate["score_data"]

            # Candidate header
            cand_heading = doc.add_heading(f"{idx}. {name}", level=2)
            if cand_heading.runs:
                cand_heading.runs[0].font.color.rgb = RGBColor(0x2E, 0x74, 0xB5)

            # Match score (prominent)
            score_para = doc.add_paragraph()
            score_run = score_para.add_run(f"Match Score: {sd['total']}%")
            score_run.bold = True
            score_run.font.size = Pt(13)
            score_run.font.color.rgb = RGBColor(0x37, 0x86, 0x3C)

            # Score breakdown
            breakdown_heading = doc.add_paragraph()
            breakdown_heading.add_run("Score Breakdown:").bold = True

            _add_score_row(doc, "  Skills", f"{sd['skill_score']}%")
            _add_score_row(doc, "  Education", f"{sd['education_score']}%")
            _add_score_row(doc, "  Experience", f"{sd['experience_score']}%")

            doc.add_paragraph()  # spacer

            # Matched skills
            matched_heading = doc.add_paragraph()
            matched_heading.add_run("Matched Skills:").bold = True

            if sd["matched_skills"]:
                # Show up to 20 most relevant matched skills
                _add_bullet_list(doc, sd["matched_skills"][:20])
            else:
                doc.add_paragraph("  None detected")

            # Missing skills
            missing_heading = doc.add_paragraph()
            missing_heading.add_run("Missing Skills:").bold = True

            if sd["missing_skills"]:
                # Show up to 20 most critical missing skills
                _add_bullet_list(doc, sd["missing_skills"][:20])
            else:
                doc.add_paragraph("  None — all JD skills matched")

            _add_horizontal_rule(doc)
            doc.add_paragraph()  # spacer between candidates

    # --- Save to bytes ---
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="ATS — Resume Screener",
        page_icon="📋",
        layout="centered",
    )

    # Minimal CSS
    st.markdown(
        """
        <style>
        .block-container { max-width: 780px; padding-top: 2rem; }
        h1 { color: #1F457C; }
        .stAlert { border-radius: 6px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("📋 ATS Resume Screener")
    st.caption("Upload job descriptions and resumes. Get ranked Word reports per JD.")

    st.divider()

    # ── 1. Upload Job Descriptions ──────────────────────────────────────────
    st.subheader("1 · Job Descriptions")
    jd_files = st.file_uploader(
        "Upload JDs (PDF, DOCX, or TXT)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="jd_uploader",
    )

    # ── 2. Upload Resumes ───────────────────────────────────────────────────
    st.subheader("2 · Resumes")
    resume_files = st.file_uploader(
        "Upload Resumes (PDF, DOCX, or TXT)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="resume_uploader",
    )

    st.divider()

    # ── 3. Top N Slider ─────────────────────────────────────────────────────
    st.subheader("3 · Top Candidates per JD")
    top_n = st.slider("Select top N candidates per JD", 1, 20, 5)

    st.divider()

    # ── 4. Scoring Weights ──────────────────────────────────────────────────
    st.subheader("4 · Scoring Weights")
    st.caption("Adjust the importance of each dimension. Total must equal 100.")

    col1, col2, col3 = st.columns(3)
    with col1:
        w_skills = st.slider("Skills %", 0, 100, 60, step=5)
    with col2:
        w_education = st.slider("Education %", 0, 100, 20, step=5)
    with col3:
        w_experience = st.slider("Experience %", 0, 100, 20, step=5)

    total_weight = w_skills + w_education + w_experience
    weight_ok = total_weight == 100

    if total_weight != 100:
        st.warning(f"⚠️ Weights total {total_weight}%. Please adjust so they sum to 100%.")
    else:
        st.success("✅ Weights sum to 100%")

    st.divider()

    # ── 5. Generate Button ──────────────────────────────────────────────────
    generate = st.button("📄 Generate Hiring Report", type="primary", use_container_width=True)

    if generate:
        # Validation
        if not jd_files:
            st.error("Please upload at least one Job Description.")
            return
        if not resume_files:
            st.error("Please upload at least one Resume.")
            return
        if not weight_ok:
            st.error("Weights must sum to 100% before generating reports.")
            return

        weights = {
            "skills": w_skills,
            "education": w_education,
            "experience": w_experience,
        }

        # ── Parse JDs (once) ────────────────────────────────────────────────
        with st.spinner("Parsing job descriptions…"):
            jd_list = []
            for f in jd_files:
                text = extract_text(f)
                if not text.strip():
                    st.warning(f"⚠️ Could not extract text from JD: {f.name}")
                    continue
                name = f.name.rsplit(".", 1)[0]
                features = extract_jd_features(text)
                jd_list.append({"name": name, "text": text, "features": features})

        if not jd_list:
            st.error("No valid JDs could be parsed.")
            return

        # ── Parse Resumes ───────────────────────────────────────────────────
        with st.spinner("Parsing resumes…"):
            resume_list = []
            for f in resume_files:
                text = extract_text(f)
                if not text.strip():
                    st.warning(f"⚠️ Could not extract text from resume: {f.name}")
                    continue
                name = f.name.rsplit(".", 1)[0]
                resume_list.append({"name": name, "text": text})

        if not resume_list:
            st.error("No valid resumes could be parsed.")
            return

        # ── Cluster & Score ─────────────────────────────────────────────────
        with st.spinner("Scoring and assigning candidates…"):
            assignments = cluster_resumes_to_jds(
                resume_list, jd_list, weights, top_n
            )

        # ── Summary Display ─────────────────────────────────────────────────
        st.divider()
        st.subheader("Results Summary")

        for jd in jd_list:
            candidates = assignments.get(jd["name"], [])
            count = len(candidates)
            if count == 0:
                st.info(f"**{jd['name']}** → No suitable candidates found")
            else:
                st.success(f"**{jd['name']}** → {count} candidate(s) selected")

        # ── Generate & Offer Downloads ──────────────────────────────────────
        st.divider()
        st.subheader("Download Reports")

        any_report = False
        for jd in jd_list:
            candidates = assignments.get(jd["name"], [])
            if not candidates:
                continue

            any_report = True
            report_bytes = generate_jd_report(jd["name"], candidates)
            safe_name = re.sub(r"[^\w\-_]", "_", jd["name"])

            st.download_button(
                label=f"⬇️ Download Report — {jd['name']}",
                data=report_bytes,
                file_name=f"{safe_name}_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )

        if not any_report:
            st.warning("No candidates were assigned to any JD.")


if __name__ == "__main__":
    main()
