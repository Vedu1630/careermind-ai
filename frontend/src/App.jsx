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
  const [detail,  setDetail]  = useState("");

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const res = await axios.get(
          `${BACKEND_URL}/health`,
          { timeout: 90000 }
        );
        if (cancelled) return;

        const data = res.data;

        // Backend is up — now check what's actually wrong
        if (data?.status === "online" || data?.message) {

          // Check if Google API key is genuinely missing
          const keyMissing = (
            data?.google_api_key === "MISSING" ||
            data?.env_vars?.GOOGLE_API_KEY?.includes("❌")
          );

          if (keyMissing) {
            // Key is genuinely not set in Render
            setStatus("no-key");
            setDetail("GOOGLE_API_KEY is not set in Render → Environment");
            return;
          }

          // Key is set — check Gemini status
          const geminiStatus = data?.gemini_status;
          const geminiTest   = data?.gemini_test || "";

          if (geminiStatus === "ok" || geminiTest.includes("✅")) {
            // Everything working perfectly
            setStatus("ok");
            return;
          }

          if (geminiStatus === "timeout" || geminiTest.includes("timed out")) {
            // Key is set but Gemini was slow — this is fine, just cold start
            // Show as OK — the key IS there, Gemini will work for real requests
            setStatus("ok");
            return;
          }

          if (geminiStatus === "error" && geminiTest.includes("❌")) {
            // Real Gemini error — key might be invalid
            setStatus("gemini-error");
            setDetail(geminiTest);
            return;
          }

          // Backend is up and key is set — consider it OK
          setStatus("ok");
        }
      } catch (err) {
        if (cancelled) return;
        if (!err.response) {
          setStatus("down");
        } else {
          // Got any response — backend is running
          setStatus("ok");
        }
      }
    };

    check();
    const interval = setInterval(check, 35000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // Hide when everything is fine
  if (status === "ok" || status === "checking") return null;

  const messages = {
    down: `⚠️ Backend not reachable at ${BACKEND_URL} — check Render dashboard`,
    "no-key": "🔑 GOOGLE_API_KEY not set in Render → Environment → Add GOOGLE_API_KEY",
    "gemini-error": `⚠️ Gemini API issue: ${detail} — check your API key at aistudio.google.com`,
    waking: "⏳ Backend waking up from sleep — please wait 30 seconds then refresh",
  };

  const colors = {
    down:          "bg-red-50 border-red-100 text-red-700",
    "no-key":      "bg-amber-50 border-amber-100 text-amber-700",
    "gemini-error":"bg-amber-50 border-amber-100 text-amber-700",
    waking:        "bg-blue-50 border-blue-100 text-blue-700",
  };

  const msg   = messages[status];
  const color = colors[status];
  if (!msg) return null;

  return (
    <div className={`w-full px-4 py-2 text-center text-xs font-medium border-b ${color} z-[200]`}>
      {msg}
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
