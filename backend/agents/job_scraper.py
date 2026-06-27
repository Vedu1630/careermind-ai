# agents/job_scraper.py
import asyncio
import json
import re
import hashlib
from typing import Optional, Callable
from langchain.prompts import ChatPromptTemplate
from core.singletons import get_llm, get_http_client, get_cache
import os

async def _fetch_jsearch(query: str, location: str) -> list:
    client = get_http_client()
    try:
        resp = await client.get(
            "https://jsearch.p.rapidapi.com/search",
            headers={
                "X-RapidAPI-Key":  os.getenv("RAPIDAPI_KEY", ""),
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            },
            params={"query": f"{query} in {location}", "num_pages": "1", "page": "1"},
            timeout=5.0,
        )
        data = resp.json().get("data", [])
        return [{
            "title":       j.get("job_title", ""),
            "company":     j.get("employer_name", ""),
            "location":    j.get("job_city", location),
            "description": (j.get("job_description") or "")[:400],
            "apply_link":  j.get("job_apply_link", ""),
            "salary":      j.get("job_salary_currency", ""),
            "source":      "jsearch"
        } for j in data[:12]]
    except Exception:
        return []

async def _fetch_adzuna(query: str, location: str) -> list:
    client = get_http_client()
    try:
        resp = await client.get(
            "https://api.adzuna.com/v1/api/jobs/in/search/1",
            params={
                "app_id":          os.getenv("ADZUNA_APP_ID", ""),
                "app_key":         os.getenv("ADZUNA_APP_KEY", ""),
                "what":            query,
                "where":           location,
                "results_per_page": 10,
            },
            timeout=5.0,
        )
        results = resp.json().get("results", [])
        return [{
            "title":       j.get("title", ""),
            "company":     j.get("company", {}).get("display_name", ""),
            "location":    j.get("location", {}).get("display_name", location),
            "description": (j.get("description") or "")[:400],
            "apply_link":  j.get("redirect_url", ""),
            "salary":      str(j.get("salary_max", "")),
            "source":      "adzuna"
        } for j in results]
    except Exception:
        return []

async def _score_single_job(job: dict, profile_summary: str) -> dict:
    """Score one job against profile — fast model, short prompt."""
    prompt = ChatPromptTemplate.from_template("""
Rate job fit. Return ONLY JSON, no markdown.
Profile: {profile}
Job: {title} at {company} — {desc}

Return: {{"match_score":85,"matched_skills":["Python"],"missing_skills":["Docker"],"recommendation":"Strong match"}}
""")
    chain = prompt | get_llm(quality=False)
    try:
        result = chain.invoke({
            "profile": profile_summary[:300],
            "title":   job["title"],
            "company": job["company"],
            "desc":    job["description"][:200],
        })
        cleaned = re.sub(r"```json|```", "", result.content).strip()
        fit = json.loads(cleaned)
        # Ensure correct schema fields are present
        return {
            "job": job,
            "match_score": fit.get("match_score", 50),
            "matched_skills": fit.get("matched_skills", []),
            "missing_skills": fit.get("missing_skills", []),
            "recommendation": fit.get("recommendation", ""),
            "fit_level": "strong" if fit.get("match_score", 50) >= 75 else "partial" if fit.get("match_score", 50) >= 50 else "weak"
        }
    except Exception:
        return {
            "job": job,
            "match_score": 50,
            "matched_skills": [],
            "missing_skills": [],
            "recommendation": "Review job details carefully.",
            "fit_level": "partial"
        }

async def scrape_and_score(
    query: str,
    location: str,
    resume_analysis: dict,
    num_results: int = 20,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> list:
    def emit(msg: str):
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    emit(f"Searching for '{query}' jobs in {location}...")

    # Fetch jobs from both sources IN PARALLEL
    jsearch_jobs, adzuna_jobs = await asyncio.gather(
        _fetch_jsearch(query, location),
        _fetch_adzuna(query, location),
        return_exceptions=True
    )

    all_jobs = []
    if isinstance(jsearch_jobs, list): all_jobs.extend(jsearch_jobs)
    if isinstance(adzuna_jobs,  list): all_jobs.extend(adzuna_jobs)

    # Deduplicate by title+company
    seen = set()
    unique_jobs = []
    for j in all_jobs:
        key = f"{j['title'].lower()}:{j['company'].lower()}"
        if key not in seen:
            seen.add(key)
            unique_jobs.append(j)

    # Fallback demo jobs if APIs return nothing
    if not unique_jobs:
        emit("No jobs returned from live APIs, using demo job listings...")
        unique_jobs = _demo_jobs(query)

    emit(f"Found {len(unique_jobs)} jobs. Scoring matches with AI...")

    # Build profile summary once
    skills = resume_analysis.get("skills_found", [])
    level  = resume_analysis.get("experience_level", "junior")
    profile_summary = f"{level} developer with skills: {', '.join(skills[:12])}"

    # Score ALL jobs IN PARALLEL (asyncio.gather)
    scored = await asyncio.gather(*[
        _score_single_job(job, profile_summary)
        for job in unique_jobs[:15]  # cap at 15 for speed
    ], return_exceptions=True)

    # Filter exceptions and sort
    valid = [j for j in scored if isinstance(j, dict)]
    valid.sort(key=lambda x: x.get("match_score", 0), reverse=True)

    emit(f"Scoring complete! Top match: {valid[0]['match_score']}%" if valid else "No results found.")
    return valid

def _demo_jobs(query: str) -> list:
    return [
        {"title": f"Senior {query}", "company": "TechCorp India", "location": "Bangalore",
         "description": f"Looking for a {query} with 2+ years experience in Python and React.",
         "apply_link": "#", "salary": "8-15 LPA", "source": "demo"},
        {"title": f"Junior {query}", "company": "StartupXYZ", "location": "Hyderabad",
         "description": f"Exciting {query} role with AI/ML focus. React, FastAPI, LangChain.",
         "apply_link": "#", "salary": "4-8 LPA", "source": "demo"},
        {"title": f"{query} Engineer", "company": "GlobalTech", "location": "Remote",
         "description": f"Remote {query} position. Python, Docker, AWS, REST APIs required.",
         "apply_link": "#", "salary": "10-20 LPA", "source": "demo"},
    ]
