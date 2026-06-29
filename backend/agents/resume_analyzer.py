# backend/agents/resume_analyzer.py
import json
import re
import hashlib
import logging
import PyPDF2
from core.singletons import get_skills_retriever, get_cache
import os
import asyncio

async def call_gemini_with_user_key_async(prompt: str) -> str:
    gemini_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not gemini_key:
        from core.singletons import call_gemini_async
        return await call_gemini_async(prompt)
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(prompt)
        )
        return response.text or ""
    except Exception as e:
        logger.error("Gemini call failed with key: %s, falling back to Groq", e)
        from core.singletons import call_gemini_async
        return await call_gemini_async(prompt)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

STRONG_ACTION_VERBS = [
    "engineered", "architected", "built", "developed", "implemented", "deployed",
    "designed", "optimized", "automated", "integrated", "launched", "led",
    "managed", "created", "delivered", "improved", "reduced", "increased",
    "streamlined", "established", "coordinated", "executed", "analyzed",
    "configured", "maintained", "migrated", "scaled", "researched", "published",
    "trained", "mentored", "collaborated", "spearheaded", "accelerated",
    "revamped", "refactored", "debugged", "tested", "monitored", "secured",
    "documented", "presented", "negotiated", "resolved", "identified", "proposed"
]

STANDARD_SECTIONS = [
    "experience", "education", "skills", "projects", "certifications",
    "achievements", "summary", "objective", "publications", "awards",
    "internship", "internships", "work experience", "professional experience"
]

GENERAL_TECH_KEYWORDS = [
    "python", "javascript", "typescript", "react", "node", "java", "c++", "c#",
    "docker", "kubernetes", "aws", "gcp", "azure", "sql", "mongodb",
    "postgresql", "redis", "git", "fastapi", "django", "flask", "express",
    "tensorflow", "pytorch", "machine learning", "deep learning", "nlp",
    "langchain", "api", "rest", "graphql", "linux", "bash", "golang",
    "rust", "html", "css", "tailwind", "nextjs", "next.js", "vue", "angular",
    "spring", "microservices", "ci/cd", "agile", "scrum", "figma",
    "selenium", "pytest", "firebase", "supabase", "stripe", "langraph",
    "openai", "gemini", "llm", "vector", "embedding", "chromadb",
    "pandas", "numpy", "scikit", "sklearn", "matplotlib", "tableau",
    "hadoop", "spark", "kafka", "rabbitmq", "celery", "nginx",
    "terraform", "ansible", "github", "bitbucket", "jira", "confluence"
]


# ─────────────────────────────────────────────────────────────────────────────
# PDF EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF."""
    text = ""
    try:
        import fitz  # PyMuPDF
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

    return text


