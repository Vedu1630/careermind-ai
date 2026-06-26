"""
CareerMind AI — Mock Interviewer Agent
Generates interview questions, scores answers, and produces TTS audio.
"""
import base64
import io
import json
import logging
import re
from typing import Optional, List, Dict

from config import llm

logger = logging.getLogger(__name__)


def _parse_json_from_llm(raw: str) -> dict:
    """Extract JSON object from LLM output."""
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        raise ValueError("Could not locate JSON object in LLM response.")
    return json.loads(match.group(0))


# ── Question types by round ────────────────────────────────────────────────────
ROUND_TEMPLATES = {
    1: "behavioral and motivation questions",
    2: "technical and skill assessment questions",
    3: "problem-solving and scenario-based questions",
    4: "leadership, collaboration, and situational questions",
    5: "advanced technical deep-dive questions",
}


def generate_question(
    job_title: str,
    round_number: int = 1,
    history: Optional[List[Dict]] = None,
    interview_type: str = "mixed",
    type_instruction: str = "",
    company: str = "",
    level: str = "",
) -> str:
    """
    Generate the next interview question based on job title, round, and history.
    Questions progressively increase in difficulty each round.
    Tailored to interview type and company/level if provided.
    """
    # Clean up duplicate consecutive words in job_title (e.g. "Software Engineer Engineer" -> "Software Engineer")
    words = job_title.strip().split()
    cleaned_words = []
    for w in words:
        if not cleaned_words or w.lower() != cleaned_words[-1].lower():
            cleaned_words.append(w)
    job_title = " ".join(cleaned_words)

    # Build company context if provided
    company_context = ""
    if company and company.strip():
        company_context = f"""
Target company: {company} — Level: {level or 'not specified'}
Tailor your questions to match {company}'s known interview style and culture.
For example:
- Google/FAANG: focus on algorithms, system design at scale, impact stories
- Goldman Sachs/Finance: focus on analytical thinking, risk awareness, market knowledge  
- Startups: focus on ownership, scrappiness, speed, wearing many hats
- TCS/Infosys/Wipro: focus on fundamentals, process adherence, client communication
"""

    history = history or []

    # Build conversation history context to make it conversational and allow follow-ups
    previous_questions = ""
    if history:
        previous_questions = "\nHere is the conversation history of this interview so far:\n"
        for idx, entry in enumerate(history):
            previous_questions += f"Interviewer: {entry.get('question', '')}\n"
            previous_questions += f"Candidate: {entry.get('answer', '')}\n\n"

    # Define prompt
    prompt = f"""You are a senior recruiter and technical interviewer conducting a {interview_type} interview for a {job_title} position.

Interview type instruction: {type_instruction or 'Mix behavioural, technical, and HR questions in a realistic interview pattern.'}
{company_context}

This is round {round_number} of 5 of the interview.
{previous_questions}

Round 1: Always start with "Tell me about yourself and why you are interested in this role."
Round 2-3: Core questions matching the interview type
Round 4: Harder, more specific question
Round 5: Final question — either a tough challenge or a "do you have any questions for us?"

Rules for generating the question:
- Never repeat a question already asked
- Make questions progressively harder each round
- Keep questions specific to {job_title} role
- Speak directly to the candidate in the first person (e.g. "Welcome!", "Let's start...", "Building on that..."). Keep it conversational, warm, and natural.
- Return ONLY the interviewer's spoken words. Do not include any numbering, round titles, quotes, or preamble.

Generate the round {round_number} question now."""

    try:
        response = llm.invoke(prompt)
        question = response.content if hasattr(response, "content") else str(response)
        question = question.strip().strip('"').strip("'")
        logger.info("Generated round %d question for %s", round_number, job_title)
        return question
    except Exception as e:
        logger.error("Question generation failed: %s", e)
        # Fallback questions designed to follow a realistic conversational path
        fallbacks = {
            1: f"Welcome! Let's start the interview. Could you please introduce yourself, walk me through your background, and explain why you're interested in the {job_title} role?",
            2: f"Thanks for introducing yourself. To transition into technical skills: What are the core technologies you bring to this {job_title} position, and how have you applied them?",
            3: "That makes sense. Now, let's discuss problem-solving. Can you describe a particularly challenging technical problem you solved, and the architectural choices you made?",
            4: "Building on that, let's talk about teamwork. How do you handle disagreements with teammates or stakeholders on technical decisions?",
            5: f"For our final round, I'd like to do a deep dive. Can you design a scalable system or describe how you would architect a core service for a {job_title} domain under high load?",
        }
        return fallbacks.get(round_number, f"Why are you a good fit for the {job_title} role?")


