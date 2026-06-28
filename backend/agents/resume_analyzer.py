# backend/agents/resume_analyzer.py
import json
import re
import hashlib
import logging
import PyPDF2
from langchain.prompts import ChatPromptTemplate
from core.singletons import get_llm, get_skills_retriever, get_cache, call_gemini_async
from utils.ats_scorer import calculate_real_ats_score

logger = logging.getLogger(__name__)

def extract_pdf_text(file_path: str) -> str:
    """Extract text once and cache by file path."""
    cache = get_cache()
    cache_key = f"pdf_text:{file_path}"
    if cache_key in cache:
        return cache[cache_key]

    text = ""
    try:
        import fitz
        doc = fitz.open(file_path)
        text = " ".join(page.get_text("text") or "" for page in doc)
        doc.close()
    except Exception as e:
        logger.warning("PyMuPDF extraction failed, trying PyPDF2: %s", e)
        try:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                text = " ".join(
                    page.extract_text() or ""
                    for page in reader.pages
                )
        except Exception as e2:
            text = f"[PDF extraction failed: {e2}]"

    cache[cache_key] = text
    return text


async def analyze_resume(file_path: str, user_id: str = "anonymous", progress_callback=None) -> dict:
    """
    Analyzes resume text using Gemini and a skills retriever.
    Supports progress_callback for streaming.
    """
    def emit(msg: str):
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    emit("Extracting text from your resume PDF...")
    resume_text = extract_pdf_text(file_path)

    # Use cache by content hash
    content_hash = hashlib.md5(f"{file_path}".encode()).hexdigest()
    cache_key = f"analysis:{content_hash}"
    cache = get_cache()

    if cache_key in cache:
        emit("⚡ Resume analysis cache hit")
        return cache[cache_key]

    # Calculate real ATS score deterministically
    emit("Scanning resume layout and formatting...")
    ats_data = calculate_real_ats_score(resume_text, "")
    real_ats_score = ats_data["ats_score"]

    # Truncate to first 2500 chars for speed
    resume_truncated = resume_text[:2500]

    emit("Retrieving relevant skills context from knowledge base...")
    retriever = get_skills_retriever(k=3)
    try:
        docs = retriever.get_relevant_documents(resume_truncated[:500])
        skills_context = " ".join(d.page_content[:200] for d in docs)
    except Exception:
        skills_context = "Python, JavaScript, React, FastAPI, Machine Learning, LangChain"

    emit("Analyzing resume with Gemini AI...")
    try:
        formatted_prompt = f"""
You are an expert resume analyst. A deterministic ATS scanner has already scored this resume.
Your job is to provide QUALITATIVE feedback only — do NOT invent or change the ATS score.

DETERMINISTIC ATS SCORE (use this exactly): {real_ats_score}/100
Score breakdown: {ats_data['score_breakdown']}
Missing keywords: {ats_data['missing_keywords'][:10]}
Missing sections: {ats_data['missing_sections']}
Issues found: {ats_data['feedback']}

Resume text:
{resume_truncated}

Provide:
1. overall_score: integer 0-100 (your holistic assessment of resume quality)
2. ats_score: integer — USE EXACTLY {real_ats_score} (do not change this)
3. skills_found: list of skills you can identify
4. skill_gaps: list of important skills missing for a tech role  
5. suggestions: 3-5 specific, actionable bullet points to improve the resume
6. experience_level: "junior" | "mid" | "senior"
7. summary: 2-sentence honest assessment
8. sections_detected: list of detected sections
9. strengths: list of resume strengths
10. keywords_missing: list of missing keywords

Return ONLY valid JSON, no markdown.
"""
        raw_output = await call_gemini_async(formatted_prompt)
        cleaned = re.sub(r"```json|```", "", raw_output).strip()
        parsed = json.loads(cleaned)
        parsed["ats_breakdown"] = ats_data["score_breakdown"]
        parsed["feedback"] = ats_data["feedback"]
        parsed["grade"] = ats_data["grade"]
        parsed["found_keywords"] = ats_data["found_keywords"]
        parsed["missing_keywords"] = ats_data["missing_keywords"]
        parsed["missing_sections"] = ats_data["missing_sections"]
        parsed["resume_text"] = resume_text  # store for rewriter
        cache[cache_key] = parsed
        emit("Analysis complete!")
        return parsed
    except Exception as e:
        logger.error("Gemini analysis failed: %s", e)
        fallback = {
            "skills_found": [],
            "skill_gaps": [],
            "experience_level": "junior",
            "overall_score": 50,
            "ats_score": 50,
            "sections_detected": [],
            "suggestions": ["Could not parse resume. Ensure PDF is text-based."],
            "strengths": ["Contact info present"],
            "keywords_missing": [],
            "format_issues": [],
            "resume_text": resume_text,
            "error": str(e)
        }
        return fallback


