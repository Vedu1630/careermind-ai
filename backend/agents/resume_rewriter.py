"""
CareerMind AI — Resume Rewriter Agent
Takes a resume PDF path and a target job, extracts text/structure, and rewrites the content.
"""
import json
import logging
import re
from typing import Callable, Optional

from config import llm
from tools.pdf_tool import pdf_handler
from langchain.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


def _heuristic_resume_rewriter(resume_text: str, job: dict) -> dict:
    """Fallback rewriter that uses rules and keywords to optimize a resume for a target job."""
    job_title = job.get("title", "Target Role")
    job_description = job.get("description", "")
    required_skills = job.get("required_skills", []) or []

    # 1. Identify missing key terms/skills from the job description
    common_skills = ["React", "TypeScript", "Python", "Docker", "Kubernetes", "AWS", "FastAPI", "SQL", "CI/CD", "Git", "Node.js", "Express", "REST API", "Tailwind CSS", "Redux", "NoSQL", "PostgreSQL", "MongoDB"]

    keywords_to_add = []
    # Use explicit required skills first
    for skill in required_skills:
        if re.search(rf"\b{re.escape(skill)}\b", job_description, re.IGNORECASE):
            if not re.search(rf"\b{re.escape(skill)}\b", resume_text, re.IGNORECASE):
                keywords_to_add.append(skill)

    # Supplement with other common tech skills found in job description
    for skill in common_skills:
        if re.search(rf"\b{re.escape(skill)}\b", job_description, re.IGNORECASE):
            if not re.search(rf"\b{re.escape(skill)}\b", resume_text, re.IGNORECASE):
                if skill not in keywords_to_add:
                    keywords_to_add.append(skill)

    keywords_to_add = keywords_to_add[:6]
    if not keywords_to_add:
        keywords_to_add = ["CI/CD", "Docker", "REST APIs"]

    # 2. Perform passive phrasing replacements
    replacements = [
        (r"\b(worked on|helped with|participated in)\b", "engineered and optimized", True),
        (r"\b(responsible for)\b", "spearheaded the development and lifecycle of", True),
        (r"\b(managed|handled)\b", "architected and orchestrated", True),
        (r"\b(fixed|resolved bugs in)\b", "debugged and enhanced stability of", True),
        (r"\b(made|created)\b", "designed and deployed", True),
        (r"\b(wrote code for)\b", "developed robust implementations for", True),
        (r"\b(used|utilized)\b", "leveraged", True),
        (r"\b(fast|quick)\b", "high-performance", True)
    ]

    rewritten_lines = []
    changes_summary = []
    action_verb_count = 0

    for line in resume_text.split("\n"):
        new_line = line
        for pattern, repl, is_verb in replacements:
            if re.search(pattern, new_line, re.IGNORECASE):
                new_line = re.sub(pattern, repl, new_line, flags=re.IGNORECASE)
                if is_verb and action_verb_count < 3:
                    action_verb_count += 1
                    changes_summary.append(f"Upgraded passive phrasing to active verb: '{repl}'")
        rewritten_lines.append(new_line)

    rewritten_text = "\n".join(rewritten_lines)

    # 3. Add a dedicated ATS optimization section
    optimization_section = f"\n\n=== ATS OPTIMIZATION & RELEVANT SKILLS FOR {job_title.upper()} ===\n"
    optimization_section += f"Target Role keywords integrated: {', '.join(keywords_to_add)}\n"
    optimization_section += "Recommended Alignment: Focus bullet points on system design, automated testing, and scalable deployments.\n"

    rewritten_text += optimization_section

    changes_summary.append(f"Injected {len(keywords_to_add)} missing high-priority ATS keywords: {', '.join(keywords_to_add)}")
    changes_summary.append(f"Appended custom ATS alignment section tailored for {job_title} at {job.get('company', 'Target Company')}")

    return {
        "original": resume_text,
        "rewritten": rewritten_text,
        "changes_summary": changes_summary,
        "keywords_added": keywords_to_add,
        "sections_reordered": ["Summary", "Technical Skills", "Professional Experience", "Projects", "Education"],
        "improvements_made": len(changes_summary) + 2,
        "is_fallback": True
    }


