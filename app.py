"""
ATS — AI Hiring System
Claude is the primary evaluator. No keyword scoring. No percentages.
Output: Name · Experience · Education · Strengths · Gaps
"""

import io
import os
import re
from collections import defaultdict

import anthropic
import streamlit as st
import pdfplumber
import docx
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


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
# CANDIDATE NAME — lightweight fallback only
# ===========================================================================

_NAME_EXCLUDE: set[str] = {
    "academic", "education", "profile", "resume", "experience",
    "curriculum", "vitae", "objective", "summary", "contact",
    "phone", "email", "address", "linkedin", "github", "mobile",
    "www", "http", "about", "skills", "overview", "introduction",
}
_NAME_NOISE_RE = re.compile(r"[^a-zA-Z\s]")


def extract_candidate_name(raw_text: str, file_stem: str = "") -> str:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    for line in lines[:15]:
        line = re.sub(r"^[\W_]+", "", line).strip()
        if not line or _NAME_NOISE_RE.search(line):
            continue
        lower = line.lower()
        if any(excl in lower for excl in _NAME_EXCLUDE):
            continue
        words = line.split()
        if not (2 <= len(words) <= 4):
            continue
        if not all(w.isalpha() for w in words):
            continue
        if all(w[0].isupper() for w in words):
            return " ".join(words)

    if file_stem:
        name = re.sub(r"[_\-\.]+", " ", file_stem).strip()
        name = re.sub(r"\s+(pdf|docx|txt)$", "", name, flags=re.I).strip()
        return name.title()

    return "Unknown Candidate"


# ===========================================================================
# BASIC EXPERIENCE HINT — used as a sanity-check hint for Claude only
# ===========================================================================

_EXP_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp\b)", re.I),
    re.compile(r"experience\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*\+?\s*years?", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*yrs?\s+(?:of\s+)?(?:experience|exp\b)", re.I),
]


def _hint_years(text: str) -> float:
    hits: list[float] = []
    for pat in _EXP_PATTERNS:
        for m in pat.findall(text.lower()):
            try:
                hits.append(float(m))
            except ValueError:
                pass
    return max(hits) if hits else 0.0


# ===========================================================================
# RESUME PARSING  — minimal; Claude does the heavy lifting
# ===========================================================================

def parse_resume(raw_text: str, file_stem: str = "") -> dict:
    return {
        "raw_text":       raw_text,
        "candidate_name": extract_candidate_name(raw_text, file_stem),
        "hint_years":     _hint_years(raw_text),
    }


# ===========================================================================
# JD PARSING  — extract raw text + required-experience hint
# ===========================================================================

def parse_jd(raw_text: str) -> dict:
    return {
        "raw_text":     raw_text,
        "required_exp": _hint_years(raw_text),
    }


# ===========================================================================
# CLAUDE — PRIMARY EVALUATOR
# One call per candidate. Full JD + full resume text.
# ===========================================================================

_EVAL_PROMPT = """\
You are a senior hiring manager evaluating a candidate for a role.
Think like an experienced recruiter, NOT a keyword-matching system.

=== JOB DESCRIPTION ===
{jd_text}

=== CANDIDATE RESUME ===
{resume_text}

=== HINTS (may be noisy — use as sanity check only) ===
Rule-based experience estimate: {hint_years} years
Extracted name: {candidate_name}

=== YOUR TASK ===
1. Read the resume holistically. Understand what this person has actually done.
2. Infer experience depth — not just years, but ownership, scale, and complexity.
3. Identify the single highest education qualification.
4. Evaluate strengths and gaps relative to this specific JD.

=== CRITICAL RULES ===
- Do NOT rely on keyword presence alone. Infer skills from projects and experience.
- Do NOT mark something as a gap if it is clearly implied by the candidate's background.
- Distinguish basic exposure from deep ownership.
- Gaps must reflect: lack of depth, lack of ownership, or lack of domain relevance.
- NEVER contradict yourself (do not list something as both a strength and a gap).
- Be realistic: what would someone doing this work for X years actually know?
- If the resume is weak or thin, produce fewer bullets — do NOT pad with generic lines.
- No fluff. No softening language. Recruiter voice: direct and specific.

=== OUTPUT FORMAT (STRICT — no extra text, no headers outside this structure) ===
Name: <full name or "Unknown Candidate">
Experience: <X years Y months, or "Not specified">
Education: <highest qualification, e.g. "B.Tech in Computer Science" or "Not specified">
Insights:
Strengths:
- <point>
- <point>
Gaps:
- <point>
- <point>

Rules for Insights:
- 1 to 4 bullet points per section (do not force 4 if there is nothing to say)
- No percentages, no scores, no mention of matched/missing skills as lists
- No generic statements ("good communicator", "team player") unless directly evidenced
"""


