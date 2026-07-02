# backend/core/singletons.py
import os
import logging
from dotenv import load_dotenv
import httpx
from config import CHROMA_DB_DIR, SKILLS_KB_DIR, smart_llm

load_dotenv()
logger = logging.getLogger(__name__)

print("⚡ Initializing singletons (lightweight Groq-only)...")

# Mock elements for compatibility
_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(8.0, connect=3.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)

_cache: dict = {}

def get_llm(quality: bool = False):
    return smart_llm

def get_embeddings():
    return None

def get_whisper():
    return None

def get_skills_retriever(k: int = 4):
    class MockRetriever:
        def invoke(self, text):
            return []
        async def ainvoke(self, text):
            return []
    return MockRetriever()

def get_http_client():
    return _http_client

def get_cache():
    return _cache

import asyncio
from functools import partial

def call_gemini(prompt: str, quality: bool = False) -> str:
    from main import call_gemini
    return call_gemini(prompt)

async def call_gemini_async(prompt: str, quality: bool = False) -> str:
    from main import call_gemini_async
    return await call_gemini_async(prompt)