STRONG_ACTION_VERBS = [
    "engineered", "architected", "built", "developed", "implemented", "deployed",
    "designed", "optimized", "automated", "integrated", "launched", "led",
    "managed", "created", "delivered", "improved", "reduced", "increased",
    "streamlined", "established", "coordinated", "executed", "analyzed",
    "configured", "maintained", "migrated", "scaled", "researched", "published",
    "trained", "mentored", "collaborated", "spearheaded", "accelerated"
]

STANDARD_SECTIONS = [
    "experience", "education", "skills", "projects", "certifications",
    "achievements", "summary", "objective", "publications", "awards"
]

def calculate_real_ats_score(resume_text: str, job_description: str = "") -> dict:
    """
    Calculate a real ATS score by analyzing the actual extracted PDF text.
    Returns detailed breakdown of every scoring component.
    """
    text_lower = resume_text.lower()
    lines = [l.strip() for l in resume_text.split('\n') if l.strip()]
    bullet_lines = [l for l in lines if l.startswith('•') or l.startswith('-') or l.startswith('*')]

    scores = {}

    # ── 1. SECTION DETECTION (20 points) ─────────────────────────────────
    sections_found = [s for s in STANDARD_SECTIONS if s in text_lower]
    section_score = min(20, len(sections_found) * 4)
    scores["sections"] = {
        "score": section_score,
        "max": 20,
        "found": sections_found,
        "missing": [s for s in ["experience", "education", "skills"] if s not in sections_found]
    }

    # ── 2. KEYWORD MATCH RATE (25 points) ────────────────────────────────
    keyword_score = 0
    matched_keywords = []
    missing_keywords = []

    if job_description:
        stopwords = {"with", "and", "the", "for", "this", "that", "will", "have",
                     "from", "they", "them", "their", "about", "into", "than",
                     "your", "our", "are", "were", "been", "being", "would",
                     "could", "should", "must", "shall", "may", "might", "also"}
        jd_words = set(
            w.lower().strip('.,;:()')
            for w in job_description.split()
            if len(w) > 4 and w.lower() not in stopwords
        )

        for kw in jd_words:
            if kw in text_lower:
                matched_keywords.append(kw)
            else:
                stem = kw[:5]
                if any(stem in word for word in text_lower.split()):
                    matched_keywords.append(kw)
                else:
                    missing_keywords.append(kw)

        match_rate = len(matched_keywords) / max(len(jd_words), 1)
        keyword_score = min(25, int(match_rate * 25))
    else:
        keyword_score = 15  # No JD provided — assume neutral

    scores["keywords"] = {
        "score": keyword_score,
        "max": 25,
        "matched": matched_keywords[:20],
        "missing": missing_keywords[:15],
        "match_rate": round(len(matched_keywords) / max(len(matched_keywords) + len(missing_keywords), 1) * 100, 1)
    }

    # ── 3. ACTION VERB USAGE (15 points) ─────────────────────────────────
    verbs_used = []
    bullets_with_verbs = 0

    for line in bullet_lines:
        content = line.lstrip('•-* ').lower()
        first_word = content.split()[0] if content.split() else ""
        if first_word in STRONG_ACTION_VERBS:
            bullets_with_verbs += 1
            verbs_used.append(first_word)

    if bullet_lines:
        verb_rate = bullets_with_verbs / len(bullet_lines)
        verb_score = min(15, int(verb_rate * 15))
    else:
        verb_score = 5

    scores["action_verbs"] = {
        "score": verb_score,
        "max": 15,
        "bullets_total": len(bullet_lines),
        "bullets_with_strong_verbs": bullets_with_verbs,
        "verbs_used": list(set(verbs_used))[:10]
    }

    # ── 4. QUANTIFICATION (15 points) ────────────────────────────────────
    number_pattern = re.compile(r'\b\d+[\.,]?\d*\s*(%|percent|x|times|ms|gb|tb|k|m|users|requests|seconds|hours|days|weeks|points|stars|million|billion|thousand)?\b', re.IGNORECASE)

    bullets_quantified = 0
    for line in bullet_lines:
        if number_pattern.search(line):
            bullets_quantified += 1

    if bullet_lines:
        quant_rate = bullets_quantified / len(bullet_lines)
        quant_score = min(15, int(quant_rate * 15))
    else:
        quant_score = 3

    scores["quantification"] = {
        "score": quant_score,
        "max": 15,
        "bullets_quantified": bullets_quantified,
        "bullets_total": len(bullet_lines),
        "rate": round(bullets_quantified / max(len(bullet_lines), 1) * 100, 1)
    }

    # ── 5. CONTACT INFO (10 points) ──────────────────────────────────────
    contact_score = 0
    contact_found = []

    if re.search(r'[\w.\-]+@[\w.\-]+\.\w+', resume_text):
        contact_score += 3
        contact_found.append("email")
    if re.search(r'\+?\d[\d\s\-().]{7,}', resume_text):
        contact_score += 3
        contact_found.append("phone")
    if re.search(r'linkedin\.com', text_lower):
        contact_score += 2
        contact_found.append("linkedin")
    if re.search(r'github\.com', text_lower):
        contact_score += 2
        contact_found.append("github")

    scores["contact_info"] = {
        "score": contact_score,
        "max": 10,
        "found": contact_found
    }

    # ── 6. FORMATTING PARSABILITY (15 points) ────────────────────────────
    format_score = 15

    non_ascii = sum(1 for c in resume_text if ord(c) > 127)
    if non_ascii / max(len(resume_text), 1) > 0.05:
        format_score -= 5

    if len(bullet_lines) == 0:
        format_score -= 5

    if len(resume_text) < 300:
        format_score -= 8

    words = resume_text.split()
    unique_words = set(words)
    if len(words) > 0 and len(unique_words) / len(words) < 0.4:
        format_score -= 6

    format_score = max(0, format_score)

    scores["formatting"] = {
        "score": format_score,
        "max": 15,
        "text_length": len(resume_text),
        "bullet_lines": len(bullet_lines),
        "clean_extraction": format_score >= 10
    }

    # ── TOTAL ─────────────────────────────────────────────────────────────
    total = sum(v["score"] for v in scores.values())
    total_max = sum(v["max"] for v in scores.values())

    return {
        "total_score": total,
        "total_max": total_max,
        "percentage": round(total / total_max * 100, 1),
        "breakdown": scores,
        "grade": (
            "Excellent" if total >= 85 else
            "Good" if total >= 70 else
            "Fair" if total >= 55 else
            "Poor"
        ),
        "total": total,
        "ats_score": round(total / total_max * 100, 1),
        "top_issues": _get_top_issues(scores)
    }


