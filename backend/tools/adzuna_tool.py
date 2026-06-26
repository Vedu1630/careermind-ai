"""
CareerMind AI — Adzuna Tool
Fallback job source when JSearch rate limit is hit.
API docs: https://developer.adzuna.com/
"""
import logging

import requests

from config import ADZUNA_APP_ID, ADZUNA_APP_KEY

logger = logging.getLogger(__name__)

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_COUNTRY = "us"


def _normalize_job(raw: dict) -> dict:
    """Map Adzuna response to our standard schema."""
    location_data = raw.get("location", {})
    area = location_data.get("area", [])
    location_str = ", ".join(area[-2:]) if area else "Unknown"

    salary_min = raw.get("salary_min", 0)
    salary_max = raw.get("salary_max", 0)
    salary = "Not disclosed"
    if salary_min and salary_max:
        salary = f"USD {int(salary_min):,} – {int(salary_max):,} / year"
    elif salary_min:
        salary = f"USD {int(salary_min):,}+ / year"

    return {
        "id": str(raw.get("id", "")),
        "title": raw.get("title", "Unknown Role"),
        "company": raw.get("company", {}).get("display_name", "Unknown Company"),
        "location": location_str,
        "description": raw.get("description", "")[:2000],
        "apply_link": raw.get("redirect_url", ""),
        "salary": salary,
        "posted_at": raw.get("created", ""),
        "employment_type": raw.get("contract_type", ""),
        "is_remote": False,
        "required_skills": [],
        "source": "adzuna",
    }