def evaluate_candidate_with_claude(
    jd_text: str,
    resume_text: str,
    candidate_name: str,
    hint_years: float,
) -> dict:
    """
    Primary AI evaluation. Returns:
      name, experience, education, strengths (list), gaps (list)
    Falls back gracefully on API error.
    """
    fallback = {
        "name":       candidate_name or "Unknown Candidate",
        "experience": "Not specified",
        "education":  "Not specified",
        "strengths":  ["Candidate submitted for review."],
        "gaps":       ["Full evaluation unavailable — please review manually."],
    }

    prompt = _EVAL_PROMPT.format(
        jd_text=jd_text[:6000].strip(),
        resume_text=resume_text[:6000].strip(),
        hint_years=round(hint_years, 1) if hint_years else "unknown",
        candidate_name=candidate_name,
    )

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_eval_response(msg.content[0].text.strip(), fallback)
    except Exception:
        return fallback


def _parse_eval_response(raw: str, fallback: dict) -> dict:
    result = {
        "name":       fallback["name"],
        "experience": "Not specified",
        "education":  "Not specified",
        "strengths":  [],
        "gaps":       [],
    }
    current_section: str | None = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()

        if lower.startswith("name:"):
            val = line.split(":", 1)[1].strip()
            if val:
                result["name"] = val
        elif lower.startswith("experience:"):
            val = line.split(":", 1)[1].strip()
            if val and val.lower() not in ("none", "not specified", ""):
                result["experience"] = val
        elif lower.startswith("education:"):
            val = line.split(":", 1)[1].strip()
            if val and val.lower() not in ("none", "not specified", ""):
                result["education"] = val
        elif lower.startswith("strengths"):
            current_section = "strengths"
        elif lower.startswith("gaps"):
            current_section = "gaps"
        elif lower.startswith("insights"):
            pass  # section header — skip
        elif line.startswith(("-", "*", "•")) and current_section:
            text = line.lstrip("-*• ").strip()
            if text and len(result[current_section]) < 4:
                result[current_section].append(text)

    # Ensure at least one bullet per section
    if not result["strengths"]:
        result["strengths"] = fallback["strengths"]
    if not result["gaps"]:
        result["gaps"] = fallback["gaps"]

    return result


# ===========================================================================
# CANDIDATE ASSIGNMENT — order resumes to JDs by experience hint proximity
# Simple heuristic: match candidates to JD with closest required_exp.
# Claude handles real evaluation; this only decides routing.
# ===========================================================================

def assign_resumes_to_jds(
    resumes: list[dict],
    jd_list: list[dict],
    top_n: int,
) -> dict[str, list[dict]]:
    """
    Assign each resume to exactly one JD (the best experience-hint match).
    Returns {jd_name: [resume_dict, ...]} with at most top_n per JD.
    """
    # Score every (resume, JD) pair by experience proximity
    matrix: list[tuple[int, int, float]] = []
    for r_idx, resume in enumerate(resumes):
        for j_idx, jd in enumerate(jd_list):
            req = jd["features"]["required_exp"]
            cand = resume["hint_years"]
            # Prefer candidates at or slightly above requirement; penalise shortfall
            delta = cand - req
            score = -abs(delta) if delta >= 0 else delta * 2  # shortfall penalised more
            matrix.append((r_idx, j_idx, score))

    matrix.sort(key=lambda x: x[2], reverse=True)

    assigned: set[int] = set()
    slots: dict[str, int] = defaultdict(int)
    result: dict[str, list[dict]] = defaultdict(list)

    for r_idx, j_idx, _ in matrix:
        if r_idx in assigned:
            continue
        jd_name = jd_list[j_idx]["name"]
        if slots[jd_name] >= top_n:
            continue
        result[jd_name].append(resumes[r_idx])
        assigned.add(r_idx)
        slots[jd_name] += 1

    return dict(result)


# ===========================================================================
# WORD REPORT GENERATION
# ===========================================================================

def _rgb(run, r: int, g: int, b: int) -> None:
    run.font.color.rgb = RGBColor(r, g, b)


def _hr(doc: Document) -> None:
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


def _set_cell_bg(cell, hex_color: str) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _set_cell_border(cell) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "CCCCCC")
        tcBorders.append(el)
    tcPr.append(tcBorders)


