# agents/mock_interviewer.py
import re
import json
import io
import tempfile
import os
from typing import Optional, List, Dict
from langchain.prompts import ChatPromptTemplate
from core.singletons import get_llm, get_whisper
from gtts import gTTS

def _parse_json_from_llm(raw: str) -> dict:
    """Extract JSON object from LLM output."""
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        raise ValueError("Could not locate JSON object in LLM response.")
    return json.loads(match.group(0))

def generate_question(
    job_title: str,
    round_number: int = 1,
    history: Optional[List[Dict]] = None,
    interview_type: str = "mixed",
    type_instruction: str = "",
    company: str = "",
    level: str = "",
) -> str:
    # Clean up duplicate consecutive words in job_title
    words = job_title.strip().split()
    cleaned_words = []
    for w in words:
        if not cleaned_words or w.lower() != cleaned_words[-1].lower():
            cleaned_words.append(w)
    job_title = " ".join(cleaned_words)

    history = history or []
    history_str = " | ".join(
        h.get("question", "")[:80]
        for h in history[-3:]  # only last 3 for context — less tokens
    )

    prompt = ChatPromptTemplate.from_template("""
You are interviewing for {title}. Round {round}/5. Type: {itype}. {company_ctx} {level_ctx} {instr_ctx}
Previous questions: {history}
Generate the next interview question. Return ONLY the question, nothing else.
Round 1 must be: "Tell me about yourself and why you are interested in this role."
""")
    chain = prompt | get_llm(quality=False)
    result = chain.invoke({
        "title":       job_title,
        "round":       round_number,
        "itype":       interview_type,
        "company_ctx": f"Company: {company}." if company else "",
        "level_ctx":   f"Level: {level}." if level else "",
        "instr_ctx":   f"Instructions: {type_instruction}." if type_instruction else "",
        "history":     history_str or "None",
    })
    return result.content.strip()

def score_answer(question: str, answer_text: str, job_title: str) -> dict:
    if not answer_text or len(answer_text) < 5:
        return {
            "score": 0, "clarity": 0, "relevance": 0,
            "feedback": "No answer detected.",
            "better_answer_hint": "Please speak clearly into your microphone.",
            "filler_count": 0,
            "strengths": [],
            "weaknesses": ["Empty response"],
            "filler_feedback": "No speech detected.",
            "star_coverage": 0
        }

    # Count fillers fast (no regex)
    fillers = ["um", "uh", "like", "basically", "literally", "you know", "i mean"]
    words   = answer_text.lower().split()
    filler_count = sum(words.count(f) for f in fillers)

    prompt = ChatPromptTemplate.from_template("""
Score this interview answer for {title}. Return ONLY valid JSON.
Q: {question}
A: {answer}
Filler words: {fillers}

{{"score":7,"clarity":8,"relevance":7,"feedback":"One sentence feedback.","better_answer_hint":"One sentence hint.","filler_count":{fillers}}}
""")
    chain = prompt | get_llm(quality=False)
    try:
        result = chain.invoke({
            "title":    job_title,
            "question": question[:200],
            "answer":   answer_text[:400],
            "fillers":  filler_count,
        })
        cleaned = re.sub(r"```json|```", "", result.content).strip()
        parsed  = json.loads(cleaned)
        parsed["filler_count"] = filler_count
        parsed.setdefault("strengths", ["Addressed key concepts", "Structured reply cleanly"])
        parsed.setdefault("weaknesses", [])
        parsed.setdefault("filler_feedback", f"Used {filler_count} filler words.")
        parsed.setdefault("star_coverage", 0)
        return parsed
    except Exception:
        return {
            "score": 5, "clarity": 5, "relevance": 5,
            "feedback":          "Could not parse score.",
            "better_answer_hint": "",
            "filler_count":      filler_count,
            "strengths": [],
            "weaknesses": [],
            "filler_feedback": f"Used {filler_count} filler words.",
            "star_coverage": 0
        }

def transcribe_audio(audio_bytes: bytes) -> str:
    """Use singleton Whisper model if available, otherwise fallback to SpeechRecognition."""
    model = get_whisper()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        if model is not None:
            result = model.transcribe(tmp, language="en", fp16=False)
            return result["text"].strip()
        else:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(tmp) as source:
                audio_data = recognizer.record(source)
            return recognizer.recognize_google(audio_data, language="en")
    except Exception as e:
        return f"[Transcription failed: {e}]"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

def text_to_speech(text: str) -> bytes:
    tts = gTTS(text=text[:300], lang="en", slow=False)
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    return buf.getvalue()
