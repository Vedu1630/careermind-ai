import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, Volume2, VolumeX, Phone, PhoneOff, Flame, AlertTriangle, Sparkles, CheckCircle, ShieldAlert, Clock, Square } from "lucide-react";
import { useSpeechSynthesis } from "../hooks/useSpeechSynthesis";
import { useVoiceRecorder } from "../hooks/useVoiceRecorder";
import api, { getOrCreateToken } from "../lib/api";
import useStore from "../store/useStore";

const COACH_PERSONAS = [
  {
    id: "female",
    label: "Aria",
    role: "English Communication Coach",
    avatar: "👩‍🏫",
    description: "Warm, friendly, and encouraging. Focuses on fluency, vocabulary, and general pacing.",
    pitch: 1.08,
    rate: 0.93,
    lang: "en-US",
    preferredVoiceNames: [
      "Google UK English Female",
      "Microsoft Zira",
      "Samantha",
      "Karen",
      "Victoria",
      "en-US-Standard-C"
    ]
  },
  {
    id: "male",
    label: "Arthur",
    role: "British Communication Specialist",
    avatar: "👨‍🏫",
    description: "Direct, encouraging, and clear. Focuses on grammar, structures, and business English.",
    pitch: 0.88,
    rate: 0.90,
    lang: "en-US",
    preferredVoiceNames: [
      "Google UK English Male",
      "Microsoft David",
      "Alex",
      "Daniel",
      "en-GB-Standard-B"
    ]
  }
];

const getTopicOpener = (coachName, topic) => {
  const coachIntro = coachName === "Aria" 
    ? "Hey! I'm Aria, your English coach." 
    : "Hello there! I'm Arthur, your communication specialist.";

  const topicPrompts = {
    "Your Day": "Let's talk about your day! How has it been going so far, and what have you been up to?",
    "Any Topic": "I'd love to discuss anything you're curious about. What topic or idea is on your mind today?",
    "Formal English": "Let's practice some formal English today. What professional scenario or business conversation would you like to practice?",
    "Current News": "Let's chat about what's happening in the world. Is there a recent news story or global event you'd like to discuss?",
    "Debates": "I love a good friendly debate! What topic or idea would you like us to debate today?",
    "Storytelling": "Let's do some storytelling today! Would you like to tell me a story, or should we make one up together?"
  };

  const prompt = topicPrompts[topic] || "How are you doing today? What would you like to talk about today?";
  return `${coachIntro} ${prompt}`;
};

const SESSION_DURATION = 600; // 10 minutes in seconds
const STORAGE_KEY = "daily_coach_session";

