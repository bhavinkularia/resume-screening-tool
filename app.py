import io
import os
import re
import anthropic
import streamlit as st
import pdfplumber
import docx
from docx import Document

# ================================
# TEXT EXTRACTION
# ================================

def extract_text(uploaded_file):
    uploaded_file.seek(0)
    data = uploaded_file.read()
    name = uploaded_file.name.lower()

    try:
        if name.endswith(".pdf"):
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join([p.extract_text() or "" for p in pdf.pages])
        elif name.endswith(".docx"):
            d = docx.Document(io.BytesIO(data))
            return "\n".join([p.text for p in d.paragraphs])
        elif name.endswith(".txt"):
            return data.decode("utf-8", errors="ignore")
    except:
        return ""

    return ""


# ================================
# NAME EXTRACTION
# ================================

def extract_candidate_name(text, fallback="Unknown"):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:10]:
        if 2 <= len(line.split()) <= 4 and line.replace(" ", "").isalpha():
            return line.title()
    return fallback


# ================================
# CLAUDE META EXTRACTION
# ================================

META_PROMPT = """\
Extract the following from the resume:

1. Total Experience → return in:
   - decimal years
   - AND "X years Y months" format

2. Highest Education:
   - Example: "B.Com", "MBA Finance", "MSc Data Science"

Resume:
{resume}

OUTPUT:
EXPERIENCE_YEARS: <number>
EXPERIENCE_DISPLAY: <text>
EDUCATION: <text>
"""

def extract_meta(resume_text):
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": META_PROMPT.format(resume=resume_text[:3000])}],
        )

        raw = msg.content[0].text

        exp_years = 0
        exp_display = "Not specified"
        edu = "Not specified"

        for line in raw.splitlines():
            if "EXPERIENCE_YEARS" in line:
                exp_years = float(re.findall(r"\d+\.?\d*", line)[0])
            elif "EXPERIENCE_DISPLAY" in line:
                exp_display = line.split(":")[1].strip()
            elif "EDUCATION" in line:
                edu = line.split(":")[1].strip()

        return exp_years, exp_display, edu

    except:
        return 0, "Not specified", "Not specified"


# ================================
# CLAUDE REASONING ENGINE
# ================================

EVAL_PROMPT = """\
You are a senior hiring manager.

Evaluate this candidate with deep reasoning — not keyword matching.

JOB DESCRIPTION:
{jd}

RESUME:
{resume}

HINTS:
Experience: {exp}
Education: {edu}

RULES:
- Infer skills from experience
- Do NOT mark obvious things as missing
- Think: what has this person been doing for X years?
- No contradictions

OUTPUT:

Name: <name>

Experience: <X years Y months>
Education: <highest degree>

Insights:

Strengths:
- <point>
- <point>

Gaps:
- <point>
- <point>
"""

def evaluate_candidate(jd_text, resume_text, name, exp, edu):
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        prompt = EVAL_PROMPT.format(
            jd=jd_text[:2000],
            resume=resume_text[:4000],
            exp=exp,
            edu=edu,
        )

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )

        return msg.content[0].text

    except:
        return f"""
Name: {name}

Experience: {exp}
Education: {edu}

Insights:

Strengths:
- Relevant background

Gaps:
- Evaluation unavailable
"""


# ================================
# REPORT GENERATION
# ================================

def generate_report(jd_name, jd_text, candidates):
    doc = Document()
    doc.add_heading(f"Hiring Report — {jd_name}", 0)

    for i, cand in enumerate(candidates, 1):
        doc.add_heading(f"{i}. {cand['name']}", 2)

        result = evaluate_candidate(
            jd_text,
            cand["text"],
            cand["name"],
            cand["exp"],
            cand["edu"],
        )

        doc.add_paragraph(result)
        doc.add_paragraph("-" * 50)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ================================
# STREAMLIT UI
# ================================

def main():
    st.title("AI Hiring Evaluator")

    jd_file = st.file_uploader("Upload JD", type=["pdf", "docx", "txt"])
    resume_files = st.file_uploader("Upload Resumes", accept_multiple_files=True)

    if st.button("Evaluate"):
        if not jd_file or not resume_files:
            st.error("Upload JD and resumes")
            return

        jd_text = extract_text(jd_file)

        candidates = []

        for f in resume_files:
            text = extract_text(f)
            name = extract_candidate_name(text, f.name)

            exp_years, exp_display, edu = extract_meta(text)

            candidates.append({
                "name": name,
                "text": text,
                "exp": exp_display,
                "edu": edu
            })

        report = generate_report(jd_file.name, jd_text, candidates)

        st.download_button(
            "Download Report",
            report,
            file_name="report.docx"
        )


if __name__ == "__main__":
    main()
