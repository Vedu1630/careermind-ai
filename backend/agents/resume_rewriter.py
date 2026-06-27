# agents/resume_rewriter.py
import re
import json
from typing import Optional, Callable
from langchain.prompts import ChatPromptTemplate
from core.singletons import get_llm, get_cache
from agents.resume_analyzer import extract_pdf_text

async def rewrite_resume(
    resume_path: str,
    job: dict,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    def emit(msg: str):
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    emit("Extracting text from original PDF resume...")
    # Reuse cached PDF text — never extract twice
    resume_text = extract_pdf_text(resume_path)
    job_title   = job.get("title", "")
    job_desc    = (job.get("description") or "")[:600]

    emit("Optimizing resume content with Gemini AI...")
    # Tight prompt — quality model but strict output format
    prompt = ChatPromptTemplate.from_template("""
You are a resume writer. Rewrite this resume for the job below.
RULES: Same line count. Same section headers. Keep all facts true. Add job keywords. Quantify achievements. Return ONLY the rewritten resume text.

Original resume:
{resume}

Target job: {title}
Job description: {desc}
""")

    chain = prompt | get_llm(quality=True)
    result = await chain.ainvoke({
        "resume": resume_text[:2500],
        "title":  job_title,
        "desc":   job_desc,
    })

    rewritten = result.content.strip()

    # Fast keyword diff
    job_words = set(
        w.lower() for w in job_desc.split()
        if len(w) > 5
    )
    orig_words  = set(resume_text.lower().split())
    new_words   = set(rewritten.lower().split())
    keywords_added = list((job_words & new_words) - orig_words)[:12]

    emit("Resume rewrite complete!")
    return {
        "original_text":   resume_text,
        "rewritten_text":  rewritten,
        "keywords_added":  keywords_added,
        "changes_summary": [
            f"Added {len(keywords_added)} role-specific keywords",
            "Preserved original layout and structure",
            "Strengthened bullet points with action verbs",
            "Aligned experience with job requirements",
        ],
        "structure": {},
        "resume_path": resume_path
    }