def search_jobs_adzuna(
    query: str,
    location: str = "United States",
    num_results: int = 20,
    country: str = DEFAULT_COUNTRY,
) -> list[dict]:
    """
    Search for jobs using Adzuna API.

    Returns:
        List of normalized job dicts, or empty list on failure.
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        logger.warning("Adzuna credentials not set; skipping Adzuna")
        return []

    url = f"{ADZUNA_BASE_URL}/{country}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": min(num_results, 50),
        "what": query,
        "where": location,
        "content-type": "application/json",
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        jobs = data.get("results", [])
        normalized = [_normalize_job(j) for j in jobs[:num_results]]
        logger.info("Adzuna returned %d jobs for query '%s'", len(normalized), query)
        return normalized

    except requests.exceptions.HTTPError as e:
        logger.error("Adzuna HTTP error: %s", e)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("Adzuna request failed: %s", e)
        return []
    except Exception as e:
        logger.error("Adzuna unexpected error: %s", e)
        return []


def get_demo_jobs(query: str, location: str = "United States", num_results: int = 10) -> list[dict]:
    """
    Returns realistic demo jobs dynamically formatted according to the searched location.
    Ensures the app is fully usable and contextually relevant without external API keys.
    """
    loc_lower = location.strip().lower()

    # 1. Look up specific country configurations
    countries_data = {
        "india": {
            "locations": ["Bangalore, India", "Mumbai, India", "Pune, India", "Hyderabad, India", "Delhi NCR, India"],
            "salaries": [
                "INR 18,00,000 – 25,00,000 / year",
                "INR 12,00,000 – 16,00,000 / year",
                "INR 6,00,000 – 9,00,000 / year",
                "INR 45,000 / month",
                "INR 28,00,000 – 38,00,000 / year"
            ],
            "suffix": " India"
        },
        "germany": {
            "locations": ["Berlin, Germany", "Munich, Germany", "Hamburg, Germany", "Frankfurt, Germany", "Stuttgart, Germany"],
            "salaries": [
                "EUR 75,000 – 95,000 / year",
                "EUR 60,000 – 80,000 / year",
                "EUR 45,000 – 55,000 / year",
                "EUR 25 / hour",
                "EUR 110,000 – 140,000 / year"
            ],
            "suffix": " GmbH"
        },
        "canada": {
            "locations": ["Toronto, ON", "Vancouver, BC", "Montreal, QC", "Ottawa, ON", "Calgary, AB"],
            "salaries": [
                "CAD 110,000 – 145,000 / year",
                "CAD 90,000 – 115,000 / year",
                "CAD 65,000 – 80,000 / year",
                "CAD 35 / hour",
                "CAD 160,000 – 200,000 / year"
            ],
            "suffix": " Canada"
        },
        "united kingdom": {
            "locations": ["London, UK", "Manchester, UK", "Edinburgh, UK", "Birmingham, UK", "Bristol, UK"],
            "salaries": [
                "GBP 70,000 – 90,000 / year",
                "GBP 55,000 – 70,000 / year",
                "GBP 35,000 – 45,000 / year",
                "GBP 25 / hour",
                "GBP 100,000 – 130,000 / year"
            ],
            "suffix": " UK"
        },
        "uk": {
            "locations": ["London, UK", "Manchester, UK", "Edinburgh, UK", "Birmingham, UK", "Bristol, UK"],
            "salaries": [
                "GBP 70,000 – 90,000 / year",
                "GBP 55,000 – 70,000 / year",
                "GBP 35,000 – 45,000 / year",
                "GBP 25 / hour",
                "GBP 100,000 – 130,000 / year"
            ],
            "suffix": " UK"
        },
        "australia": {
            "locations": ["Sydney, NSW", "Melbourne, VIC", "Brisbane, QLD", "Perth, WA", "Adelaide, SA"],
            "salaries": [
                "AUD 120,000 – 160,000 / year",
                "AUD 100,000 – 130,000 / year",
                "AUD 75,000 – 95,000 / year",
                "AUD 40 / hour",
                "AUD 180,000 – 230,000 / year"
            ],
            "suffix": " Australia"
        }
    }

    # Check if location matches any of our predefined country keys
    matched_key = None
    for key in countries_data:
        if key in loc_lower:
            matched_key = key
            break

    if matched_key:
        data = countries_data[matched_key]
        locations = data["locations"]
        salaries = data["salaries"]
        suffix = data["suffix"]
    else:
        # Dynamic fallback for custom city/country
        display_loc = location.strip().title()
        locations = [
            f"{display_loc}",
            f"{display_loc} (Remote)",
            f"North {display_loc}",
            f"Central {display_loc}",
            f"South {display_loc}"
        ]
        salaries = [
            "USD 130,000 – 170,000 / year",
            "USD 110,000 – 140,000 / year",
            "USD 75,000 – 95,000 / year",
            "USD 40 / hour",
            "USD 190,000 – 240,000 / year"
        ]
        suffix = f" {display_loc}"

    def make_title(template_prefix: str, template_suffix: str) -> str:
        t = query.strip()
        if template_prefix and not t.lower().startswith(template_prefix.lower()):
            t = f"{template_prefix} {t}"
        if template_suffix:
            t_lower = t.lower()
            job_nouns = ["engineer", "developer", "dev", "programmer", "analyst", "consultant", "specialist", "architect", "manager", "lead", "intern", "practitioner"]
            has_job_noun = any(t_lower.endswith(noun) for noun in job_nouns)
            if not has_job_noun:
                t = f"{t} {template_suffix}"
        return t

    demo_jobs = [
        {
            "id": "demo-1",
            "title": make_title("Senior", "Engineer"),
            "company": f"TechCorp AI{suffix}",
            "location": locations[0],
            "description": (
                f"We are looking for an experienced {query} to join our AI team. "
                "You will work on cutting-edge machine learning systems, design scalable "
                "architectures, and collaborate with cross-functional teams. "
                "Required: 3+ years experience, Python, and strong communication skills."
            ),
            "apply_link": "https://example.com/apply",
            "salary": salaries[0],
            "posted_at": "2024-01-15",
            "employment_type": "FULLTIME",
            "is_remote": True,
            "required_skills": ["Python", "Machine Learning", "FastAPI", "Docker"],
            "source": "demo",
        },
        {
            "id": "demo-2",
            "title": f"{make_title('', 'Developer')} — Remote",
            "company": f"InnovateTech{suffix}",
            "location": locations[1],
            "description": (
                f"Join our growing team as a {query}. "
                "Build and deploy AI-powered features, optimize model inference, "
                "and maintain production ML pipelines. "
                "We value curiosity, ownership, and continuous learning."
            ),
            "apply_link": "https://example.com/apply",
            "salary": salaries[1],
            "posted_at": "2024-01-14",
            "employment_type": "FULLTIME",
            "is_remote": True,
            "required_skills": ["Python", "LangChain", "React", "SQL"],
            "source": "demo",
        },
        {
            "id": "demo-3",
            "title": make_title("Junior", "Engineer"),
            "company": f"StartupHub{suffix}",
            "location": locations[2],
            "description": (
                f"Exciting opportunity for a Junior {query} at a fast-growing startup. "
                "Work directly with senior engineers to build AI features, "
                "contribute to open-source projects, and grow your skills rapidly."
            ),
            "apply_link": "https://example.com/apply",
            "salary": salaries[2],
            "posted_at": "2024-01-13",
            "employment_type": "FULLTIME",
            "is_remote": False,
            "required_skills": ["Python", "Git", "REST APIs", "Docker"],
            "source": "demo",
        },
        {
            "id": "demo-4",
            "title": f"{make_title('', 'Intern')} — Summer 2024",
            "company": f"BigTech Solutions{suffix}",
            "location": locations[3],
            "description": (
                f"12-week paid internship for aspiring {query} professionals. "
                "Work on real projects, get mentored by senior engineers, "
                "and potentially receive a full-time offer."
            ),
            "apply_link": "https://example.com/apply",
            "salary": salaries[3],
            "posted_at": "2024-01-12",
            "employment_type": "INTERN",
            "is_remote": False,
            "required_skills": ["Python", "Machine Learning basics", "SQL"],
            "source": "demo",
        },
        {
            "id": "demo-5",
            "title": make_title("Staff", "Engineer"),
            "company": f"Enterprise AI Corp{suffix}",
            "location": locations[4],
            "description": (
                f"Lead-level {query} role. Drive architectural decisions, "
                "mentor junior engineers, define technical roadmaps, and deliver "
                "high-impact AI systems at scale."
            ),
            "apply_link": "https://example.com/apply",
            "salary": salaries[4],
            "posted_at": "2024-01-11",
            "employment_type": "FULLTIME",
            "is_remote": True,
            "required_skills": ["Python", "LangGraph", "System Design", "MLOps", "Leadership"],
            "source": "demo",
        },
    ]
    return demo_jobs[:num_results]