def is_behavioural_question(question: str) -> bool:
    """Helper to detect if a question is behavioural."""
    behav_keywords = [
        "tell me about a time", "describe a situation", "give me an example",
        "how did you handle", "when have you", "have you ever",
        "what would you do", "walk me through", "how do you deal",
        "tell me when you", "describe how you"
    ]
    q_lower = question.lower()
    return any(kw in q_lower for kw in behav_keywords)


def _heuristic_answer_scorer(question: str, answer_text: str, job_title: str) -> dict:
    """Fallback answer scorer that evaluates answers programmatically using heuristics."""
    words = answer_text.strip().split()
    word_count = len(words)

    action_words = ["solved", "designed", "optimized", "built", "spearheaded", "developed", "implemented", "resolved", "wrote", "created", "led", "managed", "collaborated", "architected"]
    impact_words = ["percent", "increased", "decreased", "improved", "optimized", "metrics", "reduced", "saved", "achieved", "%", "seconds", "minutes", "hours", "days", "dollars", "revenue"]

    actions_found = [w for w in action_words if re.search(rf"\b{re.escape(w)}", answer_text, re.IGNORECASE)]
    impact_found = [w for w in impact_words if re.search(rf"\b{re.escape(w)}", answer_text, re.IGNORECASE)]

    # Word overlap with question
    question_words = set(re.findall(r"\b\w{4,}\b", question.lower()))
    answer_words_set = set(re.findall(r"\b\w{4,}\b", answer_text.lower()))
    overlap = len(question_words.intersection(answer_words_set))

    # Compute score
    if word_count < 10:
        base_score = 3
    elif word_count < 25:
        base_score = 5
    elif word_count < 60:
        base_score = 7
    else:
        base_score = 8

    if actions_found:
        base_score += 1
    if impact_found:
        base_score += 1
    if overlap >= 3:
        base_score += 1

    score = min(max(base_score, 1), 9)
    clarity = min(max(int(6 + (word_count > 30) * 2), 2), 9)
    relevance = min(max(int(4 + min(overlap, 4) + (word_count > 15) * 1), 2), 10)

    # Count fillers
    filler_words = ["um", "uh", "like", "basically", "literally", "kind of", "sort of", "i mean", "you know"]
    words_lower = re.findall(r"\b\w+\b", answer_text.lower())
    filler_count = 0
    for filler in filler_words:
        if " " in filler:
            filler_count += len(re.findall(rf"\b{re.escape(filler)}\b", answer_text.lower()))
        else:
            filler_count += words_lower.count(filler)

    if filler_count > 5:
        filler_feedback = f"You used around {filler_count} filler words (like 'um' or 'like'). Try pausing instead of using fillers to sound more confident."
    else:
        filler_feedback = "Your pacing was natural with minimal filler word usage. Great communication style!"

    # STAR coverage check
    is_behav = is_behavioural_question(question)
    star_coverage = 0
    if is_behav:
        has_s = any(w in answer_text.lower() for w in ["when", "project", "team", "company", "system", "at", "role", "time", "background"])
        has_t = any(w in answer_text.lower() for w in ["task", "goal", "challenge", "problem", "issue", "responsibility", "bug", "requirement"])
        has_a = len(actions_found) >= 1
        has_r = len(impact_found) >= 1 or any(c.isdigit() for c in answer_text)
        star_coverage = sum([has_s, has_t, has_a, has_r])

    strengths = []
    weaknesses = []

    if len(actions_found) >= 2:
        strengths.append("Demonstrated strong ownership with active verbs")
    elif word_count > 35:
        strengths.append("Provided a detailed explanation of your approach")

    if impact_found:
        strengths.append("Quantified your impact with clear metrics or outcomes")
    else:
        weaknesses.append("Missing quantifiable results (e.g., performance gains, time saved)")

    if overlap >= 2:
        strengths.append("Directly addressed key concepts from the question")
    else:
        weaknesses.append("Could tie your answer more closely to the core question requirements")

    if word_count < 25:
        weaknesses.append("Response was too brief; expand on your technical implementation")

    if not strengths:
        strengths = ["Structured your answer cleanly", "Shared relevant technical background"]
    if not weaknesses:
        weaknesses = ["Add a specific trade-off analysis to show deeper thinking"]

    feedback_parts = []
    if word_count < 20:
        feedback_parts.append("Your response was brief, which makes it hard to evaluate your skills.")
        feedback_parts.append("Try to expand your answers by explaining the context, your action, and the final result.")
    else:
        feedback_parts.append(f"You did a good job explaining your experience as a {job_title}.")
        if actions_found:
            feedback_parts.append(f"It was great to hear how you {', '.join(actions_found[:2])} solutions.")
        if impact_found:
            feedback_parts.append("Your inclusion of concrete outcomes strengthens your credibility.")
        else:
            feedback_parts.append("To take this to the next level, highlight the positive impact of your work with metrics.")

    feedback = " ".join(feedback_parts)

    better_answer_hint = (
        "To structure a stronger response, use the STAR method: "
        "1. Situation: Describe the project context (1 sentence). "
        "2. Task: Outline the specific challenge you faced (1 sentence). "
        "3. Action: Explain the tools and architectural choices you made (2-3 sentences). "
        "4. Result: Conclude with a measurable outcome (e.g., 'reducing API latency by 15%')."
    )

    result = {
        "score": score,
        "clarity": clarity,
        "relevance": relevance,
        "feedback": feedback,
        "better_answer_hint": better_answer_hint,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "filler_count": filler_count,
        "filler_feedback": filler_feedback,
        "is_fallback": True
    }
    if is_behav:
        result["star_coverage"] = star_coverage
    return result


