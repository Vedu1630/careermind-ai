import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Mic, MicOff, Volume2, VolumeX, RotateCcw, ChevronRight, AlertCircle,
  Award, Target, CheckCircle, Brain, Sparkles, ShieldAlert, Clock, Printer
} from "lucide-react";
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";
import { useSpeechSynthesis } from "../hooks/useSpeechSynthesis";
import { useVoiceRecorder } from "../hooks/useVoiceRecorder";
import useStore from "../store/useStore";
import api, { getUserId } from "../lib/api";

const VOICE_PROFILES = [
  {
    id: "male",
    label: "Alex",
    description: "Direct and technical. Focuses on system design and problem-solving depth.",
    avatar: "👨‍💼",
    pitch: 0.85,
    rate: 0.92,
    lang: "en-US",
    preferredVoiceNames: ["Google UK English Male", "Microsoft David", "Alex", "Daniel", "en-GB-Standard-B"]
  },
  {
    id: "female",
    label: "Lucy",
    description: "Warm but rigorous. Probes behavioral patterns and communication skills.",
    avatar: "👩‍💼",
    pitch: 1.1,
    rate: 0.9,
    lang: "en-US",
    preferredVoiceNames: ["Google UK English Female", "Microsoft Zira", "Samantha", "Karen", "Victoria", "en-US-Standard-C"]
  }
];

const INTERVIEW_TYPES = [
  {
    id: "behavioural",
    label: "Behavioural",
    icon: "🧠",
    description: "STAR method, past experience, leadership, conflict resolution",
    example: "Tell me about a time you failed and what you learned.",
    color: "indigo",
    prompt_instruction: "Ask behavioural questions using STAR method framework. Focus on past experiences, leadership, teamwork, conflict resolution, and growth mindset."
  },
  {
    id: "technical",
    label: "Technical",
    icon: "⚙️",
    description: "DSA, system design, coding concepts, architecture decisions",
    example: "How would you design a URL shortener that handles 1M requests/day?",
    color: "cyan",
    prompt_instruction: "Ask technical questions about algorithms, data structures, system design, architecture, and coding best practices relevant to the job role."
  },
  {
    id: "hr",
    label: "HR & Culture",
    icon: "🤝",
    description: "Motivation, values, career goals, salary, culture fit",
    example: "Where do you see yourself in 5 years?",
    color: "emerald",
    prompt_instruction: "Ask HR questions about motivation, career aspirations, company values alignment, salary expectations, work style, and cultural fit."
  },
  {
    id: "mixed",
    label: "Mixed (Real)",
    icon: "🎯",
    description: "Realistic mix of all types — closest to an actual interview",
    example: "Mix of technical, behavioural, and HR questions as a real interview would have.",
    color: "amber",
    prompt_instruction: "Mix behavioural, technical, and HR questions in a realistic interview pattern. Start with introduction, move to technical depth, include one behavioural, end with HR/culture questions."
  }
];

const FILLER_WORDS = [
  "um", "uh", "uhh", "umm", "like", "you know", "basically",
  "literally", "actually", "kind of", "sort of", "i mean",
  "right", "so", "well", "okay so", "yeah so"
];

const detectFillers = (text) => {
  const textLower = text.toLowerCase();
  const found = [];
  let count = 0;
  FILLER_WORDS.forEach(filler => {
    const regex = new RegExp(`\\b${filler}\\b`, "gi");
    const matches = textLower.match(regex);
    if (matches) {
      count += matches.length;
      found.push({ word: filler, count: matches.length });
    }
  });
  return { count, found };
};

const calculateConfidence = (text, fillerCount) => {
  if (!text || text.length < 10) return 100;
  const wordCount = text.split(" ").length;
  const fillerRatio = fillerCount / Math.max(wordCount, 1);
  const lengthScore = Math.min(60, wordCount * 2);
  const fillerPenalty = Math.min(40, fillerRatio * 200);
  const confidence = 80 + (lengthScore / 3) - fillerPenalty;
  return Math.max(0, Math.min(100, Math.round(confidence)));
};

const ACKNOWLEDGEMENTS = {
  high: [
    "That's a great point. Let me evaluate your response.",
    "Very interesting. I appreciate the detail there.",
    "Good answer. I'm noting that down.",
    "That's exactly the kind of thinking we look for.",
    "Excellent. Thank you for walking me through that."
  ],
  mid: [
    "I see. Thank you for sharing that.",
    "Okay, noted. Let me assess your response.",
    "Interesting perspective. Let me think about that.",
    "Right, thank you. I have a few thoughts on that.",
    "I understand. Let me evaluate what you've shared."
  ],
  low: [
    "I see. Thank you for your answer.",
    "Okay. Let me take note of that.",
    "Alright. I'll assess your response.",
    "Thank you. Let me think about that.",
    "I understand. Moving forward."
  ]
};

