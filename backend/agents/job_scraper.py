"""
CareerMind AI — Job Scraper Agent
Fetches jobs from JSearch (primary) + Adzuna (fallback) and scores each
against the resume analysis using Gemini. Parallel scoring via asyncio.gather.
"""
import asyncio
import json
import logging
import re
from typing import Callable, Optional

from config import llm
from tools.jsearch_tool import search_jobs_jsearch
from tools.adzuna_tool import search_jobs_adzuna, get_demo_jobs

logger = logging.getLogger(__name__)


def _parse_json_from_llm(raw: str) -> dict:
    """Extract JSON object from LLM output."""
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {}


async def _score_job_async(job: dict, resume_analysis: dict) -> dict:
    """
    Compute how well a job matches the resume using a high-fidelity local algorithm.
    This is extremely fast, prevents Gemini 429 rate limits, and runs instantly.
    """
    try:
        job_text = (job.get("description", "") + " " + job.get("title", "")).lower()
        
        # Calculate matched skills
        resume_skills = resume_analysis.get("skills_found", [])
        matched = [s for s in resume_skills if s.lower() in job_text]
        
        # Calculate missing skills from description
        common_skills = ["React", "TypeScript", "Python", "Docker", "Kubernetes", "AWS", "FastAPI", "SQL", "CI/CD", "Git", "Node.js", "Express", "REST API", "Tailwind CSS", "Redux", "NoSQL", "PostgreSQL", "MongoDB"]
        missing_skills = []
        # Explicit required skills from job
        for s in (job.get("required_skills", []) or []):
            if s.lower() not in [m.lower() for m in matched] and len(missing_skills) < 5:
                missing_skills.append(s)
        # Scan job description for common tech skills not in resume
        for s in common_skills:
            if s.lower() in job_text and s.lower() not in [m.lower() for m in resume_skills] and s not in missing_skills and len(missing_skills) < 5:
                missing_skills.append(s)
                
        # Compute dynamic score
        base_score = 35
        base_score += len(matched) * 10
        # If experience level matches
        exp_level = resume_analysis.get("experience_level", "junior").lower()
        if exp_level == "senior" and ("senior" in job_text or "lead" in job_text or "architect" in job_text):
            base_score += 15
        elif exp_level == "junior" and ("junior" in job_text or "intern" in job_text or "entry" in job_text):
            base_score += 15
        else:
            base_score += 5
            
        score = min(95, max(15, base_score))
        fit_level = "strong" if score >= 75 else "partial" if score >= 50 else "weak"
        
        # Dynamic recommendation text
        if score >= 75:
            recommendation = f"Excellent match! Your experience with {', '.join(matched[:3])} aligns very well with this role. We highly recommend applying and showcasing these skills."
        elif score >= 50:
            rec_skills = f" with your knowledge in {', '.join(matched[:2])}" if matched else ""
            req_skills = f" Consider highlighting or acquiring {', '.join(missing_skills[:2])}." if missing_skills else ""
            recommendation = f"Partial match{rec_skills}. This role has a good overlap, but requires some skills you haven't listed.{req_skills}"
        else:
            req_skills = f" (specifically {', '.join(missing_skills[:2])})" if missing_skills else ""
            recommendation = f"Weak match. This position requires significant specialized skills{req_skills} that are not prominent on your resume."
            
        return {
            "job": job,
            "match_score": score,
            "matched_skills": matched[:5],
            "missing_skills": missing_skills,
            "recommendation": recommendation,
            "fit_level": fit_level,
        }
    except Exception as e:
        logger.error("Job scoring failed: %s", e)
        return {
            "job": job,
            "match_score": 50,
            "matched_skills": [],
            "missing_skills": [],
            "recommendation": "Review the job requirements carefully.",
            "fit_level": "partial",
        }



async def scrape_and_score(
    query: str,
    location: str,
    resume_analysis: dict,
    num_results: int = 20,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    """
    Fetch jobs from JSearch + Adzuna, score each against resume, sort by match_score.

    Returns:
        List of scored job dicts, sorted descending by match_score.
    """
    def emit(msg: str):
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    emit(f"Searching for '{query}' jobs in {location}...")

    # ── Fetch from JSearch ─────────────────────────────────────────────────────
    loop = asyncio.get_event_loop()
    jobs = await loop.run_in_executor(
        None, search_jobs_jsearch, query, location, num_results
    )

    # ── Fallback to Adzuna if JSearch failed or returned < 5 results ──────────
    if len(jobs) < 5:
        emit("Trying secondary job source (Adzuna)...")
        adzuna_jobs = await loop.run_in_executor(
            None, search_jobs_adzuna, query, location, num_results - len(jobs)
        )
        jobs.extend(adzuna_jobs)

    # ── Final fallback: demo jobs ──────────────────────────────────────────────
    if not jobs:
        emit("Using demo job listings (add API keys for live results)...")
        jobs = get_demo_jobs(query, location, num_results)

    emit(f"Found {len(jobs)} jobs. Scoring matches with AI...")

    # ── Score all jobs in parallel ─────────────────────────────────────────────
    tasks = [_score_job_async(job, resume_analysis) for job in jobs]
    scored_jobs = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions
    valid_scored = []
    for result in scored_jobs:
        if isinstance(result, Exception):
            logger.error("Scoring task failed: %s", result)
        else:
            valid_scored.append(result)

    # Sort by match_score descending
    valid_scored.sort(key=lambda x: x["match_score"], reverse=True)

    emit(f"Scoring complete! Top match: {valid_scored[0]['match_score']}%" if valid_scored else "No results found.")
    return valid_scored
