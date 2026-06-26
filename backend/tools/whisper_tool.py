"""
CareerMind AI — Speech-to-Text Tool
Primary: openai-whisper (if available, Python 3.11+)
Fallback: SpeechRecognition with Google Speech API (Python 3.9 compatible)
"""
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# ── Try Whisper first ─────────────────────────────────────────────────────
_whisper_model = None
_whisper_available = False


def _try_load_whisper():
    global _whisper_model, _whisper_available
    try:
        import whisper
        logger.info("Loading Whisper 'base' model...")
        _whisper_model = whisper.load_model("base")
        _whisper_available = True
        logger.info("Whisper loaded successfully")
    except (ImportError, Exception) as e:
        logger.info("Whisper not available (%s), using SpeechRecognition fallback", type(e).__name__)
        _whisper_available = False


def transcribe_audio(audio_bytes: bytes, language: str = "en") -> str:
    """
    Transcribe audio bytes to text.
    Tries Whisper first, falls back to SpeechRecognition (Google Speech API).

    Args:
        audio_bytes: Raw audio data (webm, wav, etc.)
        language: Language code (default: 'en')

    Returns:
        Transcribed text, or empty string on failure.
    """
    # ── Option 1: Whisper (if available) ──────────────────────────────────
    if _whisper_available and _whisper_model is not None:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            result = _whisper_model.transcribe(tmp_path, language=language, fp16=False)
            text = result.get("text", "").strip()
            logger.info("Whisper transcribed %d chars", len(text))
            return text
        except Exception as e:
            logger.error("Whisper transcription failed: %s", e)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ── Option 2: SpeechRecognition (Google Speech API, free) ─────────────
    try:
        import speech_recognition as sr

        recognizer = sr.Recognizer()

        # Write bytes to temp file then load as AudioFile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with sr.AudioFile(tmp_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=language)
            logger.info("SpeechRecognition transcribed: %s", text[:80])
            return text
        except sr.UnknownValueError:
            logger.warning("SpeechRecognition: Could not understand audio")
            return ""
        except sr.RequestError as e:
            logger.error("SpeechRecognition API error: %s", e)
            return ""
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except ImportError:
        logger.warning("SpeechRecognition not installed")
        return "[Speech-to-text unavailable — install SpeechRecognition]"
    except Exception as e:
        logger.error("STT failed: %s", e)
        return ""


def is_whisper_available() -> bool:
    return _whisper_available


# Try to load Whisper on startup (non-blocking)
try:
    _try_load_whisper()
except Exception:
    pass