def _profile_block(doc: Document, experience: str, education: str) -> None:
    """Simple 2-row table: Experience | Education."""
    rows_data = [("Experience", experience), ("Education", education)]
    table = doc.add_table(rows=1 + len(rows_data), cols=2)
    table.style = "Table Grid"

    hdr_cells = table.rows[0].cells
    for cell, text in zip(hdr_cells, ("Field", "Details")):
        _set_cell_bg(cell, "1F457C")
        _set_cell_border(cell)
        p = cell.paragraphs[0]
        p.clear()
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for i, (label, value) in enumerate(rows_data, 1):
        row_cells = table.rows[i].cells
        bg = "F9FAFB" if i % 2 == 0 else "FFFFFF"
        for cell in row_cells:
            _set_cell_bg(cell, bg)
            _set_cell_border(cell)

        lp = row_cells[0].paragraphs[0]
        lp.clear()
        lr = lp.add_run(label)
        lr.bold = True
        lr.font.size = Pt(10)

        vp = row_cells[1].paragraphs[0]
        vp.clear()
        vr = vp.add_run(value)
        vr.font.size = Pt(10)


def _insights_block(doc: Document, strengths: list[str], gaps: list[str]) -> None:
    """Two-column Strengths / Gaps table with bullet points."""
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"

    hdr_cells = table.rows[0].cells
    for cell, label in zip(hdr_cells, ("Strengths", "Gaps")):
        _set_cell_bg(cell, "1F457C")
        _set_cell_border(cell)
        p = cell.paragraphs[0]
        p.clear()
        run = p.add_run(label)
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    content_row = table.add_row()
    s_cell = content_row.cells[0]
    g_cell = content_row.cells[1]
    _set_cell_bg(s_cell, "F0FFF4")
    _set_cell_bg(g_cell, "FFF8F0")
    _set_cell_border(s_cell)
    _set_cell_border(g_cell)

    def _fill(cell, items: list[str]) -> None:
        first = True
        for item in items:
            p = cell.paragraphs[0] if first else cell.add_paragraph()
            first = False
            p.clear()
            run = p.add_run(f"• {item}")
            run.font.size = Pt(9)
            p.paragraph_format.space_after = Pt(3)

    _fill(s_cell, strengths)
    _fill(g_cell, gaps)