export default function MockInterview() {
  const { jobs } = useStore();
  const selectedJob = jobs?.selectedJob;

  // Phase state: "voice_select" | "type_select" | "briefing" | "interview" | "complete"
  const [phase, setPhase]                     = useState("voice_select");

  // Selection states
  const [selectedVoice, setSelectedVoice]     = useState(null);
  const [interviewType, setInterviewType]     = useState(null);
  const [targetCompany, setTargetCompany]     = useState("");
  const [targetLevel, setTargetLevel]         = useState("");
  const [voicesEmpty, setVoicesEmpty]         = useState(false);

  // Briefing countdown
  const [briefingCountdown, setBriefingCountdown] = useState(30);

  // Interview state
  const [round, setRound]                     = useState(1);
  const [question, setQuestion]             = useState("");
  const [history, setHistory]               = useState([]);
  const [scoreCard, setScoreCard]           = useState(null);
  const [aiState, setAiState]               = useState("idle");
  const [isMuted, setIsMuted]               = useState(false);

  // Follow-up states
  const [isFollowUp, setIsFollowUp]         = useState(false);
  const [followUpQuestion, setFollowUpQuestion] = useState("");
  const [followUpAnswered, setFollowUpAnswered] = useState(false);
  const [loadingFollowUp, setLoadingFollowUp] = useState(false);

  // Live fillers and confidence states
  const [fillerData, setFillerData]         = useState({ count: 0, found: [] });
  const [confidenceScore, setConfidenceScore] = useState(100);

  // Timer states
  const [answerTimeLeft, setAnswerTimeLeft]   = useState(120);
  const [timerActive, setTimerActive]         = useState(false);
  const answerTimerRef                       = useRef(null);

  // Report card state
  const [geminiReport, setGeminiReport]       = useState(null);

  // Helper to resolve job title using user targetLevel override
  const getEffectiveJobTitle = useCallback(() => {
    const baseTitle = selectedJob?.title || "Software Engineer";
    if (!targetLevel || !targetLevel.trim()) return baseTitle;
    
    const levelClean = targetLevel.trim();
    const levelLower = levelClean.toLowerCase();
    
    // If the level already specifies a full role, use it directly
    const roleKeywords = ["sde", "engineer", "developer", "programmer", "analyst", "manager", "designer", "architect", "consultant", "lead"];
    if (roleKeywords.some(kw => levelLower.includes(kw))) {
      return levelClean;
    }
    
    // Otherwise, strip seniority prefixes from the job title and prepend the level
    const seniorityPrefixes = ["senior", "junior", "lead", "staff", "principal", "entry-level", "entry level", "mid-level", "mid level", "intern", "associate"];
    let finalBase = baseTitle;
    const finalBaseLower = finalBase.toLowerCase();
    for (const prefix of seniorityPrefixes) {
      if (finalBaseLower.startsWith(prefix)) {
        finalBase = finalBase.substring(prefix.length).trim();
        break;
      }
    }
    
    return `${levelClean} ${finalBase}`;
  }, [selectedJob, targetLevel]);

  const TOTAL_ROUNDS = 5;

  const { speak, stop, isSpeaking }   = useSpeechSynthesis();
  const {
    startRecording,
    stopRecording,
    resetRecording,
    transcript,
    interimText,
    isRecording,
    durationSeconds,
    isSupported: micSupported,
    error: micError
  } = useVoiceRecorder();

  // Check if voices list is empty after 2 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        const available = window.speechSynthesis.getVoices();
        if (available.length === 0) {
          setVoicesEmpty(true);
        }
      } else {
        setVoicesEmpty(true);
      }
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  // ── Pre-Interview Briefing Speech & Timer ───────────────────────────
  useEffect(() => {
    if (phase !== "briefing") return;

    const companyName = targetCompany.strip ? targetCompany.strip() : targetCompany;
    const resolvedCompany = companyName || selectedJob?.company || "this company";
    const jobTitle = getEffectiveJobTitle();

    const briefingText = `Welcome to your ${jobTitle} interview at ${resolvedCompany}. 
      Today we'll go through 5 rounds covering behavioural and technical questions. 
      I'll be evaluating your communication, technical knowledge, and problem solving approach. 
      Take your time with each answer. When you're ready, click Start Interview.`;

    if (!isMuted && selectedVoice) {
      speak(briefingText, selectedVoice, () => {}, () => {});
    }

    const timer = setInterval(() => {
      setBriefingCountdown(c => {
        if (c <= 1) {
          clearInterval(timer);
          return 0;
        }
        return c - 1;
      });
    }, 1000);

    return () => {
      clearInterval(timer);
      stop();
    };
  }, [phase]);

  // ── Live Filler Word Detector + Confidence Meter ────────────────────
  const fullLiveText = (transcript + " " + interimText).trim();

  useEffect(() => {
    if (!isRecording) return;
    const { count, found } = detectFillers(fullLiveText);
    setFillerData({ count, found });
    const score = calculateConfidence(fullLiveText, count);
    setConfidenceScore(score);
  }, [fullLiveText, isRecording]);

  // ── Answer Time Limit Countdown Timer ──────────────────────────────
  const startAnswerTimer = () => {
    setAnswerTimeLeft(120);
    setTimerActive(true);
    answerTimerRef.current = setInterval(() => {
      setAnswerTimeLeft(t => {
        if (t <= 1) {
          clearInterval(answerTimerRef.current);
          setTimerActive(false);
          // Auto-submit whatever transcript we have
          handleSubmitAnswer();
          return 0;
        }
        return t - 1;
      });
    }, 1000);
  };

  const stopAnswerTimer = () => {
    if (answerTimerRef.current) {
      clearInterval(answerTimerRef.current);
    }
    setTimerActive(false);
  };

  // Start timer when listening begins
  useEffect(() => {
    if (aiState === "listening") {
      startAnswerTimer();
    } else {
      stopAnswerTimer();
    }
    return () => stopAnswerTimer();
  }, [aiState]);

  // Spoken warning at 30 seconds
  useEffect(() => {
    if (answerTimeLeft === 30 && timerActive && !isMuted && selectedVoice) {
      speak("30 seconds remaining. Please wrap up your answer.", selectedVoice, () => {}, () => {});
    }
  }, [answerTimeLeft, timerActive, isMuted, selectedVoice, speak]);

  // ── Verbal Acknowledgements Between Answers ───────────────────────
  const speakAcknowledgement = (score) => {
    if (isMuted || !selectedVoice) return;
    const tier = score >= 7 ? "high" : score >= 4 ? "mid" : "low";
    const options = ACKNOWLEDGEMENTS[tier];
    const phrase = options[Math.floor(Math.random() * options.length)];
    speak(phrase, selectedVoice, () => {}, () => {});
  };

  // ── Heuristic check if question is behavioural ─────────────────────
  const isBehaviouralQuestion = (q) => {
    if (!q) return false;
    const behavKeywords = [
      "tell me about a time", "describe a situation", "give me an example",
      "how did you handle", "when have you", "have you ever",
      "what would you do", "walk me through", "how do you deal",
      "tell me when you", "describe how you"
    ];
    const qLower = q.toLowerCase();
    return behavKeywords.some(kw => qLower.includes(kw));
  };

  // ── Fetch question ─────────────────────────────────────────────────
  const fetchNextQuestion = useCallback(async (currentHistory) => {
    setAiState("thinking");
    setScoreCard(null);

    // CRITICAL: reset recorder and filler states for new question
    resetRecording();
    setFillerData({ count: 0, found: [] });
    setConfidenceScore(100);

    try {
      const res = await api.post("/interview/question", {
        job_title:        getEffectiveJobTitle(),
        round_number:     currentHistory.length + 1,
        history:          currentHistory,
        interview_type:   interviewType?.id || "mixed",
        type_instruction: interviewType?.prompt_instruction || "",
        company:          targetCompany,
        level:            targetLevel
      });

      const newQuestion = res.data.question;
      setQuestion(newQuestion);
      setRound(currentHistory.length + 1);

      if (!isMuted && selectedVoice) {
        setAiState("speaking");
        const textToSpeak = currentHistory.length === 0
          ? `Hello, I'm ${selectedVoice.label}, your interviewer today. Let's get started. ${newQuestion}`
          : newQuestion;

        speak(
          textToSpeak,
          selectedVoice,
          () => setAiState("speaking"),
          () => {
            // CRITICAL: after speaking ends, always go to listening
            setAiState("listening");
          }
        );
      } else {
        // Muted — go straight to listening
        setAiState("listening");
      }
    } catch (err) {
      console.error("Failed to fetch question:", err);
      setAiState("listening"); // Even on error, show the mic
    }
  }, [selectedJob, isMuted, selectedVoice, speak, resetRecording, interviewType, targetCompany, targetLevel]);

  // ── Start interview ────────────────────────────────────────────────
  const startInterview = async () => {
    setPhase("interview");
    await fetchNextQuestion([]);
  };

  // ── Submit answer — now uses browser transcript directly ───────────
  const handleSubmitAnswer = async () => {
    const answerText = transcript.trim() || "[No answer provided — time expired]";

    stop();
    setAiState("scoring");
    stopAnswerTimer();
    setLoadingFollowUp(false);
    setFollowUpQuestion(""); // Clear any previous follow-up question

    try {
      // Send text transcript directly — NO audio file, NO whisper, NO ffmpeg
      const res = await api.post("/interview/score-text", {
        transcript:  answerText,
        question:    isFollowUp ? followUpQuestion : question,
        job_title:   getEffectiveJobTitle(),
        user_id:     getUserId() || "anonymous"
      });

      const result = res.data;

      // Speak verbal acknowledgement immediately
      if (!isMuted && selectedVoice) {
        speakAcknowledgement(result.score.score);
      }

      const newEntry = {
        question: isFollowUp ? followUpQuestion : question,
        answer: answerText,
        score:  result.score,
        isFollowUp: isFollowUp
      };

      // Add to history
      setHistory(prev => [...prev, newEntry]);

      // If this is a follow-up answer
      if (isFollowUp) {
        setTimeout(() => {
          setScoreCard(result.score);
          setAiState("idle");
          setFollowUpAnswered(true);
        }, isMuted ? 0 : 1500);
      } else {
        // Main answer: show scorecard immediately (after acknowledgement delay)
        setTimeout(() => {
          setScoreCard(result.score);
          setAiState("idle");
        }, isMuted ? 0 : 1500);

        // Check if we should generate a follow-up probing question in the background
        const shouldFollowUp = result.score?.score < 8 || Math.random() < 0.6;
        if (shouldFollowUp) {
          setLoadingFollowUp(true);
          api.post("/interview/followup", {
            original_question: question,
            answer_given:      answerText,
            score:             result.score,
            job_title:         getEffectiveJobTitle()
          }).then(followUpRes => {
            const nextFollowUp = followUpRes.data.followup_question;
            setFollowUpQuestion(nextFollowUp);
            setLoadingFollowUp(false);
          }).catch(err => {
            console.error("Failed to generate follow-up, using fallback:", err);
            // Robust fallback follow-up question so flow is never blocked
            const fallbacks = [
              "Can you give me a specific example of a time you encountered that challenge?",
              "What was the single biggest technical hurdle in that situation and how did you resolve it?",
              "If you had to architect that system again today, what would you do differently?",
              "How did you measure the success of that project or implementation?"
            ];
            const chosen = fallbacks[Math.floor(Math.random() * fallbacks.length)];
            setFollowUpQuestion(chosen);
            setLoadingFollowUp(false);
          });
        }
      }
    } catch (err) {
      console.error("Scoring failed:", err);
      setAiState("idle");
    }
  };

  const handleStartFollowUp = () => {
    setIsFollowUp(true);
    setScoreCard(null);
    resetRecording();
    setFillerData({ count: 0, found: [] });
    setConfidenceScore(100);
    setAiState("speaking");

    if (!isMuted && selectedVoice && followUpQuestion) {
      speak(
        followUpQuestion,
        selectedVoice,
        () => setAiState("speaking"),
        () => setAiState("listening")
      );
    } else {
      setAiState("listening");
    }
  };

  // ── Next question ──────────────────────────────────────────────────
  const handleNextQuestion = async () => {
    setIsFollowUp(false);
    setFollowUpQuestion("");
    setFollowUpAnswered(false);

    if (round >= TOTAL_ROUNDS) {
      setAiState("thinking");
      setPhase("complete");
      try {
        // Fetch final Gemini report card
        const res = await api.post("/interview/report", {
          history: history,
          job_title: getEffectiveJobTitle()
        });
        setGeminiReport(res.data);
      } catch (err) {
        console.error("Failed to fetch report:", err);
      }
      
      setAiState("idle");
      if (!isMuted && selectedVoice) {
        speak(
          `Great job! You've completed all ${TOTAL_ROUNDS} rounds. Review your feedback below.`,
          selectedVoice, () => {}, () => {}
        );
      }
      return;
    }
    // Filter history to only include main questions for round counts
    const mainHistory = history.filter(h => !h.isFollowUp);
    await fetchNextQuestion(mainHistory);
  };

  const replayQuestion = () => {
    stop();
    const activeQuestion = isFollowUp ? followUpQuestion : question;
    if (selectedVoice) {
      speak(activeQuestion, selectedVoice, () => setAiState("speaking"), () => setAiState("listening"));
    }
  };

  // ── Helper to compile final numerical scores ───────────────────────
  const compileReportScores = () => {
    const mainHistory = history.filter(h => !h.isFollowUp);
    if (!mainHistory.length) return { avgScore: 0, avgClarity: 0, avgRelevance: 0, overallPercent: 0, verdict: "Maybe", verdictColor: "text-amber-500" };

    const avgScore     = Math.round(mainHistory.reduce((s, h) => s + (h.score?.score     || 0), 0) / mainHistory.length * 10) / 10;
    const avgClarity   = Math.round(mainHistory.reduce((s, h) => s + (h.score?.clarity   || 0), 0) / mainHistory.length * 10) / 10;
    const avgRelevance = Math.round(mainHistory.reduce((s, h) => s + (h.score?.relevance || 0), 0) / mainHistory.length * 10) / 10;
    const totalFillers = history.reduce((s, h) => s + (h.score?.filler_count || 0), 0);
    const starScores   = history.filter(h => h.score?.star_coverage !== undefined);
    const avgStar      = starScores.length
      ? Math.round(starScores.reduce((s, h) => s + h.score.star_coverage, 0) / starScores.length * 25)
      : null;

    const overallPercent = Math.round((avgScore + avgClarity + avgRelevance) / 30 * 100);

    const verdict = overallPercent >= 80 ? "Strong Hire" :
                    overallPercent >= 65 ? "Hire"        :
                    overallPercent >= 50 ? "Maybe"       : "No Hire";

    const verdictColor = {
      "Strong Hire": "text-[#16A34A] border-[#22C55E]/30 bg-[#DCFCE7]",
      "Hire":        "text-[#6B5CE7] border-[#6B5CE7]/30 bg-[#E8E4FF]",
      "Maybe":       "text-[#D97706] border-[#F59E0B]/30 bg-[#FEF3C7]",
      "No Hire":     "text-[#DC2626] border-[#EF4444]/30 bg-[#FEE2E2]"
    }[verdict];

    return { avgScore, avgClarity, avgRelevance, totalFillers, avgStar, overallPercent, verdict, verdictColor };
  };

  // ── PHASE 1: VOICE SELECTION SCREEN ─────────────────────────────────
  if (phase === "voice_select") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-2xl"
        >
          <div className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase mb-2">STEP 04</div>
          <h1 className="text-4xl font-extrabold text-[#111] font-sans mb-1 tracking-tight">
            Mock <span className="text-[#6B5CE7]">Interview</span>
          </h1>
          <p className="text-[#555] mb-6">Choose your AI interviewer to begin</p>

          {voicesEmpty && (
            <div className="mb-6 p-3 bg-[#FEF3C7] border border-[#F59E0B]/20 rounded-lg text-sm text-[#D97706]">
              ⚠️ Your browser has limited voice support. Try Chrome or Edge for the best experience.
              The interview will still work — questions will display as text.
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {VOICE_PROFILES.map((profile) => (
              <motion.div
                key={profile.id}
                onClick={() => setSelectedVoice(profile)}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className={`p-5 rounded-2xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                  selectedVoice?.id === profile.id
                    ? "border-[#6B5CE7] bg-[#F0EEFF] shadow-[0_4px_24px_rgba(107,92,231,0.15)]"
                    : "border-[#E8E4FF] bg-white hover:border-[#C5BFFF] shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
                }`}
              >
                <div>
                  <div className="text-4xl mb-3">{profile.avatar}</div>
                  <div className="text-lg font-semibold text-[#111] mb-0.5">{profile.label}</div>
                  <div className="text-xs text-[#6B5CE7] mb-3">{profile.role}</div>
                  <p className="text-sm text-[#555] leading-relaxed mb-4">{profile.description}</p>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedVoice(profile);
                    // Preview voice
                    const preview = profile.id === "male"
                      ? "Hello, I'll be your interviewer today. Let's dive right in."
                      : "Hi there, great to meet you. I'm looking forward to our conversation.";
                    speak(preview, profile, () => {}, () => {});
                  }}
                  className="flex items-center gap-2 text-xs text-[#888] hover:text-[#6B5CE7]
                             px-3 py-1.5 bg-[#FAFAFA] rounded-lg border border-[#E8E4FF]
                             hover:border-[#6B5CE7] transition-all w-fit mt-auto"
                >
                  <Volume2 className="w-3 h-3" />
                  Preview voice
                </button>
              </motion.div>
            ))}
          </div>

          <motion.button
            onClick={() => setPhase("type_select")}
            disabled={!selectedVoice}
            whileHover={{ scale: selectedVoice ? 1.02 : 1 }}
            whileTap={{ scale: selectedVoice ? 0.98 : 1 }}
            className={`w-full py-4 rounded-xl font-bold text-base transition-all flex items-center justify-center gap-2 ${
              selectedVoice
                ? "bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white shadow-[0_4px_20px_rgba(107,92,231,0.25)]"
                : "bg-[#F0EEFF] text-[#CCC] cursor-not-allowed border border-[#E8E4FF]"
            }`}
          >
            Choose Interview Persona
            <ChevronRight className="w-5 h-5" />
          </motion.button>
        </motion.div>
      </div>
    );
  }

  // ── PHASE 2: INTERVIEW TYPE SELECTOR + COMPANY MODE ──────────────────
  if (phase === "type_select") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-2xl"
        >
          <h1 className="text-3xl font-extrabold text-[#111] font-sans mb-1 tracking-tight">
            Interview <span className="text-[#6B5CE7]">Settings</span>
          </h1>
          <p className="text-[#555] mb-6">Select your focus area and optional target company</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            {INTERVIEW_TYPES.map((type) => {
              const selected = interviewType?.id === type.id;
              const colorMap = {
                indigo: "border-[#6B5CE7] bg-[#F0EEFF]",
                cyan: "border-[#8B7CF8] bg-[#F0EEFF]",
                emerald: "border-[#22C55E] bg-[#DCFCE7]",
                amber: "border-[#F59E0B] bg-[#FEF3C7]"
              };
              return (
                <motion.div
                  key={type.id}
                  onClick={() => setInterviewType(type)}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className={`p-5 rounded-2xl border-2 cursor-pointer transition-all ${
                    selected ? colorMap[type.color] : "border-[#E8E4FF] bg-white hover:border-[#C5BFFF] shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
                  }`}
                >
                  <div className="text-3xl mb-2">{type.icon}</div>
                  <div className="text-base font-semibold text-[#111] mb-1">{type.label}</div>
                  <p className="text-xs text-[#555] mb-3 leading-relaxed">{type.description}</p>
                  <p className="text-xs text-[#888] italic">e.g. "{type.example}"</p>
                </motion.div>
              );
            })}
          </div>

          {/* Company-Specific Input */}
          <div className="mb-8 p-5 bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-[#6B5CE7]" />
              <span className="text-sm font-semibold text-[#111]">Target Company Mode (Optional)</span>
            </div>
            <p className="text-xs text-[#555] mb-4">
              Enter the company and seniority level you are targeting. We will customize the questions to match their known interview patterns.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] uppercase font-bold text-[#BBB] tracking-wider block mb-1">Company</label>
                <input
                  type="text"
                  placeholder="e.g. Google, TCS, Stripe, Goldman Sachs"
                  value={targetCompany}
                  onChange={e => setTargetCompany(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-[#FAFAFA] border-[1.5px] border-[#E8E4FF] rounded-[10px]
                             text-sm text-[#111] placeholder-[#BBB] focus:border-[#6B5CE7]
                             focus:bg-white focus:outline-none transition-colors"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase font-bold text-[#BBB] tracking-wider block mb-1">Seniority Level</label>
                <input
                  type="text"
                  placeholder="e.g. Junior SDE, L4, SDE-2, Architect"
                  value={targetLevel}
                  onChange={e => setTargetLevel(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-[#FAFAFA] border-[1.5px] border-[#E8E4FF] rounded-[10px]
                             text-sm text-[#111] placeholder-[#BBB] focus:border-[#6B5CE7]
                             focus:bg-white focus:outline-none transition-colors"
                />
              </div>
            </div>
          </div>

          <div className="flex gap-4">
            <button
              onClick={() => setPhase("voice_select")}
              className="px-6 py-4 rounded-xl font-semibold border border-[#E8E4FF] bg-white hover:border-[#6B5CE7] text-[#6B5CE7] transition-all"
            >
              Back
            </button>
            <motion.button
              onClick={() => setPhase("briefing")}
              disabled={!interviewType}
              whileHover={{ scale: interviewType ? 1.02 : 1 }}
              whileTap={{ scale: interviewType ? 0.98 : 1 }}
              className={`flex-1 py-4 rounded-xl font-bold text-base transition-all flex items-center justify-center gap-2 ${
                interviewType
                  ? "bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white shadow-[0_4px_20px_rgba(107,92,231,0.25)]"
                  : "bg-[#F0EEFF] text-[#CCC] cursor-not-allowed border border-[#E8E4FF]"
              }`}
            >
              Continue to Briefing
              <ChevronRight className="w-5 h-5" />
            </motion.button>
          </div>
        </motion.div>
      </div>
    );
  }

  // ── PHASE 3: PRE-INTERVIEW WARM-UP BRIEFING SCREEN ──────────────────
  if (phase === "briefing") {
    const resolvedCompany = targetCompany.trim() || selectedJob?.company || "this company";
    const resolvedJob = getEffectiveJobTitle();
    const companyInitial = resolvedCompany.charAt(0).toUpperCase();

    const staggerContainer = {
      hidden: { opacity: 0 },
      show: {
        opacity: 1,
        transition: {
          staggerChildren: 0.1,
          delayChildren: 0.1
        }
      }
    };

    const staggerItem = {
      hidden: { opacity: 0, y: 15 },
      show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 100, damping: 15 } }
    };

    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-2xl bg-white border border-[#E8E4FF] rounded-3xl p-8 relative shadow-[0_4px_24px_rgba(107,92,231,0.08)]"
        >
          {/* Skip button */}
          <button
            onClick={startInterview}
            className="absolute top-6 right-6 px-3.5 py-1.5 rounded-lg text-xs font-semibold
                       bg-[#FAFAFA] border border-[#E8E4FF] text-[#888] hover:text-[#6B5CE7]
                       hover:border-[#6B5CE7] transition-all no-print"
          >
            Skip & Start ⚡
          </button>

          <motion.div
            variants={staggerContainer}
            initial="hidden"
            animate="show"
            className="flex flex-col"
          >
            {/* Logo and Header */}
            <motion.div variants={staggerItem} className="flex items-center gap-4 mb-8">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center font-bold text-2xl text-white shadow-lg"
                style={{ background: "linear-gradient(135deg, #6B5CE7, #8B7CF8)" }}>
                {companyInitial}
              </div>
              <div>
                <div className="text-xs text-[#6B5CE7] font-bold uppercase tracking-wider">PRE-INTERVIEW BRIEFING</div>
                <h2 className="text-2xl font-extrabold text-[#111] font-sans mt-0.5">{resolvedJob}</h2>
                <p className="text-[#555] text-sm">{resolvedCompany} {targetLevel && `· ${targetLevel}`}</p>
              </div>
            </motion.div>

            {/* Structure and Criteria Grid */}
            <motion.div variants={staggerItem} className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              <div className="p-4 rounded-xl bg-[#FAFAFA] border border-[#E8E4FF] hover:border-[#C5BFFF] transition-all">
                <div className="text-[11px] font-bold text-[#BBB] uppercase tracking-widest mb-2">Structure</div>
                <p className="text-sm text-[#555]">
                  5 rounds of mock interview questions. A mix of technical problem-solving and core behavioral patterns.
                </p>
              </div>
              <div className="p-4 rounded-xl bg-[#FAFAFA] border border-[#E8E4FF] hover:border-[#C5BFFF] transition-all">
                <div className="text-[11px] font-bold text-[#BBB] uppercase tracking-widest mb-2.5">AI Evaluation Areas</div>
                <div className="flex flex-wrap gap-1.5">
                  {["Communication", "Technical Knowledge", "Problem Solving", "Cultural Alignment"].map(c => (
                    <span key={c} className="px-2 py-1 bg-[#E8E4FF] text-[#6B5CE7] border border-[#6B5CE7]/20 text-xs rounded font-medium">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </motion.div>

            {/* Tips list */}
            <motion.div variants={staggerItem} className="mb-8">
              <div className="text-[11px] font-bold text-[#BBB] uppercase tracking-widest mb-3.5">Warm-Up Tips</div>
              <div className="space-y-3">
                {[
                  "Quality of thoughts matters more than speed. Take a moment to structure your ideas.",
                  "Structure behavioral answers with the STAR method (Situation, Task, Action, Result).",
                  "Keep track of the countdown timer — you have 2 minutes to record each answer."
                ].map((tip, idx) => (
                  <div key={idx} className="flex items-start gap-3">
                    <CheckCircle className="w-4 h-4 text-[#22C55E] mt-0.5 shrink-0" />
                    <p className="text-sm text-[#555]">{tip}</p>
                  </div>
                ))}
              </div>
            </motion.div>

            {/* Briefing countdown and button */}
            <motion.div variants={staggerItem} className="flex flex-col md:flex-row items-center justify-between gap-6 pt-6 border-t border-[#E8E4FF]">
              <div className="flex items-center gap-4">
                <div className="relative w-12 h-12 shrink-0">
                  <svg className="w-12 h-12 -rotate-90" viewBox="0 0 48 48">
                    <circle cx="24" cy="24" r="20" fill="none" stroke="#E8E4FF" strokeWidth="2.5" />
                    <motion.circle
                      cx="24" cy="24" r="20" fill="none" stroke="#6B5CE7" strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 20}`}
                      strokeDashoffset={`${2 * Math.PI * 20 * (1 - briefingCountdown / 30)}`}
                      transition={{ duration: 1, ease: "linear" }}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-xs font-mono font-bold text-[#6B5CE7]">{briefingCountdown}s</span>
                  </div>
                </div>
                <div className="text-left">
                  <span className="text-xs text-[#888] block">Briefing active</span>
                  <span className="text-sm text-[#555] font-medium">Listening to persona intro...</span>
                </div>
              </div>

              <motion.button
                onClick={startInterview}
                disabled={briefingCountdown > 20} // Enable button after 10 seconds
                whileHover={{ scale: briefingCountdown <= 20 ? 1.02 : 1 }}
                whileTap={{ scale: briefingCountdown <= 20 ? 0.98 : 1 }}
                className={`px-8 py-3.5 rounded-xl font-bold text-sm transition-all flex items-center gap-2 ${
                  briefingCountdown <= 20
                    ? "bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white shadow-[0_4px_20px_rgba(107,92,231,0.25)]"
                    : "bg-[#F0EEFF] text-[#CCC] cursor-not-allowed border border-[#E8E4FF]"
                }`}
              >
                Ready — Start Interview
                <ChevronRight className="w-4.5 h-4.5" />
              </motion.button>
            </motion.div>
          </motion.div>
        </motion.div>
      </div>
    );
  }

  // ── PHASE 5: FULL INTERVIEW REPORT CARD (COMPLETE) ──────────────────
  if (phase === "complete") {
    const report = compileReportScores();
    const companyLabel = targetCompany.trim() || selectedJob?.company || "CareerMind AI";
    const jobLabel = selectedJob?.title || "Software Engineer";
    const levelLabel = targetLevel.trim() ? ` (${targetLevel})` : "";
    const reportTitle = `Your ${companyLabel}${levelLabel} ${jobLabel} Interview Report`;

    const radarData = [
      { subject: "Communication", value: Math.round((report.avgClarity || 0) * 10) },
      { subject: "Technical",     value: Math.round((report.avgScore || 0) * 10) },
      { subject: "Relevance",     value: Math.round((report.avgRelevance || 0) * 10) },
      { subject: "Confidence",    value: Math.max(0, 100 - (report.totalFillers || 0) * 5) },
      { subject: "Structure",     value: report.avgStar ?? 75 }
    ];

    return (
      <div className="min-h-screen px-6 py-12 flex flex-col items-center">
        <style>{`
          @media print {
            body * {
              visibility: hidden;
            }
            .interview-report, .interview-report * {
              visibility: visible;
            }
            .interview-report {
              position: absolute;
              left: 0;
              top: 0;
              width: 100%;
              background: white !important;
              color: black !important;
              padding: 20px !important;
            }
            .no-print {
              display: none !important;
            }
            .interview-report h1, .interview-report h2, .interview-report h3, .interview-report p, .interview-report span, .interview-report td, .interview-report th, .interview-report div {
              color: black !important;
              border-color: #cbd5e1 !important;
            }
          }
        `}</style>

        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          className="w-full max-w-4xl interview-report"
        >
          {/* Action buttons (No-Print) */}
          <div className="flex justify-between items-center mb-8 no-print">
            <h1 className="text-3xl font-extrabold text-[#111] font-sans tracking-tight">Interview Report</h1>
            <div className="flex gap-3">
              <button
                onClick={() => window.print()}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold
                           bg-white border border-[#E8E4FF] text-[#6B5CE7] hover:border-[#6B5CE7]
                           transition-all shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
              >
                <Printer className="w-4 h-4" />
                Export PDF / Print
              </button>
              <button
                onClick={() => window.location.reload()}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold
                           bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white transition-all"
              >
                Practice Again
              </button>
            </div>
          </div>

          {/* Report header */}
          <div className="p-6 rounded-2xl bg-white border border-[#E8E4FF] mb-6 shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div>
                <div className="text-[11px] text-[#6B5CE7] font-bold uppercase tracking-widest">COMPLETE ASSESSMENT</div>
                <h2 className="text-2xl font-extrabold text-[#111] font-sans mt-1">{reportTitle}</h2>
                <p className="text-[#555] text-sm mt-0.5">
                  Conducted by AI Persona {selectedVoice?.label} · {TOTAL_ROUNDS} rounds completed
                </p>
              </div>

              {/* Verdict badge */}
              <div className={`flex flex-col items-center border rounded-2xl p-4 w-40 shrink-0 ${report.verdictColor}`}>
                <span className="text-[10px] uppercase font-bold tracking-widest text-[#888] mb-1">Recommendation</span>
                <span className="text-xl font-extrabold">{report.verdict}</span>
                <span className="text-2xl font-mono font-bold text-[#111] mt-2">{report.overallPercent}%</span>
              </div>
            </div>
          </div>

          {/* Metrics, Radar, and Chart section */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 mb-6">
            {/* Radar chart (8 cols) */}
            <div className="md:col-span-8 p-6 rounded-2xl bg-white border border-[#E8E4FF] flex flex-col justify-between shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
              <div>
                <h3 className="text-sm font-semibold text-[#111] mb-1">Performance Radar</h3>
                <p className="text-xs text-[#888]">Holistic analysis of your communication, technical competence, and structure</p>
              </div>
              <div className="flex justify-center items-center h-[280px] mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                    <PolarGrid stroke="#E8E4FF" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: "#555", fontSize: 11 }} />
                    <Radar dataKey="value" stroke="#6B5CE7" fill="#6B5CE7" fillOpacity={0.15} strokeWidth={2} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Quick stats (4 cols) */}
            <div className="md:col-span-4 grid grid-cols-1 gap-4 shrink-0">
              {[
                { label: "Technical Competence", val: `${report.avgScore}/10`, desc: "Accuracy of solutions", color: "text-[#6B5CE7]" },
                { label: "Clarity & Pacing", val: `${report.avgClarity}/10`, desc: "Structure and speed", color: "text-[#8B7CF8]" },
                { label: "Relevance Score", val: `${report.avgRelevance}/10`, desc: "Focusing on prompt", color: "text-[#22C55E]" },
                { label: "Total Filler Words", val: report.totalFillers, desc: "Pacing interruptions", color: "text-[#D97706]" }
              ].map((stat, idx) => (
                <div key={idx} className="p-5 rounded-2xl bg-white border border-[#E8E4FF] flex flex-col justify-center shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
                  <span className="text-xs text-[#888]">{stat.label}</span>
                  <span className={`text-2xl font-bold font-mono mt-1 ${stat.color}`}>{stat.val}</span>
                  <span className="text-[10px] text-[#888] mt-1">{stat.desc}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Gemini report strengths/weaknesses loader */}
          {!geminiReport && aiState === "thinking" && (
            <div className="p-6 bg-white border border-[#E8E4FF] rounded-2xl mb-6 flex items-center justify-center gap-3 shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-2 h-2 rounded-full bg-[#6B5CE7]"
                    animate={{ y: [0, -6, 0] }}
                    transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
                  />
                ))}
              </div>
              <span className="text-sm text-[#555]">AI is compiling your final assessment report...</span>
            </div>
          )}

          {/* Gemini Report Card details */}
          {geminiReport && (
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6"
            >
              {/* Strengths */}
              <div className="p-6 rounded-2xl bg-white border border-[#E8E4FF] shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle className="w-5 h-5 text-[#22C55E]" />
                  <h3 className="text-base font-semibold text-[#111]">Top Strengths</h3>
                </div>
                <ul className="space-y-3">
                  {geminiReport.strengths?.map((str, idx) => (
                    <li key={idx} className="flex gap-2 text-sm text-[#555]">
                      <span className="text-[#6B5CE7] font-mono font-bold shrink-0">{idx + 1}.</span>
                      {str}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Improvements */}
              <div className="p-6 rounded-2xl bg-white border border-[#E8E4FF] shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
                <div className="flex items-center gap-2 mb-4">
                  <ShieldAlert className="w-5 h-5 text-[#D97706]" />
                  <h3 className="text-base font-semibold text-[#111]">Key Improvement Areas</h3>
                </div>
                <ul className="space-y-3">
                  {geminiReport.improvements?.map((imp, idx) => (
                    <li key={idx} className="flex gap-2 text-sm text-[#555]">
                      <span className="text-[#6B5CE7] font-mono font-bold shrink-0">{idx + 1}.</span>
                      {imp}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Study Topics */}
              <div className="p-6 rounded-2xl bg-white border border-[#E8E4FF] md:col-span-2 shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
                <div className="flex items-center gap-2 mb-4">
                  <Brain className="w-5 h-5 text-[#8B7CF8]" />
                  <h3 className="text-base font-semibold text-[#111]">Recommended Study Topics</h3>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {geminiReport.study_topics?.map((topic, idx) => (
                    <div key={idx} className="p-3.5 bg-[#FAFAFA] border border-[#E8E4FF] rounded-xl flex items-center gap-2.5">
                      <span className="text-xs font-mono font-bold text-[#6B5CE7] bg-[#E8E4FF] px-2 py-1 rounded">#{idx + 1}</span>
                      <span className="text-sm font-medium text-[#111]">{topic}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Overall Feedback */}
              {geminiReport.overall_feedback && (
                <div className="p-6 rounded-2xl bg-[#F0EEFF] border border-[#6B5CE7]/20 md:col-span-2">
                  <h3 className="text-sm font-bold text-[#6B5CE7] uppercase tracking-wider mb-2">Overall Interview Verdict</h3>
                  <p className="text-base text-[#333] leading-relaxed font-medium">{geminiReport.overall_feedback}</p>
                </div>
              )}
            </motion.div>
          )}

          {/* Round-by-round breakdown table */}
          <div className="p-6 rounded-2xl bg-white border border-[#E8E4FF] mb-6 shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
            <h3 className="text-sm font-semibold text-[#111] mb-4">Detailed Round Breakdown</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[#E8E4FF] text-[#888] text-xs uppercase tracking-wider">
                    <th className="py-3 px-4">Round</th>
                    <th className="py-3 px-4">Interviewer Question</th>
                    <th className="py-3 px-4 text-center">Score</th>
                    <th className="py-3 px-4 text-center">Clarity</th>
                    <th className="py-3 px-4 text-center">Relevance</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item, idx) => {
                    const isFU = item.isFollowUp;
                    return (
                      <tr key={idx} className="border-b border-[#E8E4FF]/40 last:border-0 text-[#555] text-sm hover:bg-[#F0EEFF]/50 transition-colors">
                        <td className="py-4 px-4 font-mono text-xs">
                          {isFU ? (
                            <span className="px-1.5 py-0.5 bg-[#FEF3C7] text-[#D97706] border border-[#F59E0B]/20 rounded text-[10px] font-bold uppercase">
                              Follow-up
                            </span>
                          ) : (
                            <span>Round {history.filter((_, i) => i <= idx && !history[i].isFollowUp).length}</span>
                          )}
                        </td>
                        <td className="py-4 px-4 max-w-xs truncate">{item.question}</td>
                        <td className="py-4 px-4 text-center font-mono font-semibold text-[#6B5CE7]">{item.score?.score ?? "-"}/10</td>
                        <td className="py-4 px-4 text-center font-mono text-[#8B7CF8]">{item.score?.clarity ?? "-"}/10</td>
                        <td className="py-4 px-4 text-center font-mono text-[#22C55E]">{item.score?.relevance ?? "-"}/10</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </motion.div>
      </div>
    );
  }

  // ── PHASE 4: MAIN INTERVIEW SCREEN ──────────────────────────────────
  const companyLabel = targetCompany.trim() || selectedJob?.company || "CareerMind AI";
  const jobLabel = selectedJob?.title || "Software Engineer";
  const activeQuestion = isFollowUp ? followUpQuestion : question;

  return (
    <div className="min-h-screen flex flex-col px-6 py-8 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase">STEP 04</div>
          <h1 className="text-3xl font-extrabold text-[#111] font-sans tracking-tight">
            Mock <span className="text-[#6B5CE7]">Interview</span>
          </h1>
          <p className="text-[#555] text-sm mt-0.5">
            With {selectedVoice?.label} · {companyLabel} {targetLevel && `(${targetLevel})`}
          </p>
        </div>

        {/* Mute toggle */}
        <button
          onClick={() => { setIsMuted(m => !m); stop(); }}
          className="p-2.5 rounded-lg border border-[#E8E4FF] bg-white 
                     text-[#888] hover:text-[#6B5CE7] transition-colors shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
        >
          {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
        </button>
      </div>

      {/* Round progress pills */}
      <div className="flex gap-2 mb-6">
        {Array.from({ length: TOTAL_ROUNDS }).map((_, i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-all ${
              i < round ? "bg-[#6B5CE7]" :
              i === round - 1 ? "bg-[#8B7CF8] animate-pulse" :
              "bg-[#E8E4FF]"
            }`}
          />
        ))}
      </div>

      {/* Interviewer Avatar card */}
      <motion.div
        className="flex items-center gap-4 mb-6 p-4 bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
      >
        <div className="relative">
          <div className={`w-14 h-14 rounded-full flex items-center justify-center text-2xl
            bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8] border-2 transition-all ${
            isSpeaking ? "border-[#6B5CE7] shadow-[0_0_20px_rgba(107,92,231,0.3)]" : "border-[#E8E4FF]"
          }`}>
            {selectedVoice?.avatar}
          </div>

          {/* Pulsing concentric wave rings */}
          <AnimatePresence>
            {isSpeaking && (
              <>
                {[1, 2, 3].map((ring) => (
                  <motion.div
                    key={ring}
                    className="absolute inset-0 rounded-full border border-[#6B5CE7]"
                    initial={{ opacity: 0.6, scale: 1 }}
                    animate={{ opacity: 0, scale: 1.8 + ring * 0.3 }}
                    exit={{ opacity: 0 }}
                    transition={{
                      duration: 1.5,
                      repeat: Infinity,
                      delay: ring * 0.3,
                      ease: "easeOut"
                    }}
                  />
                ))}
              </>
            )}
          </AnimatePresence>
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[#111]">{selectedVoice?.label}</span>
            <span className="text-xs text-[#888]">{selectedVoice?.role}</span>
          </div>

          {/* AI activity state indicator */}
          <div className="flex items-center gap-1.5 mt-1">
            <div className={`w-1.5 h-1.5 rounded-full ${
              aiState === "speaking"  ? "bg-[#6B5CE7] animate-pulse" :
              aiState === "thinking"  ? "bg-[#D97706] animate-pulse" :
              aiState === "listening" ? "bg-[#22C55E] animate-pulse" :
              aiState === "scoring"   ? "bg-[#8B7CF8] animate-pulse" :
              "bg-[#CCC]"
            }`} />
            <span className="text-xs text-[#888] capitalize">
              {aiState === "idle"      ? "Ready" :
               aiState === "speaking"  ? "Speaking..." :
               aiState === "thinking"  ? "Thinking..." :
               aiState === "listening" ? "Listening for your answer" :
               aiState === "scoring"   ? "Evaluating your response..." :
               "Ready"}
            </span>
          </div>
        </div>

        {/* Replay button */}
        {activeQuestion && !isSpeaking && (
          <button
            onClick={replayQuestion}
            className="flex items-center gap-1.5 text-xs text-[#888] hover:text-[#6B5CE7]
                       px-3 py-1.5 bg-[#FAFAFA] rounded-lg border border-[#E8E4FF]
                       hover:border-[#6B5CE7] transition-all"
          >
            <RotateCcw className="w-3 h-3" />
            Replay
          </button>
        )}
      </motion.div>

      {/* Question Card */}
      <AnimatePresence mode="wait">
        {activeQuestion && (
          <motion.div
            key={activeQuestion}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="p-5 bg-white border border-[#E8E4FF] rounded-2xl mb-5 shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
          >
            {isFollowUp ? (
              <div className="px-2 py-0.5 bg-[#FEF3C7] border border-[#F59E0B]/20 
                              rounded text-[10px] font-bold text-[#D97706] uppercase w-fit mb-2">
                Follow-up Probing Question
              </div>
            ) : (
              <div className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase mb-3">
                INTERVIEW QUESTION · ROUND {round} OF {TOTAL_ROUNDS} ({interviewType?.label})
              </div>
            )}
            <p className="text-xl text-[#111] leading-relaxed font-semibold">{activeQuestion}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* STAR Method Coach Card — for behavioural questions */}
      {aiState === "listening" && !scoreCard && isBehaviouralQuestion(activeQuestion) && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mb-4 p-4 bg-[#F0EEFF] border border-[#6B5CE7]/20 rounded-xl"
        >
          <div className="flex items-center gap-2 mb-3">
            <div className="w-5 h-5 rounded bg-[#E8E4FF] flex items-center justify-center">
              <span className="text-[#6B5CE7] text-xs font-bold font-mono">S</span>
            </div>
            <span className="text-xs font-semibold text-[#6B5CE7]">
              STAR method framework suggested
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {[
              { letter: "S", label: "Situation", hint: "Set the context — where, when, what was happening?" },
              { letter: "T", label: "Task",      hint: "What was your responsibility or challenge?" },
              { letter: "A", label: "Action",    hint: "What specific steps did YOU take?" },
              { letter: "R", label: "Result",    hint: "What was the measurable outcome?" }
            ].map(({ letter, label, hint }) => (
              <div key={letter} className="p-2.5 bg-white rounded-lg border border-[#E8E4FF]">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-xs font-bold text-[#6B5CE7] font-mono">{letter}</span>
                  <span className="text-xs font-medium text-[#111]">{label}</span>
                </div>
                <p className="text-[10px] text-[#888] leading-relaxed">{hint}</p>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Voice Recorder Card */}
      {aiState === "listening" && !scoreCard && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="p-6 bg-white border border-[#E8E4FF] rounded-2xl mb-5 shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
        >
          {/* Answer timer */}
          {timerActive && (
            <div className="flex items-center justify-between mb-4 pb-4 border-b border-[#E8E4FF]">
              <div className="flex items-center gap-3">
                <div className="relative w-11 h-11">
                  <svg className="w-11 h-11 -rotate-90" viewBox="0 0 44 44">
                    <circle cx="22" cy="22" r="19" fill="none" stroke="#E8E4FF" strokeWidth="2" />
                    <motion.circle
                      cx="22" cy="22" r="19" fill="none"
                      stroke={answerTimeLeft <= 30 ? "#EF4444" : answerTimeLeft <= 60 ? "#F59E0B" : "#6B5CE7"}
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 19}`}
                      strokeDashoffset={`${2 * Math.PI * 19 * (1 - answerTimeLeft / 120)}`}
                      transition={{ duration: 1, ease: "linear" }}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className={`text-[10px] font-mono font-bold ${
                      answerTimeLeft <= 30 ? "text-red-500" :
                      answerTimeLeft <= 60 ? "text-[#D97706]" : "text-[#6B5CE7]"
                    }`}>
                      {Math.floor(answerTimeLeft / 60)}:{String(answerTimeLeft % 60).padStart(2, "0")}
                    </span>
                  </div>
                </div>
                <div className="text-left">
                  <span className="text-[10px] text-[#BBB] uppercase font-bold tracking-wider">Answer Time Remaining</span>
                  <span className="text-xs text-[#888] block">Drafting your answer...</span>
                </div>
              </div>

              {/* Warning at 30s */}
              <AnimatePresence>
                {answerTimeLeft <= 30 && answerTimeLeft > 0 && (
                  <motion.div
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center gap-2 px-2.5 py-1.5 bg-[#FEE2E2] border border-[#EF4444]/20 rounded-lg"
                  >
                    <Clock className="w-3 h-3 text-[#DC2626] animate-pulse" />
                    <span className="text-[10px] text-[#DC2626] font-bold">{answerTimeLeft}s left — wrap up!</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Live confidence & filler word detector */}
          {isRecording && fullLiveText.length > 5 && (
            <div className="mb-4 p-3 bg-[#FAFAFA] border border-[#E8E4FF] rounded-xl">
              {/* Confidence meter */}
              <div className="flex items-center gap-3 mb-2">
                <span className="text-[10px] uppercase font-bold tracking-wider text-[#BBB] w-16">Confidence</span>
                <div className="flex-1 h-1.5 bg-[#E8E4FF] rounded-full overflow-hidden">
                  <motion.div
                    animate={{ width: `${confidenceScore}%` }}
                    transition={{ duration: 0.3 }}
                    className={`h-full rounded-full transition-colors ${
                      confidenceScore >= 70 ? "bg-[#22C55E]" :
                      confidenceScore >= 40 ? "bg-[#F59E0B]" : "bg-[#EF4444]"
                    }`}
                  />
                </div>
                <span className={`text-xs font-mono font-bold w-8 text-right ${
                  confidenceScore >= 70 ? "text-[#22C55E]" :
                  confidenceScore >= 40 ? "text-[#D97706]" : "text-[#DC2626]"
                }`}>{confidenceScore}%</span>
              </div>

              {/* Filler words counter */}
              {fillerData.count > 0 && (
                <div className="flex items-center gap-2 pt-1.5 border-t border-[#E8E4FF]">
                  <span className="text-[10px] uppercase font-bold tracking-wider text-[#BBB]">Fillers:</span>
                  <div className="flex flex-wrap gap-1">
                    {fillerData.found.slice(0, 4).map(({ word, count }) => (
                      <span key={word} className="px-1.5 py-0.5 bg-[#FEF3C7] border border-[#F59E0B]/20 rounded text-[10px] text-[#D97706] font-mono font-bold">
                        "{word}" ×{count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Microphones support warnings */}
          {!micSupported && (
            <div className="flex items-center gap-2 mb-4 p-3 bg-[#FEF3C7] border border-[#F59E0B]/20 rounded-lg">
              <AlertCircle className="w-4 h-4 text-[#D97706] shrink-0" />
              <p className="text-xs text-[#D97706]">
                Speech recognition not supported. Try Chrome or Edge for voice input.
              </p>
            </div>
          )}

          {micError && (
            <div className="flex items-center gap-2 mb-4 p-3 bg-[#FEE2E2] border border-[#EF4444]/20 rounded-lg">
              <AlertCircle className="w-4 h-4 text-[#DC2626] shrink-0" />
              <p className="text-xs text-[#DC2626]">{micError}</p>
            </div>
          )}

          {/* Live Transcript Display */}
          {(transcript || interimText) && (
            <div className="mb-4 p-3 bg-[#FAFAFA] rounded-xl border border-[#E8E4FF] min-h-[60px]">
              <div className="text-[10px] uppercase font-bold text-[#BBB] tracking-wider mb-1">Live Transcript</div>
              <p className="text-sm text-[#555]">
                {transcript}
                {interimText && <span className="text-[#BBB] italic"> {interimText}</span>}
              </p>
            </div>
          )}

          {/* Concentric visual waves */}
          <div className="flex items-center justify-center gap-1 h-8 mb-5">
            {Array.from({ length: 20 }).map((_, i) => (
              <motion.div
                key={i}
                className={`w-1 rounded-full ${isRecording ? "bg-[#6B5CE7]" : "bg-[#E8E4FF]"}`}
                animate={isRecording ? {
                  height: [4, 8 + Math.sin(i * 0.8) * 16 + 4, 4]
                } : { height: 4 }}
                transition={{
                  duration: 0.4 + (i % 5) * 0.1,
                  repeat: Infinity,
                  delay: i * 0.04
                }}
              />
            ))}
          </div>

          {/* Record button */}
          <div className="flex flex-col items-center">
            <motion.button
              onClick={isRecording ? stopRecording : startRecording}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              disabled={!micSupported}
              animate={isRecording ? {
                boxShadow: ["0 0 0 0 rgba(239,68,68,0)", "0 0 0 20px rgba(239,68,68,0.15)", "0 0 0 0 rgba(239,68,68,0)"]
              } : {}}
              transition={{ duration: 1.5, repeat: Infinity }}
              className={`w-20 h-20 rounded-full flex items-center justify-center
                mb-3 transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                isRecording
                  ? "bg-[#EF4444] shadow-[0_0_24px_rgba(239,68,68,0.3)]"
                  : "bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8] shadow-[0_4px_20px_rgba(107,92,231,0.3)]"
              }`}
            >
              {isRecording ? <MicOff className="w-8 h-8 text-white" /> : <Mic className="w-8 h-8 text-white" />}
            </motion.button>

            <p className="text-xs text-[#888] text-center">
              {isRecording
                ? `Listening... ${durationSeconds}s — click to stop`
                : transcript
                  ? "Review your transcript above or re-record"
                  : "Click the mic and speak your answer"
              }
            </p>

            {/* Re-record button */}
            {transcript && !isRecording && (
              <button
                onClick={resetRecording}
                className="mt-3 flex items-center gap-1.5 text-xs text-[#888] hover:text-[#6B5CE7] transition-colors"
              >
                <RotateCcw className="w-3 h-3" />
                Re-record answer
              </button>
            )}
          </div>

          {/* Submit Answer */}
          <AnimatePresence>
            {transcript && !isRecording && (
              <motion.button
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                onClick={handleSubmitAnswer}
                className="mt-5 w-full py-3 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2 shadow-[0_4px_20px_rgba(107,92,231,0.25)]"
              >
                Submit Answer →
              </motion.button>
            )}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Score Card Card — displays after scored */}
      <AnimatePresence>
        {scoreCard && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="p-5 bg-white border border-[#E8E4FF] rounded-2xl mb-5 shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
          >
            {/* Transcript */}
            {transcript && (
              <div className="mb-4 p-3 bg-[#FAFAFA] rounded-lg border border-[#E8E4FF]">
                <div className="text-xs text-[#BBB] mb-1 font-bold uppercase tracking-wider">Your Answer</div>
                <p className="text-sm text-[#555] leading-relaxed">{transcript}</p>
              </div>
            )}

            {/* Scores */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: "Overall Score", value: scoreCard.score, color: "#6B5CE7" },
                { label: "Clarity Score", value: scoreCard.clarity, color: "#8B7CF8" },
                { label: "Relevance Score", value: scoreCard.relevance, color: "#22C55E" }
              ].map(({ label, value, color }) => (
                <div key={label} className="text-center p-3 bg-[#FAFAFA] rounded-lg border border-[#E8E4FF]">
                  <div className="text-2xl font-mono font-extrabold mb-0.5" style={{ color }}>{value}/10</div>
                  <div className="text-xs text-[#888]">{label}</div>
                </div>
              ))}
            </div>

            {/* Feedback text */}
            <div className="text-sm text-[#555] leading-relaxed mb-4 border-b border-[#E8E4FF] pb-3">
              <span className="text-[#BBB] text-xs font-bold uppercase tracking-wider block mb-1">Feedback</span>
              {scoreCard.feedback}
            </div>

            {/* STAR Coverage Indicator */}
            {scoreCard.star_coverage !== undefined && (
              <div className="flex items-center gap-3 mb-4 border-b border-[#E8E4FF] pb-3">
                <span className="text-xs text-[#888] font-semibold uppercase tracking-wider">STAR coverage</span>
                <div className="flex gap-1">
                  {["S","T","A","R"].map((letter, i) => (
                    <div key={letter}
                      className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold font-mono ${
                        i < (scoreCard.star_coverage || 0)
                          ? "bg-[#E8E4FF] text-[#6B5CE7] border border-[#6B5CE7]/30"
                          : "bg-[#F0EEFF] text-[#CCC] border border-[#E8E4FF]"
                      }`}
                    >
                      {letter}
                    </div>
                  ))}
                </div>
                <span className="text-xs text-[#888] font-mono font-bold">
                  ({scoreCard.star_coverage}/4 parts detected)
                </span>
              </div>
            )}

            {/* Filler feedback */}
            {scoreCard.filler_feedback && (
              <div className="mb-4 text-sm text-[#555] border-b border-[#E8E4FF] pb-3">
                <span className="text-[#BBB] text-xs font-bold uppercase tracking-wider block mb-1">Filler & Pacing style</span>
                <p className="text-xs text-[#888]">{scoreCard.filler_feedback}</p>
              </div>
            )}

            {/* Stronger answer hint */}
            {scoreCard.better_answer_hint && (
              <div className="p-4 bg-[#F0EEFF] border border-[#6B5CE7]/20 rounded-xl mb-4">
                <div className="text-xs text-[#6B5CE7] font-bold uppercase tracking-wider mb-1.5">💡 Model Answer Recommendation</div>
                <p className="text-sm text-[#555] leading-relaxed">{scoreCard.better_answer_hint}</p>
              </div>
            )}

            {/* Next action button */}
            {loadingFollowUp ? (
              <button
                disabled
                className="mt-2 w-full py-3.5 bg-[#FEF3C7] text-[#D97706] font-medium rounded-xl border border-[#F59E0B]/10 flex items-center justify-center gap-2 cursor-not-allowed"
              >
                <div className="w-4 h-4 rounded-full border-2 border-[#D97706] border-t-transparent animate-spin" />
                Preparing Probing Follow-Up...
              </button>
            ) : followUpQuestion && !isFollowUp ? (
              <motion.button
                onClick={handleStartFollowUp}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="mt-2 w-full py-3.5 bg-[#D97706] hover:bg-[#B45309] text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2 shadow-[0_4px_20px_rgba(217,119,6,0.2)] border border-[#F59E0B]/30"
              >
                Answer Follow-Up Question
                <ChevronRight className="w-4 h-4" />
              </motion.button>
            ) : (
              <motion.button
                onClick={handleNextQuestion}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="mt-2 w-full py-3.5 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2 shadow-[0_4px_20px_rgba(107,92,231,0.25)]"
              >
                {round >= TOTAL_ROUNDS && !isFollowUp ? "Finish Interview" : "Next Question"}
                <ChevronRight className="w-4 h-4" />
              </motion.button>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Thinking/Scoring loader */}
      <AnimatePresence>
        {(aiState === "thinking" || aiState === "scoring") && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-3 p-4 bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
          >
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="w-2 h-2 rounded-full bg-[#6B5CE7]"
                  animate={{ y: [0, -6, 0] }}
                  transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
                />
              ))}
            </div>
            <span className="text-sm text-[#555]">
              {aiState === "thinking" ? `${selectedVoice?.label} is preparing your question...` : "Evaluating your response..."}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