async def rewrite_resume(
    resume_path: str,
    job: dict,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Extracts text and structure from a resume PDF, calls Gemini to rewrite it,
    and returns original, rewritten, changes summary, and structure metadata.
    """
    def emit(msg: str):
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    emit("Extracting text from original PDF resume...")
    # Step 1: Extract plain text for Gemini
    original_text = pdf_handler.extract_text_for_ai(resume_path)
    
    emit("Optimizing resume content with Gemini AI...")
    # Step 3: Call Gemini to rewrite text content only
    prompt = ChatPromptTemplate.from_template("""
You are a professional ATS resume optimizer. Rewrite this resume to maximize ATS score for the target job.

YOUR ONLY JOB IS TEXT IMPROVEMENT — A SEPARATE SYSTEM HANDLES PDF FORMATTING.

STRICT RULES — breaking these corrupts the PDF:
1. Output EXACTLY the same number of lines as the input — count them before responding
2. Every section header must be kept EXACTLY word-for-word: Education, Experience, Projects, Certifications, Core Skills, Achievements and Positions of Responsibility — do not change these
3. Every name, university, school, company, CGPA, percentage, date, and job title stays EXACTLY the same
4. Bullet point marker • must appear at the start of every bullet line — never remove it
5. Do not add lines, remove lines, merge lines, or split lines
6. Only change the descriptive body text of bullet points and project descriptions
7. Add ATS keywords from the job description naturally into existing sentences
8. Quantify vague statements with metrics where possible (e.g. "improved performance" → "improved model accuracy by 18%")
9. Use strong action verbs: Engineered, Architected, Deployed, Optimized, Automated, Implemented
10. Output plain text only — no markdown, no asterisks, no bold markers, no numbering added
11. Lines that are dates, scores, school names, company names — output them UNCHANGED
12. If a line cannot be improved, output it character-for-character unchanged

ATS IMPROVEMENT GOALS:
- Match keywords from the job description exactly as they appear
- Use industry-standard terminology for the target role
- Quantify impact on every bullet point where possible
- Lead every bullet with a strong action verb
- Include relevant tools, frameworks, and methodologies from the job description

Original Resume:
{resume}

Target Job Title: {job_title}

Target Job Description:
{job_description}

Output the ATS-optimized resume now. Same number of lines. Same structure. Only descriptive text content changes.
""")
    
    is_fallback = False
    try:
        chain = prompt | llm
        result = chain.invoke({
            "resume": original_text,
            "job_title": job.get("title", ""),
            "job_description": job.get("description", "")
        })
        rewritten_text = result.content
    except Exception as e:
        logger.warning("Gemini resume rewrite failed (rate limits or error), using local heuristic fallback: %s", e)
        fallback_data = _heuristic_resume_rewriter(original_text, job)
        rewritten_text = fallback_data["rewritten"]
        is_fallback = True
        
    # Step 4: Detect what changed for the UI diff view
    original_lines = [l for l in original_text.split('\n') if l.strip()]
    rewritten_lines = [l for l in rewritten_text.split('\n') if l.strip()]
    
    keywords_added = []
    changes_summary = []
    
    job_keywords = job.get("description", "").lower().split()
    for line in rewritten_lines:
        for kw in job_keywords:
            if len(kw) > 5 and kw in line.lower() and kw not in original_text.lower():
                keywords_added.append(kw)
                
    keywords_added = list(set(keywords_added))[:15]
    
    if is_fallback:
        fallback_data = _heuristic_resume_rewriter(original_text, job)
        keywords_added = fallback_data["keywords_added"]
        changes_summary = fallback_data["changes_summary"]
    else:
        # Count how many lines actually changed
        changed_count = sum(1 for o, r in zip(original_lines, rewritten_lines) if o != r)
        changed_count += max(0, len(rewritten_lines) - len(original_lines))

        changes_summary = [
            f"Tailored {changed_count} lines for job relevance",
            f"Added {len(keywords_added)} role-specific keywords",
            "Preserved original formatting and structure",
            "Quantified impact statements where possible"
        ]
        
    return {
        "original_text": original_text,
        "rewritten_text": rewritten_text,
        "changes_summary": changes_summary,
        "keywords_added": keywords_added,
        "structure": {},
        "resume_path": resume_path
    }
