"""
CareerMind AI — JSearch Tool (RapidAPI)
Primary job search source: https://jsearch.p.rapidapi.com/search
Falls back gracefully when API limit is hit.
"""
import logging

import requests

from config import RAPIDAPI_KEY

logger = logging.getLogger(__name__)

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"
HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}


def _normalize_job(raw: dict) -> dict:
    """Map JSearch job response to our standard schema."""
    return {
        "id": raw.get("job_id", ""),
        "title": raw.get("job_title", "Unknown Role"),
        "company": raw.get("employer_name", "Unknown Company"),
        "location": f"{raw.get('job_city', '')}, {raw.get('job_country', '')}".strip(", "),
        "description": raw.get("job_description", "")[:2000],
        "apply_link": raw.get("job_apply_link", ""),
        "salary": _parse_salary(raw),
        "posted_at": raw.get("job_posted_at_datetime_utc", ""),
        "employment_type": raw.get("job_employment_type", ""),
        "is_remote": raw.get("job_is_remote", False),
        "required_skills": raw.get("job_required_skills", []) or [],
        "source": "jsearch",
    }


def _parse_salary(raw: dict) -> str:
    """Extract a readable salary string."""
    min_s = raw.get("job_min_salary")
    max_s = raw.get("job_max_salary")
    currency = raw.get("job_salary_currency", "USD")
    period = raw.get("job_salary_period", "")

    if min_s and max_s:
        return f"{currency} {int(min_s):,} – {int(max_s):,} / {period}"
    if min_s:
        return f"{currency} {int(min_s):,}+ / {period}"
    return "Not disclosed"


def search_jobs_jsearch(
    query: str,
    location: str = "United States",
    num_results: int = 20,
    page: int = 1,
) -> list[dict]:
    """
    Search for jobs using JSearch API.

    Returns:
        List of normalized job dicts, or empty list on failure.
    """
    if not RAPIDAPI_KEY:
        logger.warning("RAPIDAPI_KEY not set; skipping JSearch")
        return []

    params = {
        "query": f"{query} {location}",
        "page": str(page),
        "num_pages": "1",
        "date_posted": "month",
        "remote_jobs_only": "false",
        "employment_types": "FULLTIME,PARTTIME,INTERN,CONTRACTOR",
    }

    try:
        response = requests.get(JSEARCH_URL, headers=HEADERS, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        jobs = data.get("data", [])
        normalized = [_normalize_job(j) for j in jobs[:num_results]]
        logger.info("JSearch returned %d jobs for query '%s'", len(normalized), query)
        return normalized

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning("JSearch rate limit hit (429); switching to Adzuna")
        else:
            logger.error("JSearch HTTP error: %s", e)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("JSearch request failed: %s", e)
        return []
    except Exception as e:
        logger.error("JSearch unexpected error: %s", e)
        return []
