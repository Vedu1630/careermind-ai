# agents/resume_rewriter.py
import re
import asyncio
from typing import Optional, Callable
from core.singletons import get_llm, call_gemini_async
from tools.pdf_tool import pdf_handler

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
    original_text = pdf_handler.extract_text_for_ai(resume_path)
    job_title     = job.get("title", "Software Engineer")
    job_desc      = (job.get("description") or "")[:500]

    prompt = f"""You are a professional resume editor. Rewrite this resume to improve ATS score for the target job.

ABSOLUTE RULES — BREAKING ANY OF THESE WILL CORRUPT THE PDF:

1. Output the EXACT same number of lines as the input — count them before responding
2. NEVER add placeholder text like [Email], [LinkedIn], [GitHub], [Phone], [URL], [Website] — these will appear in the PDF and look broken
3. NEVER change section header text — Education, Experience, Projects, Certifications, Core Skills, Achievements must stay word-for-word
4. NEVER change any names, university names, school names, company names, job titles, dates, CGPA, percentages
5. NEVER change bullet point markers — keep • exactly as-is
6. NEVER merge two lines into one or split one line into two
7. NEVER change the bold/italic formatting markers — keep bold labels bold
8. ONLY improve: bullet point descriptions, project descriptions — add keywords, quantify achievements
9. All added metrics must be plausible — do not invent impossible numbers
10. Return ONLY the resume text — no explanation, no preamble, no markdown

Original Resume (count the lines — your output must have the same count):
{original_text[:2500]}

Target Job: {job_title}
Job Keywords to incorporate: {job_desc[:300]}

Rewrite now — same line count, same structure, only description content changes:"""

    emit("Optimizing resume content with Gemini AI...")
    try:
        rewritten = await call_gemini_async(prompt, quality=True)
    except Exception as e:
        rewritten = f"ERROR: {str(e)}"

    if rewritten.startswith("ERROR:"):
        return {
            "original_text":   original_text,
            "rewritten_text":  original_text,
            "keywords_added":  [],
            "changes_summary": ["AI rewriting failed — returned original resume"],
            "error":           rewritten,
        }

    # POST-PROCESS: remove any placeholders Gemini added anyway
    placeholders = [
        r'\[Email\]', r'\[LinkedIn\]', r'\[GitHub\]', r'\[Phone\]',
        r'\[URL\]', r'\[Website\]', r'\[Address\]', r'\[Name\]'
    ]
    for p in placeholders:
        rewritten = re.sub(p, '', rewritten, flags=re.IGNORECASE)
    # Clean up double spaces/pipes left after placeholder removal
    rewritten = re.sub(r'\s*\|\s*\|\s*', ' | ', rewritten)
    rewritten = re.sub(r'^\s*\|\s*', '', rewritten, flags=re.MULTILINE)
    rewritten = re.sub(r'\s*\|\s*$', '', rewritten, flags=re.MULTILINE)

    job_words      = set(w.lower() for w in job_desc.split() if len(w) > 5)
    orig_words     = set(original_text.lower().split())
    new_words      = set(rewritten.lower().split())
    keywords_added = list((job_words & new_words) - orig_words)[:12]

    # ATS scoring
    jd_kw      = [w for w in job_words if len(w) > 4]
    orig_hits  = sum(1 for k in jd_kw if k in original_text.lower())
    new_hits   = sum(1 for k in jd_kw if k in rewritten.lower())
    orig_ats   = round(orig_hits / max(len(jd_kw), 1) * 100, 1)
    new_ats    = round(new_hits  / max(len(jd_kw), 1) * 100, 1)

    # Build the PDF preserving formatting
    emit("Rebuilding PDF with rewritten text...")
    try:
        pdf_bytes = pdf_handler.rebuild_pdf_with_rewritten_text(
            original_path=resume_path,
            original_text=original_text,
            rewritten_text=rewritten,
        )
        pdf_available = True
    except Exception as e:
        pdf_bytes     = None
        pdf_available = False
        print(f"PDF rebuild failed: {e}")

    result = {
        "original_text":   original_text,
        "rewritten_text":  rewritten,
        "keywords_added":  keywords_added,
        "pdf_available":   pdf_available,
        "changes_summary": [
            f"Added {len(keywords_added)} ATS keywords from job description",
            "Quantified achievements with realistic metrics",
            "Preserved exact original formatting and layout",
            "All names, dates, and facts kept unchanged",
        ],
        "ats_scores": {
            "original":    orig_ats,
            "rewritten":   new_ats,
            "improvement": round(new_ats - orig_ats, 1),
        },
    }

    # Store PDF bytes in temp file for download endpoint
    if pdf_bytes:
        import tempfile
        import os
        os.makedirs("data/uploads", exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=".pdf",
            delete=False,
            dir="data/uploads",
            prefix="rewritten_"
        )
        tmp.write(pdf_bytes)
        tmp.close()
        result["rewritten_pdf_path"] = tmp.name

    emit("Resume rewrite complete!")
    return result
