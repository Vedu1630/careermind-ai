import { useEffect, useState, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import useAuthStore from "./store/useAuthStore";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import ResumeUpload from "./pages/ResumeUpload";
import JobMatches from "./pages/JobMatches";
import ResumeRewriter from "./pages/ResumeRewriter";
import MockInterview from "./pages/MockInterview";
import DailyCoach from "./pages/DailyCoach";
import AgentStatus from "./pages/AgentStatus";
import Navbar from "./components/Navbar";
import { useAgentStream } from "./hooks/useAgentStream";
import api, { BACKEND_URL, wakeUpBackend } from "./lib/api";
import axios from "axios";

export function BackendStatus() {
  const [status,  setStatus]  = useState("checking");
  const [message, setMessage] = useState("");
  const startRef = useRef(Date.now());

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      const t0 = Date.now();
      try {
        const res = await axios.get(
          `${BACKEND_URL}/health`,
          { timeout: 90000 }
        );
        if (cancelled) return;

        const elapsed = Date.now() - t0;

        if (res.data?.status === "online" || res.data?.message) {
          // Check if Gemini is working
          const geminiOk = res.data?.gemini_test?.includes("✅") ||
                           res.data?.llm_available === true ||
                           !res.data?.gemini_test; // if field missing assume ok

          if (geminiOk) {
            setStatus("ok");
          } else {
            setStatus("no-key");
            setMessage(res.data?.gemini_test || "Gemini API key may be missing");
          }
        } else {
          setStatus("ok");
        }
      } catch (err) {
        if (cancelled) return;

        if (err.code === "ECONNABORTED" || err.message?.includes("timeout")) {
          // Still waking up — not an error, just slow
          setStatus("waking");
        } else if (!err.response) {
          setStatus("down");
        } else {
          // Got a response — backend is up even if not 200
          setStatus("ok");
        }
      }
    };

    check();
    const interval = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (status === "ok") return null;

  const configs = {
    checking: {
      bg:   "bg-[#F0EEFF] border-[#E8E4FF]",
      text: "text-[#6B5CE7]",
      msg:  "🔄 Connecting to backend...",
    },
    waking: {
      bg:   "bg-amber-50 border-amber-100",
      text: "text-amber-700",
      msg:  "⏳ Backend is waking up from sleep (Render free tier) — please wait 30-60 seconds then retry",
    },
    down: {
      bg:   "bg-red-50 border-red-100",
      text: "text-red-700",
      msg:  `⚠️ Backend not reachable at ${BACKEND_URL} — check Render dashboard at dashboard.render.com`,
    },
    "no-key": {
      bg:   "bg-amber-50 border-amber-100",
      text: "text-amber-700",
      msg:  `🔑 Backend running but GOOGLE_API_KEY missing — add it in Render → Environment`,
    },
  };

  const cfg = configs[status] || configs.checking;

  return (
    <div className={`w-full px-4 py-2 text-center text-xs font-medium border-b ${cfg.bg} ${cfg.text} z-[200]`}>
      {cfg.msg}
      {status === "waking" && (
        <button
          onClick={() => window.location.reload()}
          className="ml-3 underline font-bold"
        >
          Refresh
        </button>
      )}
    </div>
  );
}

function Loader() {
  return (
    <div className="min-h-screen bg-[#F0EEFF] flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8]
                        flex items-center justify-center animate-pulse">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M10 2L17 6V14L10 18L3 14V6L10 2Z"
              stroke="white" strokeWidth="1.3" fill="none"/>
            <circle cx="10" cy="10" r="3" fill="white"/>
          </svg>
        </div>
        <p className="text-sm text-[#888] font-medium">Loading...</p>
      </div>
    </div>
  );
}

function Protected({ children }) {
  const { user, loading } = useAuthStore();
  if (loading) return <Loader />;
  if (!user)   return <Navigate to="/auth" replace />;
  return children;
}

function AuthRoute() {
  const { user, loading } = useAuthStore();
  if (loading) return <Loader />;
  if (user)    return <Navigate to="/dashboard" replace />;
  return <Auth />;
}

function AppContent() {
  const location = useLocation();
  const isAuth = location.pathname === "/auth";

  // Keep background agent connection and streaming active globally
  useAgentStream();

  return (
    <div className="min-h-screen bg-[#F0EEFF]">
      {!isAuth && <Navbar />}
      <div className={!isAuth ? "flex" : ""}>
        <main className={!isAuth ? "flex-1 min-w-0" : ""}>
          <AnimatePresence mode="wait">
            <Routes location={location} key={location.pathname}>
              <Route path="/auth"        element={<AuthRoute />} />
              <Route path="/"            element={<Protected><Dashboard /></Protected>} />
              <Route path="/dashboard"   element={<Protected><Dashboard /></Protected>} />
              <Route path="/upload"      element={<Protected><ResumeUpload /></Protected>} />
              <Route path="/jobs"        element={<Protected><JobMatches /></Protected>} />
              <Route path="/rewrite"     element={<Protected><ResumeRewriter /></Protected>} />
              <Route path="/interview"   element={<Protected><MockInterview /></Protected>} />
              <Route path="/daily-coach" element={<Protected><DailyCoach /></Protected>} />
              <Route path="/status"      element={<Protected><AgentStatus /></Protected>} />
              <Route path="*"            element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const { initAuth } = useAuthStore();

  useEffect(() => {
    // Initialize Firebase auth
    const unsub = initAuth();
    // Wake up Render backend immediately on app load
    // This gives the 30-60 second cold start time before user clicks anything
    wakeUpBackend();
    return () => unsub();
  }, []);

  return (
    <BrowserRouter>
      <BackendStatus />
      <AppContent />
    </BrowserRouter>
  );
}