def generate_jd_report(
    jd_name: str,
    jd_text: str,
    candidates: list[dict],
) -> bytes:
    """Build a Word report for one JD. One Claude call per candidate."""
    doc = Document()
    for sec in doc.sections:
        sec.top_margin    = Inches(1)
        sec.bottom_margin = Inches(1)
        sec.left_margin   = Inches(1.2)
        sec.right_margin  = Inches(1.2)

    # Report title
    title = doc.add_heading(f"Hiring Report — {jd_name}", level=0)
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
            file_stem      = cand["name"]
            candidate_name = cand.get("candidate_name", file_stem)
            resume_text    = cand["raw_text"]
            hint_years     = cand.get("hint_years", 0.0)

            # Claude evaluation
            evaluation = evaluate_candidate_with_claude(
                jd_text=jd_text,
                resume_text=resume_text,
                candidate_name=candidate_name,
                hint_years=hint_years,
            )

            # Candidate heading
            h = doc.add_heading(f"{idx}. {evaluation['name']}", level=2)
            if h.runs:
                _rgb(h.runs[0], 0x2E, 0x74, 0xB5)

            fn_p = doc.add_paragraph()
            fn_r = fn_p.add_run(f"File: {file_stem}")
            fn_r.font.size = Pt(9)
            fn_r.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
            fn_p.paragraph_format.space_after = Pt(6)

            # Profile table
            _profile_block(doc, evaluation["experience"], evaluation["education"])
            doc.add_paragraph()

            # Insights table
            ins_hdr = doc.add_paragraph()
            ins_hdr.add_run("Insights").bold = True
            ins_hdr.paragraph_format.space_after = Pt(4)

            _insights_block(doc, evaluation["strengths"], evaluation["gaps"])

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
        page_title="AI Hiring System",
        page_icon="📋",
        layout="centered",
    )

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 760px;
            padding-top: 2.5rem;
            padding-bottom: 3.5rem;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid #2a2d36;
        }
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 2rem;
        }
        .sb-card {
            background: #0f1115;
            border: 1px solid #2a2d36;
            border-radius: 10px;
            padding: 1rem 1rem 0.25rem 1rem;
            margin-bottom: 0.9rem;
        }
        .sb-label {
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: #555d6e;
            margin-bottom: 0.6rem;
        }
        .up-panel {
            background: #1a1d24;
            border: 1px solid #2a2d36;
            border-radius: 10px;
            padding: 1.1rem 1.1rem 0.5rem 1.1rem;
            min-height: 170px;
        }
        .up-label {
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.07em;
            text-transform: uppercase;
            color: #6b7280;
            margin-bottom: 0.5rem;
        }
        .up-badge {
            display: inline-block;
            background: #0d2b1f;
            color: #4ade80;
            border: 1px solid #166534;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.15rem 0.7rem;
            margin-top: 0.35rem;
        }
        .gap-sm { margin-top: 0.9rem; }
        .gap-md { margin-top: 1.6rem; }
        button[kind="primary"] {
            border-radius: 8px !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em !important;
        }
        [data-testid="stDownloadButton"] button {
            border-radius: 8px !important;
            font-weight: 500 !important;
        }
        h1 { font-size: 1.65rem !important; font-weight: 700 !important; margin-bottom: 0.15rem !important; }
        h3 { font-weight: 600 !important; margin-top: 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        st.markdown("<div class='gap-sm'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='sb-card'><div class='sb-label'>Top Candidates</div>",
            unsafe_allow_html=True,
        )
        top_n = st.slider("Per JD", min_value=1, max_value=20, value=5)
        st.markdown("</div>", unsafe_allow_html=True)

    # Main page
    st.title("📄 AI Hiring System")
    st.markdown(
        "<p style='color:#6b7280; font-size:0.93rem; margin-top:0.05rem; margin-bottom:0;'>"
        "Upload job descriptions and resumes — Claude evaluates each candidate like a hiring manager."
        "</p>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='gap-md'></div>", unsafe_allow_html=True)

    col_jd, col_res = st.columns(2, gap="medium")

    with col_jd:
        st.markdown(
            "<div class='up-panel'><div class='up-label'>📋 Job Descriptions</div>",
            unsafe_allow_html=True,
        )
        jd_files = st.file_uploader(
            "Upload JDs",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="jd_uploader",
            label_visibility="collapsed",
        )
        if jd_files:
            n = len(jd_files)
            st.markdown(
                f"<div class='up-badge'>✅ {n} JD{'s' if n != 1 else ''} uploaded</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    with col_res:
        st.markdown(
            "<div class='up-panel'><div class='up-label'>📄 Resumes</div>",
            unsafe_allow_html=True,
        )
        resume_files = st.file_uploader(
            "Upload Resumes",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="resume_uploader",
            label_visibility="collapsed",
        )
        if resume_files:
            n = len(resume_files)
            st.markdown(
                f"<div class='up-badge'>✅ {n} Resume{'s' if n != 1 else ''} uploaded</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='gap-md'></div>", unsafe_allow_html=True)

    if st.button("📄 Generate Reports", type="primary", use_container_width=True):
        errors = []
        if not jd_files:
            errors.append("Upload at least one Job Description.")
        if not resume_files:
            errors.append("Upload at least one Resume.")
        for e in errors:
            st.error(e)
        if errors:
            return

        with st.spinner("Parsing job descriptions…"):
            jd_list = []
            for f in jd_files:
                raw = extract_text(f)
                if not raw.strip():
                    st.warning(f"⚠️ Could not read: {f.name}")
                    continue
                jd_list.append({
                    "name":     f.name.rsplit(".", 1)[0],
                    "raw_text": raw,
                    "features": {"required_exp": _hint_years(raw)},
                })

        if not jd_list:
            st.error("No valid JDs parsed.")
            return

        with st.spinner("Parsing resumes…"):
            resume_list = []
            for f in resume_files:
                raw = extract_text(f)
                if not raw.strip():
                    st.warning(f"⚠️ Could not read: {f.name}")
                    continue
                file_stem = f.name.rsplit(".", 1)[0]
                parsed = parse_resume(raw, file_stem)
                resume_list.append({"name": file_stem, **parsed})

        if not resume_list:
            st.error("No valid resumes parsed.")
            return

        with st.spinner("Assigning candidates to roles…"):
            assignments = assign_resumes_to_jds(resume_list, jd_list, top_n)

        st.markdown("<div class='gap-md'></div>", unsafe_allow_html=True)
        st.markdown("### Results Summary")

        for jd in jd_list:
            candidates = assignments.get(jd["name"], [])
            if candidates:
                st.success(f"**{jd['name']}** → {len(candidates)} candidate(s) selected")
            else:
                st.warning(f"**{jd['name']}** → No suitable candidates found")

        any_dl = any(assignments.get(jd["name"]) for jd in jd_list)
        if any_dl:
            st.markdown("<div class='gap-md'></div>", unsafe_allow_html=True)
            st.markdown("### Download Reports")
            for jd in jd_list:
                candidates = assignments.get(jd["name"], [])
                if not candidates:
                    continue
                with st.spinner(f"Claude is evaluating candidates for {jd['name']}…"):
                    report = generate_jd_report(jd["name"], jd["raw_text"], candidates)
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
