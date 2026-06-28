import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { LayoutDashboard, FileUp, Briefcase, FileEdit, Mic, Menu, X, Flame, LogOut, User, Award, ShieldCheck, Star, Sparkles, Activity } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import useAuthStore from '../store/useAuthStore'
import useStore from '../store/useStore'

const sessionAvailable = () => {
  if (typeof window === 'undefined') return false
  const stored = JSON.parse(localStorage.getItem('daily_coach_session') || '{}')
  const today = new Date().toDateString()
  if (stored.date !== today) return true
  return (stored.secondsUsed || 0) < 600
}

const navLinks = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/upload', label: 'Resume', icon: FileUp },
  { to: '/jobs', label: 'Jobs', icon: Briefcase },
  { to: '/rewrite', label: 'Rewrite', icon: FileEdit },
  { to: '/interview', label: 'Interview', icon: Mic },
  { to: '/daily-coach', label: 'Daily Coach', icon: Flame, isDailyCoach: true },
  { to: '/status', label: 'Agent Status', icon: Activity },
]

export default function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const dropdownRef = useRef(null)
  const [provider, setProvider] = useState("gemini")

  useEffect(() => {
    const apiURL = import.meta.env.VITE_API_URL || "http://localhost:8000"
    fetch(`${apiURL.replace(/\/$/, "")}/api/health`)
      .then(r => r.json())
      .then(d => {
        if (d && d.llm_provider) {
          setProvider(d.llm_provider)
        }
      })
      .catch(e => console.error("Error fetching provider status:", e))
  }, [])


  const { user, signOut } = useAuthStore()
  const store = useStore()
  const { resume, jobs, interview } = store

  // Career stats for the profile card
  const atsScore = resume?.analysis?.ats_score || null
  const overallScore = resume?.analysis?.overall_score || null
  const jobsMatched = jobs?.listings?.length || 0
  const interviewRounds = interview?.history?.length || 0
  const fluencyScore = typeof window !== 'undefined' ? localStorage.getItem('daily_coach_last_score') : null

  const handleSignOut = async () => {
    setProfileOpen(false)
    await signOut()
    navigate('/auth')
  }

  // Close profile dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setProfileOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <nav className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-[#E8E4FF] w-full">
      <div className="flex items-center justify-between px-4 sm:px-6 py-3.5 w-full">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2.5 group" onClick={() => setProfileOpen(false)}>
          <div className="w-7 h-7 rounded-lg flex items-center justify-center bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8]">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 1L12 3.8V10.2L7 13L2 10.2V3.8L7 1Z" stroke="#fff" strokeWidth="1.1" fill="none"/>
              <circle cx="7" cy="7" r="2" fill="#fff"/>
            </svg>
          </div>
          <span className="font-extrabold text-[15px] text-[#111] tracking-tight">CareerMind AI</span>
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ml-1.5 transition-all duration-300 ${
            provider === "groq" ? "bg-orange-50 text-orange-600 border border-orange-200" : "bg-emerald-50 text-emerald-600 border border-emerald-200"
          }`}>
            {provider === "groq" ? "⚡ Groq backup" : "✨ Gemini"}
          </span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-1">
          {navLinks.map(({ to, label, icon: Icon, isDailyCoach }) => {
            const active = location.pathname === to || location.pathname.startsWith(to + '/')
            const hasBadge = isDailyCoach && sessionAvailable()
            return (
              <Link key={to} to={to} onClick={() => setProfileOpen(false)}>
                <motion.div
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-[13px] font-medium transition-all duration-200 cursor-pointer relative ${
                    active
                      ? 'text-[#6B5CE7] bg-[#F0EEFF]'
                      : 'text-[#888] hover:text-[#111] hover:bg-[#FAFAFA]'
                  }`}
                >
                  <Icon size={15} />
                  {label}
                  {hasBadge && (
                    <div className="w-1.5 h-1.5 rounded-full bg-[#22C55E] absolute top-1 right-1 animate-pulse" />
                  )}
                </motion.div>
              </Link>
            )
          })}
        </div>

        {/* Right: User Profile & Dropdown */}
        <div className="flex items-center gap-3 relative" ref={dropdownRef}>
          {user ? (
            <>
              <div 
                onClick={() => setProfileOpen(!profileOpen)}
                className="flex items-center gap-2.5 cursor-pointer select-none group"
              >
                {/* Avatar circle */}
                {user.photo ? (
                  <img src={user.photo} alt={user.name}
                    className="w-8 h-8 rounded-full border-2 border-[#E8E4FF] group-hover:border-[#6B5CE7] object-cover transition-all" />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8] flex items-center justify-center text-white text-[11px] font-bold shadow-sm group-hover:scale-105 transition-transform">
                    {user.name?.charAt(0)?.toUpperCase() || 'U'}
                  </div>
                )}
                <span className="text-[13px] font-semibold text-[#111] hidden lg:block group-hover:text-[#6B5CE7] transition-colors">
                  {user.name?.split(" ")[0]}
                </span>
              </div>

              {/* STUNNING USER PROFILE DROPDOWN */}
              <AnimatePresence>
                {profileOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 12, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 12, scale: 0.95 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                    className="absolute right-0 top-11 w-80 bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_10px_30px_rgba(107,92,231,0.15)] overflow-hidden z-50"
                  >
                    {/* Career Stats Dashboard */}
                    <div className="p-5 bg-[#FAFAFA]">
                      <div className="flex items-center justify-between mb-3 font-sans">
                        <span className="text-[10px] uppercase font-bold tracking-widest text-[#BBB]">Your Career Profile</span>
                        <span className="text-[10px] text-[#888] font-medium truncate max-w-[160px]" title={user.email}>
                          {user.email}
                        </span>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-2.5">
                        {/* ATS Score */}
                        <div className="p-3 bg-white border border-[#E8E4FF] rounded-xl flex flex-col justify-between">
                          <div className="flex items-center gap-1.5 text-[10px] text-[#888] font-medium font-sans">
                            <Award className="w-3.5 h-3.5 text-[#6B5CE7]" /> ATS Score
                          </div>
                          <div className="text-lg font-mono font-bold text-[#111] mt-1">
                            {atsScore ? `${atsScore}%` : "—"}
                          </div>
                        </div>

                        {/* Fluency Score */}
                        <div className="p-3 bg-white border border-[#E8E4FF] rounded-xl flex flex-col justify-between">
                          <div className="flex items-center gap-1.5 text-[10px] text-[#888] font-medium font-sans">
                            <Sparkles className="w-3.5 h-3.5 text-[#8B7CF8]" /> Speak Fluency
                          </div>
                          <div className="text-lg font-mono font-bold text-[#111] mt-1">
                            {fluencyScore ? `${fluencyScore}%` : "—"}
                          </div>
                        </div>

                        {/* Interview Rounds */}
                        <div className="p-3 bg-white border border-[#E8E4FF] rounded-xl flex flex-col justify-between">
                          <div className="flex items-center gap-1.5 text-[10px] text-[#888] font-medium font-sans">
                            <Mic className="w-3.5 h-3.5 text-[#C084FC]" /> Interview Rounds
                          </div>
                          <div className="text-lg font-mono font-bold text-[#111] mt-1">
                            {interviewRounds}
                          </div>
                        </div>

                        {/* Job Matches */}
                        <div className="p-3 bg-white border border-[#E8E4FF] rounded-xl flex flex-col justify-between">
                          <div className="flex items-center gap-1.5 text-[10px] text-[#888] font-medium font-sans">
                            <Briefcase className="w-3.5 h-3.5 text-[#F472B6]" /> Jobs Matched
                          </div>
                          <div className="text-lg font-mono font-bold text-[#111] mt-1">
                            {jobsMatched}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Sign Out Button */}
                    <div className="p-4 bg-white border-t border-[#F0EEFF] flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-[11px] text-[#555] font-medium">
                        <ShieldCheck className="w-4 h-4 text-[#22C55E]" />
                        <span>Secure Session</span>
                      </div>
                      <button
                        onClick={handleSignOut}
                        className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-[#EF4444] bg-[#FEE2E2] hover:bg-[#FCA5A5]/30 transition-all cursor-pointer"
                      >
                        <LogOut size={13} />
                        Sign Out
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </>
          ) : (
            <button
              onClick={() => navigate('/auth')}
              className="px-5 py-2 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] rounded-xl text-[13px] font-bold text-white hover:opacity-90 cursor-pointer"
            >
              Get Started
            </button>
          )}

          {/* Mobile toggle */}
          <button
            className="md:hidden p-2 rounded-lg text-[#888] hover:text-[#111] hover:bg-[#F0EEFF] transition-colors cursor-pointer"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="md:hidden bg-white border-t border-[#E8E4FF] px-4 pb-3"
        >
          {navLinks.map(({ to, label, icon: Icon, isDailyCoach }) => {
            const active = location.pathname === to
            const hasBadge = isDailyCoach && sessionAvailable()
            return (
              <Link key={to} to={to} onClick={() => setMobileOpen(false)}>
                <div className={`flex items-center justify-between px-4 py-3 rounded-xl text-sm font-medium transition-colors mb-1 ${
                  active ? 'text-[#6B5CE7] bg-[#F0EEFF]' : 'text-[#888] hover:text-[#111] hover:bg-[#FAFAFA]'
                }`}>
                  <div className="flex items-center gap-3">
                    <Icon size={16} />
                    {label}
                  </div>
                  {hasBadge && (
                    <div className="w-1.5 h-1.5 rounded-full bg-[#22C55E] mr-2 animate-pulse" />
                  )}
                </div>
              </Link>
            )
          })}
          {user ? (
            <button
              onClick={handleSignOut}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-[#EF4444] hover:bg-[#FEE2E2] transition-colors mt-1 cursor-pointer"
            >
              <LogOut size={16} />
              Log out
            </button>
          ) : (
            <button
              onClick={() => { setMobileOpen(false); navigate('/auth'); }}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-[#6B5CE7] hover:bg-[#F0EEFF] transition-colors mt-1 cursor-pointer"
            >
              Get Started
            </button>
          )}
        </motion.div>
      )}
    </nav>
  )
}