export default function DailyCoach() {
  const { jobs } = useStore();
  const selectedJob = jobs?.selectedJob;

  // Session state
  const [phase, setPhase] = useState("idle"); 
  // phases: idle | active | ended | locked

  const [timeLeft, setTimeLeft] = useState(SESSION_DURATION);
  const [timeUsedToday, setTimeUsedToday] = useState(0);
  const [secondsUntilMidnight, setSecondsUntilMidnight] = useState(0);

  // Persona state
  const [selectedCoach, setSelectedCoach] = useState(COACH_PERSONAS[0]);

  // Conversation state
  const [messages, setMessages]         = useState([]);
  const [agentState, setAgentState]     = useState("idle");
  // agentState: idle | thinking | speaking | listening
  const [isMuted, setIsMuted]           = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [feedback, setFeedback]         = useState(null);
  const [twoMinWarned, setTwoMinWarned] = useState(false);
  const [thirtySecWarned, setThirtySecWarned] = useState(false);

  const timerRef      = useRef(null);
  const messagesEndRef = useRef(null);
  const conversationHistory = useRef([]);

  const { speak, stop, isSpeaking } = useSpeechSynthesis();
  const {
    startRecording, stopRecording, resetRecording,
    transcript, interimText, isRecording, isSupported: micSupported, error: micError
  } = useVoiceRecorder();

  // ── Load today's session data from localStorage ──────────────────────
  useEffect(() => {
    const initSession = async () => {
      try {
        await getOrCreateToken();
      } catch (err) {
        console.error("Failed to initialize auth token:", err);
      }
    };
    initSession();

    const today = new Date().toDateString();
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

    if (stored.date === today) {
      const used = stored.secondsUsed || 0;
      setTimeUsedToday(used);
      if (used >= SESSION_DURATION) {
        setPhase("locked");
        setTimeLeft(0);
      } else {
        setTimeLeft(SESSION_DURATION - used);
      }
    } else {
      // New day — reset
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ date: today, secondsUsed: 0 }));
      setTimeLeft(SESSION_DURATION);
      setTimeUsedToday(0);
    }

    // Calculate seconds until midnight initial
    const getSecondsToMidnight = () => {
      const now = new Date();
      const midnight = new Date(now);
      midnight.setHours(24, 0, 0, 0);
      return Math.floor((midnight - now) / 1000);
    };
    setSecondsUntilMidnight(getSecondsToMidnight());
  }, []);

  // ── Live Countdown to Midnight Timer ───────────────────────────────
  useEffect(() => {
    if (phase !== "locked" && phase !== "ended") return;

    const interval = setInterval(() => {
      const now = new Date();
      const midnight = new Date(now);
      midnight.setHours(24, 0, 0, 0);
      setSecondsUntilMidnight(Math.floor((midnight - now) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [phase]);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Save time used to localStorage ──────────────────────────────────
  const saveTimeUsed = useCallback((secondsUsed) => {
    const today = new Date().toDateString();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ date: today, secondsUsed }));
  }, []);

  // ── End session ──────────────────────────────────────────────────────
  const endSession = useCallback(async () => {
    clearInterval(timerRef.current);
    stop();
    stopRecording();
    setPhase("ended");
    setAgentState("idle");
    saveTimeUsed(SESSION_DURATION);

    try {
      // Pass the FULL conversation history including both roles
      const res = await api.post("/daily-coach/feedback", {
        history: conversationHistory.current,
        job_title: selectedJob?.title || ""
      });

      setFeedback(res.data);
      if (res.data && typeof res.data.fluency_score === 'number') {
        localStorage.setItem("daily_coach_last_score", res.data.fluency_score);
      }

      // Only speak feedback if there was real content
      if (res.data.word_count > 10) {
        const feedbackText = `${res.data.overall_feedback} Keep practicing and I'll see you tomorrow!`;
        setTimeout(() => {
          speak(feedbackText, selectedCoach, () => {}, () => {});
        }, 800);
      } else {
        const emptyText = "It seems like there was very little speech detected today. Make sure your microphone is working and try again tomorrow!";
        setTimeout(() => {
          speak(emptyText, selectedCoach, () => {}, () => {});
        }, 800);
      }

    } catch (error) {
      console.error("Feedback failed:", error);
      setFeedback({
        fluency_score:        0,
        overall_feedback:     "Could not generate feedback. Please check your connection.",
        strengths:            [],
        improvements:         [],
        vocabulary_highlights: [],
        grammar_notes:        "",
        topic_engagement:     "",
        word_count:           0,
        message_count:        0
      });
    }
  }, [stop, stopRecording, saveTimeUsed, speak, selectedCoach, selectedJob]);

  // ── Agent speaks a message ───────────────────────────────────────────
  const agentSpeak = useCallback((text, isOpener = false) => {
    // Add to messages
    setMessages(prev => [...prev, { role: "agent", text, id: Date.now() }]);
    conversationHistory.current.push({ role: "assistant", content: text });

    if (!isMuted) {
      setAgentState("speaking");
      speak(
        text,
        selectedCoach,
        () => setAgentState("speaking"),
        () => {
          setAgentState("listening");
          // Auto-start recording after agent finishes speaking
          if (!isOpener) {
            setTimeout(() => startRecording(), 400);
          } else {
            setTimeout(() => startRecording(), 600);
          }
        }
      );
    } else {
      setAgentState("listening");
      setTimeout(() => startRecording(), 400);
    }
  }, [isMuted, speak, selectedCoach, startRecording]);

  // ── Start session ────────────────────────────────────────────────────
  const startSession = useCallback(async (topic = null) => {
    // Immediately lock the session for today to prevent reload or tab closure bypasses
    saveTimeUsed(SESSION_DURATION);

    setPhase("active");
    setMessages([]);
    conversationHistory.current = [];
    setTwoMinWarned(false);
    setThirtySecWarned(false);

    // Start countdown timer
    timerRef.current = setInterval(() => {
      setTimeLeft(prev => {
        const next = prev - 1;

        // 2-minute warning trigger
        if (next === 120) {
          setTwoMinWarned(true);
        }
        // 30-second warning trigger
        if (next === 30) {
          setThirtySecWarned(true);
        }
        // Session end
        if (next <= 0) {
          clearInterval(timerRef.current);
          endSession();
          return 0;
        }
        return next;
      });
    }, 1000);

    // AI speaks opener after short delay
    setTimeout(() => {
      const openerText = getTopicOpener(selectedCoach.label, topic);
      agentSpeak(openerText, true);
    }, 800);
  }, [saveTimeUsed, selectedCoach, agentSpeak, endSession]);


  // ── User submits their response ──────────────────────────────────────
  const handleUserResponse = useCallback(async () => {
    const userText = transcript.trim();
    if (!userText || isProcessing) return;

    stopRecording();
    resetRecording();
    stop();
    setIsProcessing(true);
    setAgentState("thinking");

    // Add user message to UI
    setMessages(prev => [...prev, { role: "user", text: userText, id: Date.now() }]);
    conversationHistory.current.push({ role: "user", content: userText });

    try {
      const res = await api.post("/daily-coach/respond", {
        user_message: userText,
        history: conversationHistory.current, // Pass the full conversation history for context and memory
        time_left: timeLeft,
        coach_name: selectedCoach.label // Pass the active coach name (Aria or Arthur)
      });

      const agentReply = res.data.reply;
      setIsProcessing(false);
      agentSpeak(agentReply);

    } catch (error) {
      console.error("Agent response failed:", error);
      setIsProcessing(false);
      agentSpeak("Sorry, I missed that. Could you say that again?");
    }
  }, [transcript, isProcessing, stopRecording, resetRecording, stop, agentSpeak, timeLeft, selectedCoach]);

  const silenceTimeoutRef = useRef(null);

  // ── Hands-free Silence Detection (Auto-Submit) ──────────────────────
  useEffect(() => {
    // Only run when active, recording, and there is a non-empty transcript
    if (phase !== "active" || !isRecording || !transcript.trim() || isProcessing) return;

    // Clear any existing silence timer
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current);
    }

    // Set a new silence timer to auto-submit after 2.0 seconds of silence
    silenceTimeoutRef.current = setTimeout(() => {
      if (isRecording && transcript.trim() && !isProcessing) {
        handleUserResponse();
      }
    }, 2000); // 2.0 second silence threshold

    return () => {
      if (silenceTimeoutRef.current) {
        clearTimeout(silenceTimeoutRef.current);
      }
    };
  }, [transcript, interimText, isRecording, phase, isProcessing, handleUserResponse]);

  // ── 2-minute warning ─────────────────────────────────────────────────
  useEffect(() => {
    if (!twoMinWarned || phase !== "active") return;
    stop();
    stopRecording();
    const warning = "Just so you know, we have about 2 minutes left in today's session.";
    setMessages(prev => [...prev, { role: "agent", text: warning, id: Date.now() + 1 }]);
    if (!isMuted) {
      setAgentState("speaking");
      speak(warning, selectedCoach, () => setAgentState("speaking"), () => {
        setAgentState("listening");
        startRecording();
      });
    } else {
      setAgentState("listening");
      setTimeout(() => startRecording(), 400);
    }
  }, [twoMinWarned, selectedCoach, isMuted, speak, stop, stopRecording, startRecording]);

  // ── 30-second warning ────────────────────────────────────────────────
  useEffect(() => {
    if (!thirtySecWarned || phase !== "active") return;
    stop();
    stopRecording();
    const warning = "We're wrapping up soon. I'll share my feedback in just a moment.";
    setMessages(prev => [...prev, { role: "agent", text: warning, id: Date.now() + 2 }]);
    if (!isMuted) {
      setAgentState("speaking");
      speak(warning, selectedCoach, () => setAgentState("speaking"), () => setAgentState("idle"));
    } else {
      setAgentState("idle");
    }
  }, [thirtySecWarned, selectedCoach, isMuted, speak, stop, stopRecording]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
      stop();
      stopRecording();
    };
  }, [stop, stopRecording]);

  // Format time
  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  };

  const formatCountdown = (seconds) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`;
  };

  // ── USER INTERRUPT FUNCTION ─────────────────────────────────────────
  const handleInterrupt = () => {
    stop(); // cancel speech synthesis
    setAgentState("listening");
    setTimeout(() => startRecording(), 300);
  };

  // ── LOCKED SCREEN ────────────────────────────────────────────────────
  if (phase === "locked") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="w-full max-w-md text-center bg-white border border-[#E8E4FF] rounded-3xl p-8 shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
        >
          <div className="w-20 h-20 rounded-2xl bg-[#F0EEFF] border border-[#E8E4FF]
                          flex items-center justify-center text-4xl mx-auto mb-6">
            🔒
          </div>
          <h2 className="text-2xl font-bold text-[#111] mb-2 font-sans">Daily Limit Reached</h2>
          <p className="text-[#555] text-sm mb-6 leading-relaxed font-sans">
            You've used your 10 minutes of conversation practice for today. Come back tomorrow to continue speaking!
          </p>

          {/* Countdown to midnight */}
          <div className="p-5 bg-[#F0EEFF] border border-[#E8E4FF] rounded-2xl mb-6">
            <div className="text-[10px] uppercase font-bold tracking-wider text-[#888] mb-1">Next Session Unlocks In</div>
            <div className="text-3xl font-mono font-bold text-[#6B5CE7]">
              {formatCountdown(secondsUntilMidnight)}
            </div>
          </div>


          <div className="flex items-center justify-center gap-2 text-xs text-[#555] mb-2">
            <CheckCircle className="w-4 h-4 text-[#22C55E]" />
            10 minutes successfully logged today
          </div>
        </motion.div>
      </div>
    );
  }


  // ── IDLE SCREEN ──────────────────────────────────────────────────────
  if (phase === "idle") {
    const minutesLeft = Math.floor(timeLeft / 60);
    const secondsLeft = timeLeft % 60;
    const percentLeft = (timeLeft / SESSION_DURATION) * 100;

    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-[#DCFCE7] 
                            border border-[#BBF7D0] rounded-full mb-4">
              <div className="w-1.5 h-1.5 rounded-full bg-[#22C55E] animate-pulse"/>
              <span className="text-xs text-[#16A34A] font-medium font-sans">Session Available Today</span>
            </div>
            <h1 className="text-4xl font-bold text-[#111] mb-2 font-sans">
              Daily <span className="text-[#6B5CE7] font-extrabold">English Coach</span>
            </h1>
            <p className="text-[#555] text-sm leading-relaxed font-sans">
              Practice English conversation with a dedicated AI speaking partner
            </p>
          </div>

          {/* Time available ring */}
          <div className="flex justify-center mb-8">
            <div className="relative w-44 h-44">
              <svg className="w-44 h-44 -rotate-90" viewBox="0 0 176 176">
                <circle cx="88" cy="88" r="78"
                  fill="none" stroke="#E8E4FF" strokeWidth="5"/>
                <motion.circle cx="88" cy="88" r="78"
                  fill="none" stroke="#6B5CE7" strokeWidth="5"
                  strokeLinecap="round"
                  strokeDasharray={`${2 * Math.PI * 78}`}
                  strokeDashoffset={`${2 * Math.PI * 78 * (1 - percentLeft / 100)}`}
                  initial={{ strokeDashoffset: 2 * Math.PI * 78 }}
                  animate={{ strokeDashoffset: 2 * Math.PI * 78 * (1 - percentLeft / 100) }}
                  transition={{ duration: 1.2, ease: "easeOut" }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-mono font-bold text-[#111]">
                  {minutesLeft}:{String(secondsLeft).padStart(2, "0")}
                </span>
                <span className="text-[10px] uppercase tracking-wider font-bold text-[#888] mt-1">Available Today</span>
              </div>
            </div>
          </div>

          {/* Coach Persona Selector */}
          <div className="mb-6">
            <span className="text-[11px] uppercase font-bold tracking-widest text-[#BBB] block mb-3 font-sans">Choose Your English Coach</span>
            <div className="grid grid-cols-2 gap-3">
              {COACH_PERSONAS.map((coach) => {
                const isSelected = selectedCoach.id === coach.id;
                return (
                  <motion.div
                    key={coach.id}
                    onClick={() => setSelectedCoach(coach)}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className={`p-4 rounded-2xl border cursor-pointer transition-all flex flex-col justify-between ${
                      isSelected
                        ? "border-[#6B5CE7] bg-[#F0EEFF] shadow-[0_2px_12px_rgba(107,92,231,0.12)]"
                        : "border-[#E8E4FF] bg-white hover:border-[#C4BFFF]"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <div className="w-10 h-10 rounded-xl bg-[#F0EEFF] flex items-center justify-center text-xl border border-[#E8E4FF]">
                          {coach.avatar}
                        </div>
                        {isSelected && (
                          <span className="w-2 h-2 rounded-full bg-[#6B5CE7]" />
                        )}
                      </div>
                      <div className="font-semibold text-[#111] text-sm font-sans">{coach.label}</div>
                      <div className="text-[9px] text-[#6B5CE7] font-mono mb-2">{coach.role}</div>
                      <p className="text-[10px] text-[#888] leading-relaxed mb-3 font-sans">{coach.description}</p>
                      
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedCoach(coach);
                          const preview = coach.id === "male"
                            ? "Hello there! I'm Arthur, your British communication specialist."
                            : "Hi! I'm Aria, your English communication coach.";
                          speak(preview, coach, () => {}, () => {});
                        }}
                        className="flex items-center gap-1.5 text-[9px] text-[#555] hover:text-[#6B5CE7]
                                   px-2.5 py-1.5 bg-[#F0EEFF] rounded-lg border border-[#E8E4FF]
                                   hover:border-[#6B5CE7] transition-all w-fit mt-auto cursor-pointer"
                      >
                        <Volume2 className="w-3.5 h-3.5" />
                        Preview voice
                      </button>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>

          {/* What you can discuss (Clickable Suggested Topics) */}
          <div className="mb-6">
            <span className="text-[11px] uppercase font-bold tracking-widest text-[#BBB] block mb-3 font-sans">Click a Topic to Start Today's Session</span>
            <div className="grid grid-cols-3 gap-2">
              {[
                { emoji: "☀️", label: "Your Day" },
                { emoji: "💡", label: "Any Topic" },
                { emoji: "🗣️", label: "Formal English" },
                { emoji: "🌍", label: "Current News" },
                { emoji: "💭", label: "Debates" },
                { emoji: "📚", label: "Storytelling" }
              ].map(({ emoji, label }) => (
                <motion.button
                  key={label}
                  onClick={() => startSession(label)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="p-3 bg-white border border-[#E8E4FF] rounded-xl text-center hover:border-[#6B5CE7] transition-all flex flex-col items-center justify-center cursor-pointer shadow-[0_1px_4px_rgba(0,0,0,0.04)]"
                >
                  <div className="text-xl mb-1">{emoji}</div>
                  <div className="text-[10px] font-bold text-[#555] leading-tight font-sans">{label}</div>
                </motion.button>
              ))}
            </div>
          </div>

          {/* Start button */}
          <motion.button
            onClick={() => startSession()}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="w-full py-4 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] hover:from-[#5B4CD7] hover:to-[#7B6CE8] text-white 
                       font-bold rounded-2xl transition-colors flex items-center 
                       justify-center gap-2 shadow-[0_4px_16px_rgba(107,92,231,0.3)] text-sm cursor-pointer font-sans"
          >
            <Phone className="w-4 h-4"/>
            Start Today's Session
          </motion.button>


          <p className="text-center text-[10px] text-[#888] mt-3 font-mono">
            Session automatically expires after {formatTime(timeLeft)}
          </p>
        </motion.div>
      </div>
    );
  }


  // ── ACTIVE CALL SCREEN ───────────────────────────────────────────────
  if (phase === "active") {
    return (
      <div className="min-h-screen flex flex-col max-w-xl mx-auto px-4 py-6 justify-between">
        
        {/* Call header */}
        <div className="flex items-center justify-between p-4 bg-white border border-[#E8E4FF] rounded-2xl mb-4 shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
          <div className="flex items-center gap-3">
            <div className={`relative w-12 h-12 rounded-full bg-gradient-to-br 
                            from-[#6B5CE7] to-[#8B7CF8] flex items-center 
                            justify-center text-2xl border-2 transition-all ${
              isSpeaking
                ? "border-[#6B5CE7] shadow-[0_0_16px_rgba(107,92,231,0.3)] animate-pulse"
                : "border-transparent"
            }`}>
              {selectedCoach.avatar}
              {/* Speaking rings */}
              <AnimatePresence>
                {isSpeaking && [1, 2].map(ring => (
                  <motion.div key={ring}
                    className="absolute inset-0 rounded-full border border-[#6B5CE7]"
                    initial={{ opacity: 0.5, scale: 1 }}
                    animate={{ opacity: 0, scale: 1.6 + ring * 0.2 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: ring * 0.3 }}
                  />
                ))}
              </AnimatePresence>
            </div>
            <div>
              <div className="font-semibold text-[#111] text-sm font-sans">{selectedCoach.label}</div>
              <div className="text-xs flex items-center gap-1.5">
                <div className={`w-1.5 h-1.5 rounded-full ${
                  agentState === "speaking"  ? "bg-[#6B5CE7] animate-pulse" :
                  agentState === "thinking"  ? "bg-amber-400 animate-pulse" :
                  agentState === "listening" ? "bg-[#22C55E] animate-pulse" :
                  "bg-[#CCC]"
                }`}/>
                <span className="text-[#888] capitalize text-[10px] font-mono">
                  {agentState === "speaking"  ? "Speaking..." :
                   agentState === "thinking"  ? "Thinking..." :
                   agentState === "listening" ? "Listening..." : "Ready"}
                </span>
              </div>
            </div>
          </div>

          {/* Timer */}
          <div className={`px-4 py-2 rounded-xl border font-mono font-bold text-base
            transition-all flex items-center gap-2 ${
            timeLeft <= 30  ? "bg-[#FEE2E2] border-[#FECACA] text-[#EF4444] animate-pulse" :
            timeLeft <= 120 ? "bg-[#FEF3C7] border-[#FDE68A] text-[#D97706]" :
            "bg-white border-[#E8E4FF] text-[#111]"
          }`}>
            <Clock className="w-4 h-4 shrink-0" />
            {formatTime(timeLeft)}
          </div>
        </div>

        {/* Conversation messages */}
        <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-1 min-h-[300px] max-h-[450px]">
          <AnimatePresence>
            {messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed font-sans ${
                  msg.role === "agent"
                    ? "bg-white border border-[#E8E4FF] text-[#111] rounded-tl-sm shadow-[0_1px_4px_rgba(0,0,0,0.04)]"
                    : "bg-[#6B5CE7] text-white rounded-tr-sm shadow-[0_2px_8px_rgba(107,92,231,0.25)]"
                }`}>
                  {msg.text}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Thinking indicator */}
          {isProcessing && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex justify-start"
            >
              <div className="bg-white border border-[#E8E4FF] rounded-2xl rounded-tl-sm px-4 py-3.5 flex gap-1.5 shadow-[0_1px_4px_rgba(0,0,0,0.04)]">
                {[0, 1, 2].map(i => (
                  <motion.div key={i}
                    className="w-2 h-2 rounded-full bg-[#8B7CF8]"
                    animate={{ y: [0, -4, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity, delay: i * 0.15 }}
                  />
                ))}
              </div>
            </motion.div>
          )}
          <div ref={messagesEndRef}/>
        </div>

        {/* Live transcript while speaking */}
        {(transcript || interimText) && agentState === "listening" && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 px-4 py-3 bg-[#F0EEFF] border border-[#E8E4FF] rounded-xl"
          >
            <div className="text-[10px] uppercase font-bold tracking-wider text-[#6B5CE7] mb-1">Live Transcript</div>
            <p className="text-sm text-[#111] font-sans">
              {transcript}
              {interimText && (
                <span className="text-[#888] italic"> {interimText}</span>
              )}
            </p>
          </motion.div>
        )}

        {/* Mic error */}
        {micError && (
          <div className="mb-4 p-3.5 bg-[#FEE2E2] border border-[#FECACA] rounded-xl flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-[#EF4444] shrink-0" />
            <p className="text-xs text-[#EF4444] font-sans">{micError}</p>
          </div>
        )}

        {/* Bottom controls */}
        <div className="flex items-center gap-3">
          {/* Mute button */}
          <button
            onClick={() => { setIsMuted(m => !m); stop(); }}
            className={`w-12 h-12 rounded-xl flex items-center justify-center 
                        border transition-all shrink-0 ${
              isMuted
                ? "bg-[#FEE2E2] border-[#FECACA] text-[#EF4444]"
                : "bg-white border-[#E8E4FF] text-[#555] hover:text-[#6B5CE7] hover:border-[#6B5CE7]"
            }`}
          >
            {isMuted ? <VolumeX className="w-5 h-5"/> : <Volume2 className="w-5 h-5"/>}
          </button>

          {/* Main mic / interrupt / send button */}
          <div className="flex-1">
            {isProcessing ? (
              /* Processing state */
              <div className="w-full py-3.5 bg-[#F0EEFF] border border-[#E8E4FF] 
                              rounded-xl flex items-center justify-center gap-2 opacity-50">
                <div className="w-4 h-4 border-2 border-[#6B5CE7] border-t-transparent rounded-full animate-spin" />
                <span className="text-[#6B5CE7] text-xs font-semibold font-sans">Processing...</span>
              </div>
            ) : agentState === "speaking" ? (
              /* Interrupt button when coach is speaking */
              <motion.button
                onClick={handleInterrupt}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                className="w-full py-3.5 bg-[#F0EEFF] border border-[#6B5CE7] text-[#6B5CE7] hover:bg-[#E8E4FF]
                           font-semibold rounded-xl transition-all
                           flex items-center justify-center gap-2 text-sm cursor-pointer font-sans"
              >
                <Square className="w-4 h-4 fill-current"/>
                Interrupt & Reply
              </motion.button>
            ) : agentState === "listening" ? (
              transcript ? (
                /* Send button when transcript ready */
                <motion.button
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  onClick={handleUserResponse}
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  className="w-full py-3.5 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] hover:from-[#5B4CD7] hover:to-[#7B6CE8]
                             text-white font-bold rounded-xl transition-colors
                             flex items-center justify-center gap-2 text-sm shadow-[0_4px_16px_rgba(107,92,231,0.3)] font-sans cursor-pointer"
                >
                  <Mic className="w-4 h-4"/>
                  Send Reply
                </motion.button>
              ) : (
                /* Recording mic button */
                <motion.button
                  onClick={isRecording ? stopRecording : startRecording}
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  animate={isRecording ? {
                    boxShadow: [
                      "0 0 0 0 rgba(239,68,68,0)",
                      "0 0 0 12px rgba(239,68,68,0.15)",
                      "0 0 0 0 rgba(239,68,68,0)"
                    ]
                  } : {}}
                  transition={{ duration: 1.5, repeat: Infinity }}
                  className={`w-full py-3.5 rounded-xl font-semibold transition-all
                              flex items-center justify-center gap-2 text-sm font-sans cursor-pointer ${
                    isRecording
                      ? "bg-red-500 text-white shadow-lg shadow-red-500/25"
                      : "bg-[#6B5CE7] hover:bg-[#5B4CD7] text-white shadow-[0_4px_16px_rgba(107,92,231,0.2)]"
                  }`}
                >
                  <Mic className="w-4 h-4"/>
                  {isRecording ? "Stop Speaking" : "Tap to Speak"}
                </motion.button>
              )
            ) : (
              /* Idle / fallback */
              <div className="w-full py-3.5 bg-[#F0EEFF] border border-[#E8E4FF] 
                              rounded-xl flex items-center justify-center gap-2 opacity-50">
                <Mic className="w-4 h-4 text-[#888]"/>
                <span className="text-[#888] text-xs font-sans">Ready</span>
              </div>
            )}
          </div>

          {/* End call button */}
          <button
            onClick={endSession}
            className="w-12 h-12 rounded-xl bg-[#FEE2E2] border border-[#FECACA] 
                       text-[#EF4444] hover:bg-[#FCA5A5]/30 flex items-center justify-center
                       transition-all shrink-0 cursor-pointer"
          >
            <PhoneOff className="w-5 h-5"/>
          </button>
        </div>

        <p className="text-center text-[10px] text-[#888] mt-4 font-mono">
          {!micSupported
            ? "⚠️ Speech recognition not supported in this browser"
            : isRecording
              ? `${selectedCoach.label} is listening... speak naturally and pause when done`
              : agentState === "speaking"
                ? "Tap 'Interrupt' to talk anytime"
                : `Tap the mic and start talking to ${selectedCoach.label}`
          }
        </p>
      </div>
    );
  }

  // ── ENDED / FEEDBACK SCREEN ──────────────────────────────────────────
  if (phase === "ended") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-lg"
        >
          {/* Header */}
          <div className="text-center mb-6">
            <div className="w-16 h-16 rounded-2xl bg-[#F0EEFF] border border-[#E8E4FF] flex items-center justify-center text-3xl mx-auto mb-4">
              🎉
            </div>
            <h2 className="text-2xl font-bold text-[#111] mb-1 font-sans">
              Great Session Today!
            </h2>
            <p className="text-[#555] text-sm font-sans">
              You completed your speaking practice with {selectedCoach.label}. Next session unlocks at midnight!
            </p>
          </div>

          {/* Zero-speech warning card */}
          {feedback && feedback.word_count < 10 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 p-4 bg-[#FEF3C7] border border-[#FDE68A] rounded-2xl"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[#D97706] text-lg">⚠️</span>
                <span className="text-sm font-medium text-[#D97706] font-sans">
                  Very little speech detected
                </span>
              </div>
              <p className="text-sm text-[#555] leading-relaxed font-sans">
                Only {feedback.word_count} words were captured this session.
                This could mean your microphone wasn't working, you forgot to tap the mic button,
                or you were too quiet. Tomorrow's session will be fresh — try to speak more!
              </p>
              <div className="mt-3 space-y-1.5 text-xs text-[#555]">
                <div className="flex items-center gap-2">
                  <span className="text-[#6B5CE7]">→</span>
                  Make sure Chrome/Edge has microphone permission
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[#6B5CE7]">→</span>
                  Tap the mic button first, then speak
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[#6B5CE7]">→</span>
                  Tap "Stop speaking" then "Send Reply" to submit
                </div>
              </div>
            </motion.div>
          )}

          {/* Feedback card */}
          {feedback ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2 }}
              className="bg-white border border-[#E8E4FF] rounded-3xl p-6 mb-6 shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
            >
              {/* Fluency Score Section */}
              <div className="mb-5 pb-5 border-b border-[#E8E4FF]">
                <div className="text-[11px] uppercase font-bold tracking-widest text-[#BBB] mb-3 font-mono">ENGLISH FLUENCY SCORE</div>

                <div className="flex items-center gap-4">
                  {/* Animated ring */}
                  <div className="relative w-20 h-20 shrink-0">
                    <svg viewBox="0 0 80 80" className="w-20 h-20 -rotate-90">
                      {/* Background track */}
                      <circle
                        cx="40" cy="40" r="34"
                        fill="none"
                        stroke="#E8E4FF"
                        strokeWidth="6"
                      />
                      {/* Animated score fill */}
                      <motion.circle
                        cx="40" cy="40" r="34"
                        fill="none"
                        stroke={
                          feedback.fluency_score >= 75 ? "#22C55E" :
                          feedback.fluency_score >= 50 ? "#6B5CE7" :
                          feedback.fluency_score >= 25 ? "#F59E0B" : "#EF4444"
                        }
                        strokeWidth="6"
                        strokeLinecap="round"
                        strokeDasharray={`${2 * Math.PI * 34}`}
                        initial={{ strokeDashoffset: 2 * Math.PI * 34 }}
                        animate={{
                          strokeDashoffset: 2 * Math.PI * 34 * (1 - feedback.fluency_score / 100)
                        }}
                        transition={{ duration: 1.5, ease: "easeOut", delay: 0.3 }}
                      />
                    </svg>
                    {/* Score number inside ring */}
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className={`text-lg font-mono font-bold ${
                        feedback.fluency_score >= 75 ? "text-[#22C55E]" :
                        feedback.fluency_score >= 50 ? "text-[#6B5CE7]" :
                        feedback.fluency_score >= 25 ? "text-[#F59E0B]" : "text-[#EF4444]"
                      }`}>
                        {feedback.fluency_score}
                      </span>
                    </div>
                  </div>

                  <div className="flex-1">
                    <div className="text-3xl font-mono font-bold text-[#111] mb-1">
                      {feedback.fluency_score}/100
                    </div>
                    <div className={`text-xs font-semibold uppercase tracking-wider ${
                      feedback.fluency_score >= 75 ? "text-[#22C55E]" :
                      feedback.fluency_score >= 50 ? "text-[#6B5CE7]" :
                      feedback.fluency_score >= 25 ? "text-[#F59E0B]" : "text-[#EF4444]"
                    }`}>
                      {feedback.fluency_score >= 80 ? "Excellent" :
                       feedback.fluency_score >= 65 ? "Good" :
                       feedback.fluency_score >= 45 ? "Developing" :
                       feedback.fluency_score >= 25 ? "Needs Practice" : "Very Low — Try Again"}
                    </div>
                  </div>
                </div>
              </div>

              {/* Real Metrics Row */}
              <div className="grid grid-cols-3 gap-2 mb-5">
                {[
                  {
                    label: "Words spoken",
                    value: feedback.word_count ?? 0,
                    good: (feedback.word_count ?? 0) >= 100,
                    low: (feedback.word_count ?? 0) < 30
                  },
                  {
                    label: "Avg per reply",
                    value: feedback.avg_words_per_message ?? 0,
                    good: (feedback.avg_words_per_message ?? 0) >= 20,
                    low: (feedback.avg_words_per_message ?? 0) < 8
                  },
                  {
                    label: "Filler words",
                    value: feedback.filler_count ?? 0,
                    good: (feedback.filler_count ?? 0) === 0,
                    low: (feedback.filler_count ?? 0) > 5,
                    invertColors: true  // lower is better
                  }
                ].map(({ label, value, good, low, invertColors }) => (
                  <div key={label}
                    className="p-3 bg-[#F0EEFF] rounded-xl border border-[#E8E4FF] text-center"
                  >
                    <div className={`text-xl font-mono font-bold mb-0.5 ${
                      good ? "text-[#22C55E]" : low ? "text-[#EF4444]" : "text-[#D97706]"
                    }`}>
                      {value}
                    </div>
                    <div className="text-[9px] text-[#888] uppercase font-bold tracking-wider">{label}</div>
                  </div>
                ))}
              </div>

              {/* Vocab diversity bar */}
              {feedback.vocab_diversity !== undefined && (
                <div className="mb-5 p-3 bg-[#F0EEFF]/50 border border-[#E8E4FF] rounded-xl">
                  <div className="flex justify-between text-xs text-[#555] mb-1.5">
                    <span className="font-semibold font-sans">Vocabulary Diversity</span>
                    <span className="font-mono font-bold text-[#6B5CE7]">{feedback.vocab_diversity}%</span>
                  </div>
                  <div className="h-2 bg-[#E8E4FF] border border-[#E8E4FF] rounded-full overflow-hidden mb-2">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${feedback.vocab_diversity}%` }}
                      transition={{ duration: 1, ease: "easeOut", delay: 0.5 }}
                      className="h-full rounded-full bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]"
                    />
                  </div>
                  <div className="text-[10px] text-[#888] leading-normal font-sans">
                    {feedback.vocab_diversity >= 60 ? "Excellent vocabulary range. You avoided repeating the same words." :
                     feedback.vocab_diversity >= 40 ? "Good vocabulary. Try to use more varied descriptive terms next session." :
                     "Low vocabulary diversity. Work on expanding your synonyms and descriptors."}
                  </div>
                </div>
              )}

              {/* Overall feedback */}
              <p className="text-sm text-[#333] leading-relaxed mb-5 font-medium font-sans">
                {feedback.overall_feedback}
              </p>

              {/* Strengths */}
              {feedback.strengths?.length > 0 && (
                <div className="mb-5">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#22C55E] mb-2.5">
                    <CheckCircle className="w-4 h-4" />
                    Key Strengths
                  </div>
                  <div className="space-y-2">
                    {feedback.strengths.map((s, i) => (
                      <div key={i} className="flex gap-2 text-xs text-[#333] leading-relaxed font-sans">
                        <span className="text-[#6B5CE7] font-mono font-bold shrink-0">{i + 1}.</span>
                        {s}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Improvements */}
              {feedback.improvements?.length > 0 && (
                <div className="mb-5">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#D97706] mb-2.5">
                    <ShieldAlert className="w-4 h-4" />
                    Suggested Improvement Areas
                  </div>
                  <div className="space-y-2">
                    {feedback.improvements.map((imp, i) => (
                      <div key={i} className="flex gap-2 text-xs text-[#333] leading-relaxed font-sans">
                        <span className="text-[#6B5CE7] font-mono font-bold shrink-0">{i + 1}.</span>
                        {imp}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Grammar flags — only shown if real ones detected */}
              {feedback.grammar_flags?.length > 0 && (
                <div className="mb-5 p-3.5 bg-[#FEE2E2] border border-[#FECACA] rounded-xl">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[#EF4444] mb-2.5">
                    Grammar Patterns to Fix
                  </div>
                  <div className="space-y-1.5">
                    {feedback.grammar_flags.map((flag, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs text-[#333] font-sans">
                        <span className="text-[#EF4444] font-bold shrink-0">✗</span>
                        <span>{flag}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Grammar notes — shown always */}
              {feedback.grammar_notes && (
                <div className="mb-5 p-3 bg-[#F0EEFF] border border-[#E8E4FF] rounded-xl">
                  <div className="text-[11px] uppercase font-bold tracking-widest text-[#BBB] mb-1.5 font-mono">Grammar Observation</div>
                  <p className="text-xs text-[#555] leading-relaxed font-sans">{feedback.grammar_notes}</p>
                </div>
              )}

              {/* Vocabulary Highlights */}
              {feedback.vocabulary_highlights?.length > 0 && (
                <div className="mb-5">
                  <div className="text-[11px] uppercase font-bold tracking-widest text-[#BBB] mb-2.5 font-mono">Vocabulary Highlights</div>
                  <div className="flex flex-wrap gap-1.5">
                    {feedback.vocabulary_highlights.map((word, i) => (
                      <span key={i}
                        className="px-2.5 py-1 bg-[#E8E4FF] border border-[#D5D0FF] 
                                   rounded-lg text-xs text-[#6B5CE7] font-mono font-medium"
                      >
                        {word}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Honest Score Scale Guide */}
              <div className="mt-6 p-4 bg-[#F0EEFF] border border-[#E8E4FF] rounded-2xl">
                <div className="text-[11px] uppercase font-bold tracking-widest text-[#BBB] mb-3 font-mono">How your score is calculated</div>
                <div className="grid grid-cols-2 gap-2.5 text-xs">
                  {[
                    { range: "80-100", label: "Fluent speaker", color: "text-[#22C55E]" },
                    { range: "60-79",  label: "Proficient",     color: "text-[#6B5CE7]"  },
                    { range: "40-59",  label: "Developing",     color: "text-[#F59E0B]"   },
                    { range: "0-39",   label: "Needs practice", color: "text-[#EF4444]"     }
                  ].map(({ range, label, color }) => (
                    <div key={range} className="flex items-center gap-2">
                      <span className={`font-mono font-bold ${color}`}>{range}</span>
                      <span className="text-[#555] font-sans">{label}</span>
                    </div>
                  ))}
                </div>
                <div className="text-[9px] text-[#888] mt-3 leading-normal font-mono border-t border-[#E8E4FF] pt-2.5">
                  Score = word count + vocabulary diversity + sentence length − filler word penalty − grammar penalty
                </div>
              </div>

            </motion.div>
          ) : (
            /* Loading feedback state */
            <div className="p-8 bg-white border border-[#E8E4FF] rounded-3xl mb-6 flex flex-col items-center justify-center gap-4 shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
              <div className="flex gap-1.5">
                {[0, 1, 2].map(i => (
                  <motion.div key={i}
                    className="w-2.5 h-2.5 rounded-full bg-[#6B5CE7]"
                    animate={{ y: [0, -6, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity, delay: i * 0.15 }}
                  />
                ))}
              </div>
              <span className="text-xs text-[#888] font-sans">{selectedCoach.label} is compiling your communication scorecard...</span>
            </div>
          )}

          {/* Tomorrow unlock info */}
          <div className="text-center p-5 bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
            <div className="text-[11px] uppercase font-bold tracking-widest text-[#BBB] mb-1.5 font-mono">Next Session Unlocks In</div>
            <div className="text-xl font-mono font-bold text-[#6B5CE7]">
              {formatCountdown(secondsUntilMidnight)}
            </div>
          </div>
        </motion.div>
      </div>
    );
  }

  return null;
}