def score_answer(
    question: str,
    answer_text: str,
    job_title: str,
) -> dict:
    """
    Score a candidate's answer using Gemini, including filler word counting,
    clarity penalty, and STAR coverage checks.
    """
    if not answer_text.strip():
        return {
            "score": 0,
            "clarity": 0,
            "relevance": 0,
            "feedback": "No answer provided.",
            "better_answer_hint": "Please speak clearly into your microphone and try again.",
            "strengths": [],
            "weaknesses": ["Empty answer"],
            "filler_count": 0,
            "filler_feedback": "No speech detected.",
            "star_coverage": 0
        }

    # Count fillers in the answer text
    filler_words = ["um", "uh", "like", "basically", "literally",
                    "kind of", "sort of", "i mean", "you know"]
    words_lower = re.findall(r"\b\w+\b", answer_text.lower())
    filler_count = 0
    for filler in filler_words:
        if " " in filler:
            filler_count += len(re.findall(rf"\b{re.escape(filler)}\b", answer_text.lower()))
        else:
            filler_count += words_lower.count(filler)
    
    filler_penalty = min(2, filler_count // 3)

    is_behav = is_behavioural_question(question)
    star_instruction = ""
    star_coverage_part = ""
    if is_behav:
        star_instruction = """
Additionally, check if the answer follows the STAR method:
- Did they describe the Situation? (yes/no)
- Did they describe the Task? (yes/no)  
- Did they describe specific Actions? (yes/no)
- Did they describe measurable Results? (yes/no)
Add "star_coverage": <integer 0-4> to your JSON (number of STAR parts covered).
"""
        star_coverage_part = ' ,"star_coverage": <integer 0-4>'

    prompt = f"""Score this interview answer for a {job_title} position.

Question: {question}
Answer: {answer_text}

Note: The candidate used approximately {filler_count} filler words (um, uh, like, etc.).
Apply a small penalty to clarity score if filler usage is excessive (more than 5 fillers).

{star_instruction}

Return ONLY valid JSON with these exact keys (no markdown, no extra text):
{{
  "score": <integer 1-10>,
  "clarity": <integer 1-10>,
  "relevance": <integer 1-10>,
  "feedback": "<one constructive sentence>",
  "better_answer_hint": "<one sentence on how to improve>",
  "filler_feedback": "<one sentence about communication style, mention fillers if count > 3>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>"]{star_coverage_part}
}}
"""

    try:
        response = llm.invoke(prompt)
        raw_output = response.content if hasattr(response, "content") else str(response)
        result = _parse_json_from_llm(raw_output)

        scored = {
            "score": max(1, min(10, int(result.get("score", 5)))),
            "clarity": max(1, min(10, int(result.get("clarity", 5)) - filler_penalty)),
            "relevance": max(1, min(10, int(result.get("relevance", 5)))),
            "feedback": result.get("feedback", "Good attempt. Keep practicing."),
            "better_answer_hint": result.get("better_answer_hint", "Add specific examples and metrics."),
            "strengths": result.get("strengths", []),
            "weaknesses": result.get("weaknesses", []),
            "filler_count": filler_count,
            "filler_feedback": result.get("filler_feedback", "Good communication style."),
        }
        if is_behav:
            scored["star_coverage"] = max(0, min(4, int(result.get("star_coverage", 0))))
        return scored
    except Exception as e:
        logger.warning("Answer scoring failed, falling back to heuristic scorer: %s", e)
        fallback_res = _heuristic_answer_scorer(question, answer_text, job_title)
        fallback_res["filler_count"] = filler_count
        fallback_res["clarity"] = max(1, fallback_res["clarity"] - filler_penalty)
        return fallback_res
