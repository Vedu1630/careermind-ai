import { useEffect } from "react";
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
      <AppContent />
    </BrowserRouter>
  );
}
