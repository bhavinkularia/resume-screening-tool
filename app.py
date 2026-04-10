import streamlit as st
import pdfplumber
import docx
import re
import io
from collections import Counter

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Resume Screener", layout="wide")

# ---------------- SKILL SYSTEM ----------------
SKILL_LIBRARY = {
    "python","java","sql","excel","tableau","power bi","marketing",
    "seo","sem","finance","valuation","accounting","aws","docker",
    "kubernetes","machine learning","data analysis","analytics"
}

# Synonyms mapping (NEW)
SKILL_SYNONYMS = {
    "data analysis": ["analytics","analysis"],
    "marketing": ["branding","campaign","seo","sem"],
    "finance": ["valuation","investment","equity"],
    "machine learning": ["ml","ai"],
}

# ---------------- TEXT EXTRACTION ----------------
def extract_text(file_bytes, filename):
    if filename.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return " ".join([p.extract_text() or "" for p in pdf.pages])
    else:
        doc = docx.Document(io.BytesIO(file_bytes))
        return " ".join([p.text for p in doc.paragraphs])

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text)

# ---------------- FEATURE EXTRACTION ----------------
def extract_skills(text):
    skills = set()

    for skill in SKILL_LIBRARY:
        if skill in text:
            skills.add(skill)

    # Synonym mapping
    for main, syns in SKILL_SYNONYMS.items():
        if any(s in text for s in syns):
            skills.add(main)

    return skills

def extract_keywords(text):
    tokens = re.findall(r'\b[a-z]{3,}\b', text)
    freq = Counter(tokens)
    return set([w for w, _ in freq.most_common(50)])  # limit keywords

def extract_experience(text):
    match = re.findall(r'(\d+)\s*\+?\s*years?', text)
    return max([int(x) for x in match], default=0)

def extract_education(text):
    if "mba" in text:
        return "mba"
    if "btech" in text or "engineer" in text:
        return "btech"
    return "other"

def build_features(text, filename):
    text = normalize(text)
    return {
        "name": filename,
        "skills": extract_skills(text),
        "keywords": extract_keywords(text),
        "experience": extract_experience(text),
        "education": extract_education(text)
    }

# ---------------- SCORING ----------------
def skill_score(jd, res):
    if not jd:
        return 0
    return len(jd & res) / len(jd)

def keyword_score(jd, res):
    if not jd:
        return 0
    return len(jd & res) / len(jd)

def education_score(jd, res):
    return 1 if jd == res else 0.5 if res != "other" else 0

def experience_score(jd, res):
    if res >= jd:
        return 1
    if jd == 0:
        return 0.5
    return res / jd

def compute_score(jd, res):
    s1 = skill_score(jd["skills"], res["skills"])
    s2 = keyword_score(jd["keywords"], res["keywords"])
    s3 = education_score(jd["education"], res["education"])
    s4 = experience_score(jd["experience"], res["experience"])

    total = (
        0.6 * s1 +
        0.05 * s2 +
        0.2 * s3 +
        0.15 * s4
    )

    return round(total * 100, 1)

# ---------------- CLUSTERING ----------------
def assign_candidates(jds, resumes):
    clusters = {jd["name"]: [] for jd in jds}

    for res in resumes:
        scores = {jd["name"]: compute_score(jd, res) for jd in jds}
        best_jd = max(scores, key=scores.get)

        clusters[best_jd].append({
            "name": res["name"],
            "score": scores[best_jd]
        })

    for jd in clusters:
        clusters[jd].sort(key=lambda x: x["score"], reverse=True)

    return clusters

# ---------------- UI ----------------
st.title("🎯 Resume Screening System")

jd_files = st.file_uploader("Upload Job Descriptions", accept_multiple_files=True)
resume_files = st.file_uploader("Upload Resumes", accept_multiple_files=True)

top_n = st.slider("Top candidates per JD", 1, 10, 3)

if st.button("Analyze"):
    if not jd_files or not resume_files:
        st.warning("Upload both JDs and resumes")
    else:
        jd_features = []
        for f in jd_files:
            jd_features.append(build_features(extract_text(f.read(), f.name), f.name))

        resume_features = []
        for f in resume_files:
            resume_features.append(build_features(extract_text(f.read(), f.name), f.name))

        clusters = assign_candidates(jd_features, resume_features)

        for jd, candidates in clusters.items():
            st.subheader(f"📌 {jd}")
            for i, c in enumerate(candidates[:top_n], 1):
                st.write(f"{i}. {c['name']} — {c['score']}%")
