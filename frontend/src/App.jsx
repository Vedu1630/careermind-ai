import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import useAuthStore from "./store/useAuthStore";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import ResumeUpload from "./pages/ResumeUpload";
import JobMatches from "./pages/JobMatches";
import ResumeRewriter from "./pages/ResumeRewriter";
import MockInterview from "./pages/MockInterview";
import DailyCoach from "./pages/DailyCoach";
import Navbar from "./components/Navbar";
import { useAgentStream } from "./hooks/useAgentStream";
import api from "./lib/api";

function BackendStatus() {
  const [status, setStatus] = useState("checking");

  useEffect(() => {
    const check = async () => {
      try {
        const res = await api.get("/health", { timeout: 5000 });
        const data = res.data;
        if (data.status === "healthy" || data.status === "ok" || data.gemini_test?.includes("✅")) {
          setStatus("ok");
        } else {
          setStatus("partial");
        }
      } catch {
        setStatus("down");
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  if (status === "ok") return null; // don't show when everything is fine

  return (
    <div className={`fixed top-0 left-0 right-0 z-[100] py-2 px-4 text-center text-sm font-medium ${
      status === "down"
        ? "bg-red-50 border-b border-red-200 text-red-600"
        : status === "partial"
          ? "bg-amber-50 border-b border-amber-200 text-amber-600"
          : "bg-[#F0EEFF] border-b border-[#E8E4FF] text-[#6B5CE7]"
    }`}>
      {status === "down" && "⚠️ Backend server is not reachable. Start it with: cd backend && uvicorn main:app --reload --port 8000"}
      {status === "partial" && "⚠️ Backend running but Gemini API key may be missing. Check your .env file."}
      {status === "checking" && "Connecting to server..."}
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
    const unsub = initAuth();
    return () => unsub();
  }, []);

  return (
    <BrowserRouter>
      <BackendStatus />
      <AppContent />
    </BrowserRouter>
  );
}
