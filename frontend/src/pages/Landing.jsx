import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, FileSearch, Briefcase, Mic, Shield, Flame, Sparkles } from 'lucide-react'

const FEATURES = [
  {
    icon: FileSearch,
    color: '#6B5CE7',
    title: 'AI Resume Analysis',
    desc: 'Get a comprehensive skill audit, ATS score, gap analysis, and actionable suggestions powered by Gemini.',
    badge: 'Instant',
  },
  {
    icon: Briefcase,
    color: '#3B82F6',
    title: 'Live Job Matching',
    desc: 'Scrape real job listings from JSearch + Adzuna and score each one against your profile.',
    badge: 'Real-time',
  },
  {
    icon: Sparkles,
    color: '#22C55E',
    title: 'Smart Rewriter',
    desc: 'Gemini rewrites your resume to target a specific role — adding keywords, quantifying achievements.',
    badge: 'AI-powered',
  },
  {
    icon: Mic,
    color: '#F59E0B',
    title: 'Voice Mock Interview',
    desc: 'Practice with AI-generated questions, answer via microphone, get transcription and scoring.',
    badge: 'Voice AI',
  },
  {
    icon: Flame,
    color: '#EC4899',
    title: 'Daily English Coach',
    desc: 'Practice spoken English with a dedicated 10-minute daily voice coach. Get real-time fluency metrics.',
    badge: 'Daily Practice',
  },
]

const STATS = [
  { value: '5 AI Agents', label: 'Working for you' },
  { value: '100%', label: 'Free to use' },
  { value: '< 60s', label: 'Analysis time' },
  { value: 'Live', label: 'Job listings' },
]

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1 } },
}

const itemVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] } },
}

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="relative flex flex-col items-center justify-center pt-20 pb-20 px-4 max-w-6xl mx-auto">
        <motion.div
          initial="hidden"
          animate="visible"
          variants={containerVariants}
          className="relative z-10 w-full text-center"
        >
          {/* Badge */}
          <motion.div variants={itemVariants} className="flex justify-center mb-6">
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white border border-[#E8E4FF] text-[12px] font-semibold text-[#6B5CE7] shadow-card">
              <Sparkles size={13} />
              AI-Powered Career Intelligence
            </span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            variants={itemVariants}
            className="font-extrabold text-5xl sm:text-6xl lg:text-7xl mb-6 leading-tight tracking-tight text-[#111]"
          >
            Your AI{' '}
            <span className="text-gradient">Career Coach</span>
            <br />
            <span className="text-[#888] text-3xl sm:text-4xl font-semibold">
              Lands You the Job
            </span>
          </motion.h1>

          {/* Subtitle */}
          <motion.p
            variants={itemVariants}
            className="text-lg sm:text-xl text-[#555] max-w-2xl mx-auto mb-10 leading-relaxed"
          >
            Upload your resume. Match live jobs. Rewrite for the role. Ace the interview. Practice spoken English.{' '}
            <strong className="text-[#111]">All in one session.</strong>
          </motion.p>

          {/* CTAs */}
          <motion.div variants={itemVariants} className="flex flex-col sm:flex-row gap-4 justify-center">
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/upload')}
              className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] rounded-xl text-base font-bold text-white shadow-purple hover:opacity-90 transition-opacity"
            >
              Analyze My Resume
              <ArrowRight size={18} />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/dashboard')}
              className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white border-[1.5px] border-[#E8E4FF] rounded-xl text-base font-semibold text-[#6B5CE7] hover:border-[#6B5CE7] transition-colors"
            >
              View Dashboard
            </motion.button>
          </motion.div>
        </motion.div>
      </section>

      {/* ── Stats Bar ──────────────────────────────────────────────────── */}
      <section className="border-y border-[#E8E4FF] py-8 px-4 bg-white">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          variants={containerVariants}
          className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-6 text-center"
        >
          {STATS.map(({ value, label }) => (
            <motion.div key={label} variants={itemVariants}>
              <p className="font-extrabold text-2xl text-[#6B5CE7] mb-1">{value}</p>
              <p className="text-xs text-[#888]">{label}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── Features ──────────────────────────────────────────────────── */}
      <section className="py-20 px-4">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-80px' }}
          variants={containerVariants}
          className="max-w-6xl mx-auto"
        >
          <motion.div variants={itemVariants} className="text-center mb-14">
            <p className="text-[10px] font-bold text-[#BBB] tracking-[0.1em] uppercase mb-3">What we do</p>
            <h2 className="font-extrabold text-3xl sm:text-4xl mb-4 text-[#111] tracking-tight">
              Five specialized agents, one goal:{' '}
              <span className="text-gradient">get you hired</span>
            </h2>
            <p className="text-[#555] max-w-2xl mx-auto">
              A multi-agent LangGraph pipeline orchestrates specialized AI for each step of your job search.
            </p>
          </motion.div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5">
            {FEATURES.map(({ icon: Icon, color, title, desc, badge }) => (
              <motion.div
                key={title}
                variants={itemVariants}
                whileHover={{
                  y: -6,
                  scale: 1.02,
                  borderColor: '#6B5CE7',
                }}
                className="bg-white border border-[#E8E4FF] rounded-2xl p-6 shadow-card group cursor-default transition-all duration-300"
              >
                {/* Icon */}
                <div
                  className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-200"
                  style={{ background: `${color}15` }}
                >
                  <Icon size={22} style={{ color }} />
                </div>

                {/* Badge */}
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold mb-3"
                  style={{ background: `${color}15`, color }}>
                  {badge}
                </span>

                <h3 className="font-semibold text-base text-[#111] mb-2">{title}</h3>
                <p className="text-sm text-[#555] leading-relaxed">{desc}</p>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ── CTA section ───────────────────────────────────────────────── */}
      <section className="py-20 px-4">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="max-w-2xl mx-auto text-center"
        >
          <div className="bg-white border border-[#E8E4FF] rounded-2xl p-12 shadow-card">
            <div className="w-14 h-14 rounded-2xl bg-[#F0EEFF] flex items-center justify-center mx-auto mb-5">
              <Shield size={28} className="text-[#6B5CE7]" />
            </div>
            <h2 className="font-extrabold text-2xl sm:text-3xl mb-4 text-[#111] tracking-tight">
              From raw resume to job-ready in one session
            </h2>
            <p className="text-[#555] mb-8">
              No subscriptions. No API costs for you. Just AI-powered career acceleration.
            </p>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/upload')}
              className="inline-flex items-center gap-2 px-10 py-4 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] rounded-xl text-base font-bold text-white shadow-purple hover:opacity-90 transition-opacity"
            >
              Get Started Free
              <ArrowRight size={18} />
            </motion.button>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#E8E4FF] py-8 px-4 text-center text-xs text-[#888]">
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="w-5 h-5 rounded-md bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8] flex items-center justify-center">
            <svg width="10" height="10" viewBox="0 0 14 14" fill="none">
              <path d="M7 1L12 3.8V10.2L7 13L2 10.2V3.8L7 1Z" stroke="#fff" strokeWidth="1.1" fill="none"/>
              <circle cx="7" cy="7" r="2" fill="#fff"/>
            </svg>
          </div>
          <span className="font-semibold text-[#555]">CareerMind AI</span>
        </div>
        <p>Built with LangGraph · Gemini · FastAPI · React · Tailwind</p>
        <p>Built by Vedant Bhatt</p>
      </footer>
    </div>
  )
}
