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
import ErrorBoundary from "./components/ErrorBoundary";
import { useAgentStream } from "./hooks/useAgentStream";
import api, { BACKEND_URL, wakeUpBackend } from "./lib/api";
import axios from "axios";

export function BackendStatus() {
  const [status, setStatus] = useState("checking");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await axios.get(`${BACKEND_URL}/health`, { timeout: 90000 });
        if (cancelled) return;
        const data = res.data;

        if (data?.status === "online") {
          const groqKeyMissing = data?.groq_api_key === "MISSING";
          if (groqKeyMissing) {
            setStatus("no-groq-key");
            return;
          }
          const groqStatus = data?.groq_status;
          if (groqStatus === "ok" || groqStatus === "timeout") {
            setStatus("ok");
          } else if (groqStatus === "error") {
            setStatus("groq-error");
            setDetail(data?.groq_test || "");
          } else {
            setStatus("ok");
          }
        }
      } catch {
        if (!cancelled) setStatus("down");
      }
    };
    check();
    const iv = setInterval(check, 30000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  if (status === "ok" || status === "checking") return null;

  const msgs = {
    down:         `⚠️ Backend not reachable at ${BACKEND_URL}`,
    "no-groq-key":"🔑 GROQ_API_KEY missing — add it in Render → Environment → GROQ_API_KEY (get free at console.groq.com)",
    "groq-error": `⚠️ Groq API issue: ${detail} — check your API key at console.groq.com`,
  };

  const colors = {
    down:         "bg-red-50 border-red-100 text-red-700",
    "no-groq-key":"bg-amber-50 border-amber-100 text-amber-700",
    "groq-error": "bg-amber-50 border-amber-100 text-amber-700",
  };

  return (
    <div className={`w-full px-4 py-2 text-center text-xs font-medium border-b ${colors[status] || ""}`}>
      {msgs[status] || ""}
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
          <ErrorBoundary>
            <AnimatePresence mode="wait">
              <Routes location={location} key={location.pathname}>
                <Route path="/auth"        element={<AuthRoute />} />
                <Route path="/"            element={<Protected><ErrorBoundary><Dashboard /></ErrorBoundary></Protected>} />
                <Route path="/dashboard"   element={<Protected><ErrorBoundary><Dashboard /></ErrorBoundary></Protected>} />
                <Route path="/upload"      element={<Protected><ErrorBoundary><ResumeUpload /></ErrorBoundary></Protected>} />
                <Route path="/jobs"        element={<Protected><ErrorBoundary><JobMatches /></ErrorBoundary></Protected>} />
                <Route path="/rewrite"     element={<Protected><ErrorBoundary><ResumeRewriter /></ErrorBoundary></Protected>} />
                <Route path="/interview"   element={<Protected><ErrorBoundary><MockInterview /></ErrorBoundary></Protected>} />
                <Route path="/daily-coach" element={<Protected><ErrorBoundary><DailyCoach /></ErrorBoundary></Protected>} />
                <Route path="/status"      element={<Protected><ErrorBoundary><AgentStatus /></ErrorBoundary></Protected>} />
                <Route path="*"            element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </AnimatePresence>
          </ErrorBoundary>
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
