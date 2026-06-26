// hooks/useVoiceRecorder.js
import { useState, useRef, useEffect, useCallback } from "react";

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

export function useVoiceRecorder() {
  const [isRecording, setIsRecording]     = useState(false);
  const [transcript, setTranscript]       = useState("");
  const [interimText, setInterimText]     = useState("");
  const [durationSeconds, setDuration]    = useState(0);
  const [isSupported]                     = useState(() => !!SpeechRecognition);
  const [error, setError]                 = useState(null);

  const recognitionRef = useRef(null);
  const timerRef       = useRef(null);
  const finalRef       = useRef("");  // accumulates final transcript segments

  const startRecording = useCallback(() => {
    if (!isSupported) {
      setError("Speech recognition not supported. Please use Chrome or Edge.");
      return;
    }

    setError(null);
    setTranscript("");
    setInterimText("");
    setDuration(0);
    finalRef.current = "";

    const recognition = new SpeechRecognition();
    recognition.continuous      = true;   // keep listening until stopped
    recognition.interimResults  = true;   // show partial results live
    recognition.lang            = "en-US";
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsRecording(true);
      timerRef.current = setInterval(() => {
        setDuration(d => d + 1);
      }, 1000);
    };

    recognition.onresult = (event) => {
      let interim = "";
      let final   = finalRef.current;

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript + " ";
          finalRef.current = final;
        } else {
          interim += result[0].transcript;
        }
      }

      setTranscript(final.trim());
      setInterimText(interim);
    };

    recognition.onerror = (event) => {
      if (event.error === "no-speech") return; // ignore no-speech, keep listening
      if (event.error === "aborted")   return; // user stopped
      setError(`Microphone error: ${event.error}. Please allow microphone access.`);
      setIsRecording(false);
      clearInterval(timerRef.current);
    };

    recognition.onend = () => {
      setIsRecording(false);
      setInterimText("");
      clearInterval(timerRef.current);
      // Set final transcript from accumulated ref
      setTranscript(finalRef.current.trim());
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [isSupported]);

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    clearInterval(timerRef.current);
    setIsRecording(false);
    setInterimText("");
  }, []);

  const resetRecording = useCallback(() => {
    stopRecording();
    setTranscript("");
    setInterimText("");
    setDuration(0);
    finalRef.current = "";
    setError(null);
  }, [stopRecording]);

  useEffect(() => {
    return () => {
      if (recognitionRef.current) recognitionRef.current.abort();
      clearInterval(timerRef.current);
    };
  }, []);

  return {
    startRecording,
    stopRecording,
    resetRecording,
    transcript,      // final confirmed transcript
    interimText,     // live partial text while speaking
    isRecording,
    durationSeconds,
    isSupported,
    error,
    // Keep audioBlob as null — not needed anymore
    audioBlob: transcript ? new Blob([transcript], { type: "text/plain" }) : null
  };
}