# ─────────────────────────────────────────────────────────────────────────────
# REAL ATS SCORER  (no hardcoded scores)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_real_ats_score(resume_text: str, job_description: str = "") -> dict:
    """
    Calculate a REAL ATS score by analyzing the actual extracted PDF text.
    Every category is computed from the resume content — nothing is hardcoded.
    Returns a detailed breakdown of every scoring component.
    """
    text_lower = resume_text.lower()
    lines = [l.strip() for l in resume_text.split("\n") if l.strip()]
    bullet_lines = [l for l in lines if l.startswith(("•", "-", "*", "–", "▪", "○"))]

    scores = {}

    # ── 1. SECTION DETECTION (20 points) ─────────────────────────────────────
    sections_found = [s for s in STANDARD_SECTIONS if s in text_lower]
    # Deduplicate (e.g. "experience" and "work experience" both match)
    unique_sections = list(set(sections_found))
    # Only count the 6 most important unique ones
    section_score = min(20, len(unique_sections) * 4)

    scores["sections"] = {
        "score": section_score,
        "max": 20,
        "found": unique_sections,
        "missing": [s for s in ["experience", "education", "skills", "projects", "summary"]
                    if s not in text_lower]
    }

    # ── 2. KEYWORD MATCH RATE (25 points) ────────────────────────────────────
    keyword_score = 0
    matched_keywords = []
    missing_keywords = []

    if job_description and job_description.strip():
        # Score against job description keywords
        stopwords = {
            "with", "and", "the", "for", "this", "that", "will", "have",
            "from", "they", "them", "their", "about", "into", "than",
            "your", "our", "are", "were", "been", "being", "would",
            "could", "should", "must", "shall", "may", "might", "also",
            "which", "what", "when", "where", "who", "how", "not", "but"
        }
        jd_words = set(
            w.lower().strip(".,;:()")
            for w in job_description.split()
            if len(w) > 3 and w.lower() not in stopwords
        )

        for kw in jd_words:
            if kw in text_lower:
                matched_keywords.append(kw)
            else:
                # Try stem matching (first 5 chars)
                stem = kw[:5]
                if any(stem in word for word in text_lower.split()):
                    matched_keywords.append(kw)
                else:
                    missing_keywords.append(kw)

        match_rate = len(matched_keywords) / max(len(jd_words), 1)
        keyword_score = min(25, int(match_rate * 25))

    else:
        # ── FIX: No JD — score by counting general tech keywords in the resume ──
        # This ensures every resume gets a DIFFERENT score based on its content.
        found = [kw for kw in GENERAL_TECH_KEYWORDS if kw in text_lower]
        matched_keywords = found
        missing_keywords = [kw for kw in GENERAL_TECH_KEYWORDS if kw not in text_lower]

        # Scale: 0 keywords=0pts | 5=7pts | 10=15pts | 17+=25pts
        keyword_score = min(25, int(len(found) * 1.5))

    scores["keywords"] = {
        "score": keyword_score,
        "max": 25,
        "matched": matched_keywords[:20],
        "missing": missing_keywords[:15],
        "match_rate": round(
            len(matched_keywords) / max(len(matched_keywords) + len(missing_keywords), 1) * 100, 1
        )
    }

    # ── 3. ACTION VERB USAGE (15 points) ─────────────────────────────────────
    verbs_used = []
    bullets_with_verbs = 0

    for line in bullet_lines:
        content = line.lstrip("•-*–▪○ ").lower()
        parts = content.split()
        if not parts:
            continue
        first_word = parts[0].rstrip(".,;:")
        if first_word in STRONG_ACTION_VERBS:
            bullets_with_verbs += 1
            verbs_used.append(first_word)

    if bullet_lines:
        verb_rate = bullets_with_verbs / len(bullet_lines)
        verb_score = min(15, int(verb_rate * 15))
    else:
        # No bullet points at all — heavy penalty
        verb_score = 0

    scores["action_verbs"] = {
        "score": verb_score,
        "max": 15,
        "bullets_total": len(bullet_lines),
        "bullets_with_strong_verbs": bullets_with_verbs,
        "verbs_used": list(set(verbs_used))[:10]
    }

    # ── 4. QUANTIFICATION (15 points) ────────────────────────────────────────
    number_pattern = re.compile(
        r"\b\d+[\.,]?\d*\s*"
        r"(%|percent|x|times|ms|gb|tb|kb|k|m|users|requests|seconds|hours|"
        r"days|weeks|points|stars|million|billion|thousand|lakh|crore)?\b",
        re.IGNORECASE
    )

    bullets_quantified = 0
    for line in bullet_lines:
        if number_pattern.search(line):
            bullets_quantified += 1

    if bullet_lines:
        quant_rate = bullets_quantified / len(bullet_lines)
        quant_score = min(15, int(quant_rate * 15))
    else:
        quant_score = 0

    scores["quantification"] = {
        "score": quant_score,
        "max": 15,
        "bullets_quantified": bullets_quantified,
        "bullets_total": len(bullet_lines),
        "rate": round(bullets_quantified / max(len(bullet_lines), 1) * 100, 1)
    }

    # ── 5. CONTACT INFO (10 points) ───────────────────────────────────────────
    contact_score = 0
    contact_found = []

    if re.search(r"[\w.\-]+@[\w.\-]+\.\w+", resume_text):
        contact_score += 3
        contact_found.append("email")
    if re.search(r"\+?\d[\d\s\-().]{7,}", resume_text):
        contact_score += 2
        contact_found.append("phone")
    if re.search(r"linkedin\.com", text_lower):
        contact_score += 2
        contact_found.append("linkedin")
    if re.search(r"github\.com", text_lower):
        contact_score += 2
        contact_found.append("github")
    if re.search(r"(portfolio|website|behance|dribbble|leetcode|kaggle)\.?(com)?", text_lower):
        contact_score += 1
        contact_found.append("portfolio/other")

    contact_score = min(10, contact_score)

    scores["contact_info"] = {
        "score": contact_score,
        "max": 10,
        "found": contact_found
    }

    # ── 6. FORMATTING & PARSABILITY (15 points) ───────────────────────────────
    format_score = 15
    format_issues = []

    # Too many non-ASCII characters (tables, special chars, graphics)
    non_ascii = sum(1 for c in resume_text if ord(c) > 127)
    if len(resume_text) > 0 and non_ascii / len(resume_text) > 0.05:
        format_score -= 5
        format_issues.append("High non-ASCII character ratio — possible table/graphic parsing issue")

    # No bullet points at all
    if len(bullet_lines) == 0:
        format_score -= 4
        format_issues.append("No bullet points detected — use bullet points for experience entries")

    # Too short
    if len(resume_text) < 300:
        format_score -= 8
        format_issues.append("Resume text is very short — PDF may not be text-based (scanned image?)")
    elif len(resume_text) < 600:
        format_score -= 3
        format_issues.append("Resume content seems thin — add more detail")

    # Too long (over 3 pages worth)
    if len(resume_text) > 5000:
        format_score -= 2
        format_issues.append("Resume may be too long — aim for 1-2 pages")

    # Low vocabulary diversity (repetitive text)
    words = resume_text.split()
    unique_words = set(words)
    if len(words) > 0 and len(unique_words) / len(words) < 0.4:
        format_score -= 3
        format_issues.append("Low word diversity — avoid repeating the same words")

    format_score = max(0, format_score)

    scores["formatting"] = {
        "score": format_score,
        "max": 15,
        "text_length": len(resume_text),
        "bullet_lines": len(bullet_lines),
        "issues": format_issues,
        "clean_extraction": format_score >= 10
    }

    # ── TOTAL ─────────────────────────────────────────────────────────────────
    total = sum(v["score"] for v in scores.values())
    total_max = sum(v["max"] for v in scores.values())  # Should be 100
    percentage = round(total / total_max * 100, 1)

    grade = (
        "Excellent" if percentage >= 85 else
        "Good"      if percentage >= 70 else
        "Fair"      if percentage >= 55 else
        "Poor"
    )

    all_feedback = []
    for key, val in scores.items():
        if "issues" in val:
            all_feedback.extend(val["issues"])

    return {
        "ats_score": percentage,
        "total": total,
        "total_max": total_max,
        "percentage": percentage,
        "grade": grade,
        "score_breakdown": {
            k: {"score": v["score"], "max": v["max"]}
            for k, v in scores.items()
        },
        "found_keywords": scores["keywords"]["matched"],
        "missing_keywords": scores["keywords"]["missing"],
        "missing_sections": scores["sections"]["missing"],
        "feedback": all_feedback,
        "top_issues": _get_top_issues(scores)
    }