def _get_top_issues(scores: dict) -> list:
    issues = []
    labels = {
        "sections": "Add missing resume sections (Experience, Skills, Education)",
        "keywords": "Add more keywords from the job description",
        "action_verbs": "Start bullet points with strong action verbs",
        "quantification": "Add numbers and metrics to bullet points",
        "contact_info": "Add LinkedIn / GitHub / phone number",
        "formatting": "Fix PDF formatting — text may not be parsing cleanly"
    }
    for key, val in scores.items():
        gap = val["max"] - val["score"]
        if gap > 2:
            issues.append({"area": labels.get(key, key), "gap": gap, "score": val["score"], "max": val["max"]})

    issues.sort(key=lambda x: -x["gap"])
    return issues[:3]


def calculate_overall_score(resume_text: str, job_description: str = "") -> dict:
    text_lower = resume_text.lower()
    lines = [l.strip() for l in resume_text.split('\n') if l.strip()]
    bullet_lines = [l for l in lines if l.startswith(('•', '-', '*'))]

    breakdown = {}

    # ── 1. ATS COMPATIBILITY (25 points) ─────────────────────────────────
    ats_result = calculate_real_ats_score(resume_text, job_description)
    ats_component = round(ats_result["percentage"] * 0.25)
    breakdown["ats_compatibility"] = {
        "score": ats_component,
        "max": 25,
        "label": "ATS Compatibility",
        "detail": f"{ats_result['percentage']}% keyword & structure match"
    }

    # ── 2. CONTENT QUALITY (20 points) ───────────────────────────────────
    content_score = 0

    verbed = sum(
        1 for l in bullet_lines
        if l.lstrip('•-* ').split()[0].lower() in STRONG_ACTION_VERBS
        if l.lstrip('•-* ').split()
    )
    verb_ratio = verbed / max(len(bullet_lines), 1)
    content_score += min(10, int(verb_ratio * 10))

    number_pattern = re.compile(
        r'\b\d+[\.,]?\d*\s*(%|x|times|ms|gb|k|m|users|requests|points|million|thousand)?\b',
        re.IGNORECASE
    )
    quantified = sum(1 for l in bullet_lines if number_pattern.search(l))
    quant_ratio = quantified / max(len(bullet_lines), 1)
    content_score += min(10, int(quant_ratio * 10))

    breakdown["content_quality"] = {
        "score": content_score,
        "max": 20,
        "label": "Content Quality",
        "detail": f"{verbed}/{len(bullet_lines)} bullets with action verbs, {quantified} quantified"
    }

    # ── 3. SKILLS RELEVANCE (20 points) ──────────────────────────────────
    skills_score = 0
    if job_description:
        jd_lower = job_description.lower()
        tech_skills = [
            "python", "javascript", "typescript", "react", "node", "fastapi",
            "django", "docker", "kubernetes", "aws", "gcp", "azure", "sql",
            "mongodb", "postgresql", "redis", "git", "langchain", "tensorflow",
            "pytorch", "machine learning", "deep learning", "nlp", "api", "rest",
            "graphql", "linux", "bash", "java", "c++", "golang", "rust"
        ]
        jd_skills = [s for s in tech_skills if s in jd_lower]
        resume_skills = [s for s in jd_skills if s in text_lower]
        if jd_skills:
            skills_score = min(20, int((len(resume_skills) / len(jd_skills)) * 20))
        else:
            skills_score = 12
    else:
        all_skills = [
            "python", "javascript", "typescript", "react", "node", "java",
            "docker", "aws", "sql", "mongodb", "git", "tensorflow", "pytorch"
        ]
        found_skills = [s for s in all_skills if s in text_lower]
        skills_score = min(20, len(found_skills) * 2)

    breakdown["skills_relevance"] = {
        "score": skills_score,
        "max": 20,
        "label": "Skills Relevance",
        "detail": f"{skills_score}/20 based on job match"
    }

    # ── 4. EXPERIENCE DEPTH (15 points) ──────────────────────────────────
    exp_score = 0

    date_pattern = re.compile(r'\b(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|present|current)\b', re.IGNORECASE)
    experience_entries = len(date_pattern.findall(resume_text))
    exp_score += min(6, experience_entries * 2)

    project_indicators = len(re.findall(r'(project|app|system|platform|website|tool|bot)', text_lower))
    exp_score += min(5, project_indicators)

    exp_score += min(4, len(bullet_lines) // 3)

    exp_score = min(15, exp_score)
    breakdown["experience_depth"] = {
        "score": exp_score,
        "max": 15,
        "label": "Experience Depth",
        "detail": f"{experience_entries} roles/entries, {len(bullet_lines)} bullet points"
    }

    # ── 5. EDUCATION (10 points) ──────────────────────────────────────────
    edu_score = 0

    if any(d in text_lower for d in ["b.tech", "btech", "bachelor", "b.e.", "be "]):
        edu_score += 4
    elif any(d in text_lower for d in ["m.tech", "mtech", "master", "mba", "m.s."]):
        edu_score += 5
    elif "phd" in text_lower or "doctorate" in text_lower:
        edu_score += 6

    if re.search(r'(cgpa|gpa|grade)\s*[:\-]?\s*\d+[\.,]\d+', text_lower):
        edu_score += 3

    if any(u in text_lower for u in ["university", "college", "institute", "nmims", "iit", "nit"]):
        edu_score += 3

    edu_score = min(10, edu_score)
    breakdown["education"] = {
        "score": edu_score,
        "max": 10,
        "label": "Education",
        "detail": "Degree level and academic credentials"
    }

    # ── 6. COMPLETENESS (10 points) ──────────────────────────────────────
    complete_score = 0

    required_sections = ["experience", "education", "skills", "projects"]
    for section in required_sections:
        if section in text_lower:
            complete_score += 2

    if re.search(r'[\w.\-]+@[\w.\-]+\.\w+', resume_text):
        complete_score += 1
    if re.search(r'\+?\d[\d\s\-().]{7,}', resume_text):
        complete_score += 1

    complete_score = min(10, complete_score)
    breakdown["completeness"] = {
        "score": complete_score,
        "max": 10,
        "label": "Completeness",
        "detail": f"{complete_score}/10 required sections and contact info found"
    }

    # ── TOTAL ─────────────────────────────────────────────────────────────
    total = sum(v["score"] for v in breakdown.values())
    total_max = sum(v["max"] for v in breakdown.values())
    percentage = round(total / total_max * 100)

    return {
        "overall_score": percentage,
        "raw_score": total,
        "max_score": total_max,
        "breakdown": breakdown,
        "grade": (
            "Excellent" if percentage >= 85 else
            "Good"      if percentage >= 70 else
            "Fair"      if percentage >= 55 else
            "Needs Work"
        )
    }
