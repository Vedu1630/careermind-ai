"""
CareerMind AI — SQLite Database Layer
Uses aiosqlite for async operations.
"""
import aiosqlite
import os
import json
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "careermind.db")


async def init_db():
    """Create tables on startup."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id TEXT PRIMARY KEY,
                resume_path TEXT,
                resume_text TEXT,
                resume_analysis TEXT,  -- JSON blob
                job_query TEXT,
                job_location TEXT,
                job_listings TEXT,     -- JSON blob
                selected_job TEXT,     -- JSON blob
                rewritten_resume TEXT, -- JSON blob
                interview_history TEXT, -- JSON blob
                interview_scores TEXT,  -- JSON blob
                current_step TEXT DEFAULT 'idle',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def get_session(user_id: str) -> Optional[dict]:
    """Fetch a session by user_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            data = dict(row)
            # Deserialize JSON blobs
            for json_field in [
                "resume_analysis", "job_listings", "selected_job",
                "rewritten_resume", "interview_history", "interview_scores"
            ]:
                if data.get(json_field):
                    try:
                        data[json_field] = json.loads(data[json_field])
                    except (json.JSONDecodeError, TypeError):
                        data[json_field] = None
            return data


async def upsert_session(user_id: str, **fields) -> None:
    """Create or update session fields."""
    # Serialize JSON fields
    json_fields = [
        "resume_analysis", "job_listings", "selected_job",
        "rewritten_resume", "interview_history", "interview_scores"
    ]
    for f in json_fields:
        if f in fields and not isinstance(fields[f], str) and fields[f] is not None:
            fields[f] = json.dumps(fields[f])

    # Build upsert SQL dynamically
    columns = ["user_id"] + list(fields.keys())
    placeholders = ["?"] * len(columns)
    values = [user_id] + list(fields.values())

    updates = ", ".join(
        f"{col} = excluded.{col}" for col in fields.keys()
    ) + ", updated_at = CURRENT_TIMESTAMP"

    sql = f"""
        INSERT INTO sessions ({', '.join(columns)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT(user_id) DO UPDATE SET {updates}
    """

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, values)
        await db.commit()


async def delete_session(user_id: str) -> None:
    """Remove a session."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await db.commit()