def _get_top_issues(scores: dict) -> list:
    labels = {
        "sections":      "Add missing resume sections (Experience, Skills, Education, Projects)",
        "keywords":      "Add more relevant tech keywords to your resume",
        "action_verbs":  "Start bullet points with strong action verbs (Built, Led, Optimized...)",
        "quantification": "Quantify achievements with numbers (%, $, users, ms, etc.)",
        "contact_info":  "Add LinkedIn, GitHub, and phone number to contact section",
        "formatting":    "Fix PDF formatting — text may not be parsing cleanly"
    }
    issues = []
    for key, val in scores.items():
        gap = val["max"] - val["score"]
        if gap > 2:
            issues.append({
                "area": labels.get(key, key),
                "gap": gap,
                "score": val["score"],
                "max": val["max"]
            })
    issues.sort(key=lambda x: -x["gap"])
    return issues[:4]


# ─────────────────────────────────────────────────────────────────────────────
# OVERALL SCORE  (composite across 6 dimensions)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_overall_score(resume_text: str, job_description: str = "") -> dict:
    text_lower = resume_text.lower()
    lines = [l.strip() for l in resume_text.split("\n") if l.strip()]
    bullet_lines = [l for l in lines if l.startswith(("•", "-", "*", "–", "▪", "○"))]

    breakdown = {}

    # ── 1. ATS COMPATIBILITY (25 points) ─────────────────────────────────────
    ats_result = calculate_real_ats_score(resume_text, job_description)
    ats_component = round(ats_result["percentage"] * 0.25)
    breakdown["ats_compatibility"] = {
        "score": ats_component,
        "max": 25,
        "label": "ATS Compatibility",
        "detail": f"{ats_result['percentage']}% keyword & structure match"
    }

    # ── 2. CONTENT QUALITY (20 points) ───────────────────────────────────────
    content_score = 0

    verbed = sum(
        1 for l in bullet_lines
        if l.lstrip("•-*–▪○ ").split()
        and l.lstrip("•-*–▪○ ").split()[0].rstrip(".,;:").lower() in STRONG_ACTION_VERBS
    )
    verb_ratio = verbed / max(len(bullet_lines), 1)
    content_score += min(10, int(verb_ratio * 10))

    number_pattern = re.compile(
        r"\b\d+[\.,]?\d*\s*(%|x|times|ms|gb|k|m|users|requests|points|million|thousand|lakh)?\b",
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

    # ── 3. SKILLS RELEVANCE (20 points) ──────────────────────────────────────
    skills_score = 0
    if job_description and job_description.strip():
        jd_lower = job_description.lower()
        jd_skills = [s for s in GENERAL_TECH_KEYWORDS if s in jd_lower]
        resume_skills = [s for s in jd_skills if s in text_lower]
        if jd_skills:
            skills_score = min(20, int((len(resume_skills) / len(jd_skills)) * 20))
        else:
            skills_score = 10
    else:
        found_skills = [s for s in GENERAL_TECH_KEYWORDS if s in text_lower]
        skills_score = min(20, len(found_skills) * 2)

    breakdown["skills_relevance"] = {
        "score": skills_score,
        "max": 20,
        "label": "Skills Relevance",
        "detail": f"{skills_score}/20 based on tech keywords found"
    }

    # ── 4. EXPERIENCE DEPTH (15 points) ──────────────────────────────────────
    exp_score = 0

    date_pattern = re.compile(
        r"\b(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|present|current|now)\b",
        re.IGNORECASE
    )
    experience_entries = len(date_pattern.findall(resume_text))
    exp_score += min(6, experience_entries * 2)

    project_indicators = len(re.findall(
        r"(project|app|system|platform|website|tool|bot|dashboard|api|service|module)",
        text_lower
    ))
    exp_score += min(5, project_indicators)

    exp_score += min(4, len(bullet_lines) // 3)
    exp_score = min(15, exp_score)

    breakdown["experience_depth"] = {
        "score": exp_score,
        "max": 15,
        "label": "Experience Depth",
        "detail": f"{experience_entries} roles/entries detected, {len(bullet_lines)} bullet points"
    }

    # ── 5. EDUCATION (10 points) ──────────────────────────────────────────────
    edu_score = 0

    if any(d in text_lower for d in ["b.tech", "btech", "bachelor", "b.e.", "b.sc", "bsc", "be "]):
        edu_score += 4
    if any(d in text_lower for d in ["m.tech", "mtech", "master", "mba", "m.s.", "m.sc", "msc"]):
        edu_score += 5
    if "phd" in text_lower or "doctorate" in text_lower or "ph.d" in text_lower:
        edu_score += 6

    if re.search(r"(cgpa|gpa|grade)\s*[:\-]?\s*\d+[\.,]\d+", text_lower):
        edu_score += 2

    if any(u in text_lower for u in [
        "university", "college", "institute", "iit", "nit", "bits", "nmims",
        "vit", "manipal", "amity", "mit", "stanford", "harvard", "oxford"
    ]):
        edu_score += 2

    edu_score = min(10, edu_score)
    breakdown["education"] = {
        "score": edu_score,
        "max": 10,
        "label": "Education",
        "detail": "Degree level and academic credentials"
    }

    # ── 6. COMPLETENESS (10 points) ───────────────────────────────────────────
    complete_score = 0
    required_sections = ["experience", "education", "skills", "projects"]
    for section in required_sections:
        if section in text_lower:
            complete_score += 2

    if re.search(r"[\w.\-]+@[\w.\-]+\.\w+", resume_text):
        complete_score += 1
    if re.search(r"\+?\d[\d\s\-().]{7,}", resume_text):
        complete_score += 1

    complete_score = min(10, complete_score)
    breakdown["completeness"] = {
        "score": complete_score,
        "max": 10,
        "label": "Completeness",
        "detail": f"{complete_score}/10 required sections and contact info found"
    }

    # ── TOTAL ─────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ANALYSIS ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_resume(
    file_path: str,
    user_id: str = "anonymous",
    job_description: str = "",
    progress_callback=None
) -> dict:
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

    # ── FIX: Hash resume CONTENT and JOB DESC not just file path ──────────────
    content_hash = hashlib.md5(resume_text.encode()).hexdigest()
    jd_hash = hashlib.md5(job_description.encode()).hexdigest() if job_description else "general"
    cache_key = f"analysis:{content_hash}:{jd_hash}"
    cache = get_cache()

    if cache_key in cache:
        emit("⚡ Resume analysis cache hit")
        return cache[cache_key]

    # ── Calculate real ATS score deterministically ────────────────────────────
    emit("Scanning resume layout and formatting...")
    ats_data = calculate_real_ats_score(resume_text, job_description)
    real_ats_score = ats_data["ats_score"]

    # Truncate to first 2500 chars for Gemini speed
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
1. overall_score: integer 0-100 (your holistic assessment of resume quality, can differ from ATS score)
2. ats_score: integer — USE EXACTLY {real_ats_score} (do not change this)
3. skills_found: list of skills you can identify from the resume text
4. skill_gaps: list of important skills missing for a tech role
5. suggestions: 3-5 specific, actionable bullet points to improve this resume
6. experience_level: "junior" | "mid" | "senior"
7. summary: 2-sentence honest assessment of this specific resume
8. sections_detected: list of sections you can see in the resume
9. strengths: list of 2-4 concrete strengths of this resume
10. keywords_missing: list of important keywords not found

Return ONLY valid JSON, no markdown backticks, no explanation outside JSON.
"""
        raw_output = await call_gemini_with_user_key_async(formatted_prompt)
        cleaned = re.sub(r"```json|```", "", raw_output).strip()
        parsed = json.loads(cleaned)

        # Always overwrite ats_score with the deterministic value
        parsed["ats_score"] = real_ats_score
        parsed["ats_breakdown"] = ats_data["score_breakdown"]
        parsed["feedback"] = ats_data["feedback"]
        parsed["grade"] = ats_data["grade"]
        parsed["found_keywords"] = ats_data["found_keywords"]
        parsed["missing_keywords"] = ats_data["missing_keywords"]
        parsed["missing_sections"] = ats_data["missing_sections"]
        parsed["resume_text"] = resume_text  # stored for resume rewriter agent

        cache[cache_key] = parsed
        emit("✅ Analysis complete!")
        return parsed

    except Exception as e:
        logger.error("Gemini analysis failed: %s", e)

        # ── FIX: Fallback uses real calculated score, not hardcoded 50 ──────────
        fallback = {
            "skills_found": ats_data.get("found_keywords", []),
            "skill_gaps": ats_data.get("missing_keywords", [])[:10],
            "experience_level": "junior",
            "overall_score": int(real_ats_score),
            "ats_score": int(real_ats_score),          # real score, not 50
            "ats_breakdown": ats_data["score_breakdown"],
            "sections_detected": ats_data["score_breakdown"].get("sections", {}).get("found", []),
            "suggestions": [
                "Gemini AI analysis failed — showing deterministic ATS scan results.",
                *ats_data.get("feedback", [])[:4]
            ],
            "strengths": [
                f"Keywords found: {', '.join(ats_data.get('found_keywords', [])[:5]) or 'None detected'}",
                f"Sections present: {', '.join(ats_data['score_breakdown'].get('sections', {}).get('found', [])) or 'None detected'}"
            ],
            "keywords_missing": ats_data.get("missing_keywords", [])[:10],
            "format_issues": ats_data.get("feedback", []),
            "grade": ats_data["grade"],
            "found_keywords": ats_data.get("found_keywords", []),
            "missing_keywords": ats_data.get("missing_keywords", []),
            "missing_sections": ats_data.get("missing_sections", []),
            "feedback": ats_data.get("feedback", []),
            "resume_text": resume_text,
            "error": str(e)
        }
        return fallback
