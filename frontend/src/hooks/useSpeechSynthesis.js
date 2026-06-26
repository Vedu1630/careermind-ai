import { useEffect, useRef, useState, useCallback } from "react";

export function useSpeechSynthesis() {
  const [voices, setVoices] = useState([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isSupported] = useState(() => typeof window !== "undefined" && "speechSynthesis" in window);
  const utteranceRef = useRef(null);

  useEffect(() => {
    if (!isSupported) return;

    const loadVoices = () => {
      const available = window.speechSynthesis.getVoices();
      if (available.length > 0) setVoices(available);
    };

    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      window.speechSynthesis.cancel();
    };
  }, [isSupported]);

  const findBestVoice = useCallback((preferredNames, lang) => {
    if (voices.length === 0) return null;

    // Try preferred voices first (exact name match)
    for (const name of preferredNames) {
      const match = voices.find(v =>
        v.name.toLowerCase().includes(name.toLowerCase())
      );
      if (match) return match;
    }

    // Fallback: any voice matching the language
    const langMatch = voices.find(v => v.lang.startsWith(lang.split('-')[0]));
    if (langMatch) return langMatch;

    // Final fallback: first available voice
    return voices[0];
  }, [voices]);

  const speak = useCallback((text, voiceProfile, onStart, onEnd) => {
    if (!isSupported) return;

    // Cancel any ongoing speech
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);

    // Apply voice profile settings
    const voice = findBestVoice(voiceProfile.preferredVoiceNames, voiceProfile.lang);
    if (voice) utterance.voice = voice;

    utterance.pitch  = voiceProfile.pitch;
    utterance.rate   = voiceProfile.rate;
    utterance.volume = 1.0;
    utterance.lang   = voiceProfile.lang;

    utterance.onstart = () => {
      setIsSpeaking(true);
      onStart?.();
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      onEnd?.();
    };

    utterance.onerror = () => {
      setIsSpeaking(false);
      onEnd?.();
    };

    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, [isSupported, findBestVoice]);

  const stop = useCallback(() => {
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, []);

  const pause = useCallback(() => {
    window.speechSynthesis.pause();
  }, []);

  const resume = useCallback(() => {
    window.speechSynthesis.resume();
  }, []);

  return { speak, stop, pause, resume, isSpeaking, isSupported, voices };
}
