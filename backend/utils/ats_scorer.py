import re
from typing import Dict, List

# Common ATS-relevant keywords by category
TECH_KEYWORDS = [
    # Languages
    "python", "java", "javascript", "typescript", "c++", "c#", "golang", "rust",
    "kotlin", "swift", "ruby", "php", "scala", "r", "matlab",
    # Frameworks
    "react", "angular", "vue", "django", "flask", "fastapi", "spring", "node.js",
    "express", "nextjs", "tensorflow", "pytorch", "scikit-learn", "keras",
    "langchain", "langgraph", "huggingface",
    # Cloud & DevOps
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ci/cd",
    "github actions", "jenkins", "ansible",
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "sqlite",
    "dynamodb", "firebase", "supabase",
    # AI/ML
    "machine learning", "deep learning", "nlp", "computer vision", "llm",
    "rag", "fine-tuning", "embeddings", "neural network", "transformer",
    # Tools
    "git", "linux", "rest api", "graphql", "microservices", "agile", "scrum",
]

ATS_SECTION_PATTERNS = {
    "contact": r"(email|phone|linkedin|github|portfolio|@|\d{10})",
    "summary": r"(summary|objective|profile|about)",
    "skills": r"(skills|technologies|tech stack|competencies|tools)",
    "experience": r"(experience|work|employment|internship|position|role)",
    "education": r"(education|degree|university|college|bachelor|master|b\.tech|m\.tech)",
    "projects": r"(project|built|developed|created|implemented)",
    "achievements": r"(achievement|award|certification|certificate|honor|winner)",
}

QUANTIFICATION_PATTERN = r"\b\d+[%+x]?\b.{0,30}(improved|reduced|increased|achieved|built|deployed|managed|led|processed|trained|accuracy|users|requests)"


def calculate_real_ats_score(resume_text: str, job_description: str = "") -> Dict:
    """
    Calculate a real, honest ATS score based on:
    - Keyword matching (40 points)
    - Required sections present (25 points)  
    - Quantified achievements (20 points)
    - Format/length quality (15 points)
    """
    text_lower = resume_text.lower()
    job_lower = job_description.lower() if job_description else ""
    
    score_breakdown = {}
    total_score = 0
    feedback = []
    missing_keywords = []
    found_keywords = []

    # ── 1. KEYWORD SCORE (40 points) ──────────────────────────────────────────
    if job_lower:
        jd_keywords = [kw for kw in TECH_KEYWORDS if kw in job_lower]
        jd_words = set(re.findall(r'\b[A-Z][a-zA-Z+#.]{1,20}\b', job_description))
        jd_keywords_set = set(jd_keywords) | {w.lower() for w in jd_words}
    else:
        jd_keywords_set = set(TECH_KEYWORDS)
    
    for kw in jd_keywords_set:
        if kw in text_lower:
            found_keywords.append(kw)
        else:
            missing_keywords.append(kw)
    
    if jd_keywords_set:
        keyword_ratio = len(found_keywords) / len(jd_keywords_set)
        keyword_score = min(40, int(keyword_ratio * 40))
    else:
        keyword_score = 20
    
    score_breakdown["keywords"] = keyword_score
    total_score += keyword_score
    
    if keyword_score < 20:
        feedback.append(f"Low keyword match: only {len(found_keywords)}/{len(jd_keywords_set)} relevant keywords found.")
    
    # ── 2. SECTION SCORE (25 points) ──────────────────────────────────────────
    section_score = 0
    missing_sections = []
    found_sections = []
    
    for section, pattern in ATS_SECTION_PATTERNS.items():
        if re.search(pattern, text_lower):
            found_sections.append(section)
            section_score += 25 // len(ATS_SECTION_PATTERNS)
        else:
            missing_sections.append(section)
    
    section_score = min(25, section_score)
    score_breakdown["sections"] = section_score
    total_score += section_score
    
    if missing_sections:
        feedback.append(f"Missing sections: {', '.join(missing_sections)}")

    # ── 3. QUANTIFICATION SCORE (20 points) ────────────────────────────────────
    quantified_bullets = re.findall(QUANTIFICATION_PATTERN, text_lower)
    quant_count = len(quantified_bullets)
    
    if quant_count >= 5:
        quant_score = 20
    elif quant_count >= 3:
        quant_score = 15
    elif quant_count >= 1:
        quant_score = 8
    else:
        quant_score = 0
        feedback.append("No quantified achievements found (e.g., 'Improved speed by 40%', 'Built system for 10K users')")
    
    score_breakdown["quantification"] = quant_score
    total_score += quant_score

    # ── 4. FORMAT/LENGTH SCORE (15 points) ─────────────────────────────────────
    format_score = 0
    word_count = len(resume_text.split())
    
    if 300 <= word_count <= 800:
        format_score += 6
    elif word_count < 200:
        feedback.append("Resume is too short (under 200 words). Add more detail.")
    elif word_count > 1000:
        feedback.append("Resume may be too long for ATS (over 1000 words).")
    else:
        format_score += 3
    
    has_tables = bool(re.search(r'\|.+\|', resume_text))
    has_email = bool(re.search(r'\b[\w.]+@[\w.]+\.\w+\b', resume_text))
    has_phone = bool(re.search(r'\b[\d\s\-\(\)]{10,}\b', resume_text))
    
    if has_email:
        format_score += 3
    else:
        feedback.append("No email address detected — ATS systems require contact info.")
    
    if has_phone:
        format_score += 3
    else:
        feedback.append("No phone number detected.")
    
    if has_tables:
        feedback.append("Tables/columns detected — many ATS systems cannot parse tables.")
        format_score -= 3
    else:
        format_score += 3
    
    format_score = max(0, min(15, format_score))
    score_breakdown["format"] = format_score
    total_score += format_score

    # ── FINAL ──────────────────────────────────────────────────────────────────
    total_score = max(0, min(100, total_score))
    
    return {
        "ats_score": total_score,
        "score_breakdown": score_breakdown,
        "found_keywords": found_keywords[:20],
        "missing_keywords": missing_keywords[:20],
        "missing_sections": missing_sections,
        "quantified_achievements_count": quant_count,
        "word_count": word_count,
        "feedback": feedback,
        "grade": (
            "Excellent" if total_score >= 80 else
            "Good" if total_score >= 65 else
            "Fair" if total_score >= 50 else
            "Poor — needs major improvement"
        )
    }
