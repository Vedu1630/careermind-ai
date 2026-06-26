import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { FileUp, Briefcase, FileEdit, Mic, Brain, TrendingUp, ArrowRight, CheckCircle, Flame } from 'lucide-react'
import useStore from '../store/useStore'

const steps = [
  { to: '/upload', icon: FileUp, color: '#6B5CE7', label: 'Upload & Analyze Resume', step: '01', done: (s) => !!s.resume?.analysis },
  { to: '/jobs', icon: Briefcase, color: '#8B7CF8', label: 'Find Job Matches', step: '02', done: (s) => (s.jobs?.listings?.length || 0) > 0 },
  { to: '/rewrite', icon: FileEdit, color: '#A78BFA', label: 'Rewrite Resume for Role', step: '03', done: (s) => !!s.rewrite?.rewritten },
  { to: '/interview', icon: Mic, color: '#C084FC', label: 'Mock Interview Practice', step: '04', done: (s) => (s.interview?.history?.length || 0) > 0 },
  { to: '/daily-coach', icon: Flame, color: '#F472B6', label: 'Daily English Coach', step: '05', done: () => typeof window !== 'undefined' && localStorage.getItem('daily_coach_last_score') !== null },
]

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } },
}

const itemVariants = {
  hidden: { opacity: 0, y: 15 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
}

export default function Dashboard() {
  const navigate = useNavigate()
  const store = useStore()
  const { resume, jobs, rewrite, interview } = store

  const completedSteps = steps.filter((s) => s.done(store)).length
  const progress = Math.round((completedSteps / steps.length) * 100)

  return (
    <div className="page-container py-10">
      {/* Header */}
      <motion.div
        initial="hidden"
        animate="visible"
        variants={containerVariants}
        className="mb-10"
      >
        <motion.div variants={itemVariants} className="flex items-center gap-3 mb-2">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center shadow-md bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8]">
            <Brain size={24} className="text-white" />
          </div>
          <div>
            <p className="section-label">Welcome back</p>
            <h1 className="font-sans font-bold text-2xl text-[#111111]">Career Dashboard</h1>
          </div>
        </motion.div>

        {/* Progress bar */}
        <motion.div variants={itemVariants} className="mt-6 card p-6 bg-white border border-[#E8E4FF] rounded-2xl">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={18} className="text-[#6B5CE7]" />
              <span className="text-sm font-semibold text-[#111111]">Career Journey Progress</span>
            </div>
            <span className="font-sans font-bold text-[#6B5CE7]">{progress}%</span>
          </div>
          <div className="h-2.5 bg-[#F0EEFF] rounded-full overflow-hidden">
            <motion.div
              className="h-full rounded-full"
              style={{ background: 'linear-gradient(90deg, #6B5CE7, #8B7CF8)' }}
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
            />
          </div>
          <p className="text-xs text-[#888888] mt-2">{completedSteps} of {steps.length} steps complete</p>
        </motion.div>
      </motion.div>

      {/* Step cards */}
      <motion.div
        initial="hidden"
        animate="visible"
        variants={containerVariants}
        className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5 mb-10"
      >
        {steps.map(({ to, icon: Icon, color, label, step, done }) => {
          const isDone = done(store)
          return (
            <motion.div
              key={to}
              variants={itemVariants}
              whileHover={{ y: -4, scale: 1.02 }}
              onClick={() => navigate(to)}
              className="card p-6 bg-white border border-[#E8E4FF] rounded-2xl cursor-pointer group relative overflow-hidden transition-all duration-250"
              style={{ borderColor: isDone ? `${color}40` : undefined, boxShadow: isDone ? `0 4px 20px -2px ${color}15` : undefined }}
            >
              {isDone && (
                <div className="absolute top-4 right-4">
                  <CheckCircle size={18} style={{ color }} />
                </div>
              )}
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-5 transition-all duration-200"
                style={{ background: `${color}10`, border: `1px solid ${color}20` }}>
                <Icon size={20} style={{ color }} />
              </div>
              <p className="font-sans text-xs text-[#888888] mb-1">{step}</p>
              <h3 className="font-semibold text-sm text-[#111111] group-hover:text-[#6B5CE7] transition-all duration-200 min-h-[40px] flex items-center">{label}</h3>
              <div className="flex items-center gap-1 mt-4 text-xs font-semibold" style={{ color }}>
                {isDone ? 'Complete' : 'Start now'}
                <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
              </div>
            </motion.div>
          )
        })}
      </motion.div>

      {/* Quick stats */}
      {resume?.analysis && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
        >
          {[
            { label: 'Resume Score', value: `${resume.analysis?.overall_score || 0}/100`, color: '#6B5CE7' },
            { label: 'ATS Score', value: `${resume.analysis?.ats_score || '—'}/100`, color: '#8B7CF8' },
            { label: 'Jobs Matched', value: jobs.listings?.length || 0, color: '#A78BFA' },
            { label: 'Interview Rounds', value: interview.history?.length || 0, color: '#C084FC' },
            { label: 'Daily Fluency', value: typeof window !== 'undefined' && localStorage.getItem('daily_coach_last_score') ? `${localStorage.getItem('daily_coach_last_score')}/100` : '—', color: '#F472B6' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card p-5 bg-white border border-[#E8E4FF] rounded-2xl text-center shadow-sm">
              <p className="font-sans font-extrabold text-2xl mb-1" style={{ color }}>{value}</p>
              <p className="text-xs text-[#888888] font-medium uppercase tracking-wider">{label}</p>
            </div>
          ))}
        </motion.div>
      )}

      {/* Empty state */}
      {!resume?.analysis && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="card p-12 text-center bg-white border border-[#E8E4FF] rounded-2xl shadow-sm"
        >
          <FileUp size={48} className="text-[#888888] mx-auto mb-4" />
          <h2 className="font-sans font-bold text-xl text-[#111111] mb-2">Start your career journey</h2>
          <p className="text-sm text-[#555555] mb-6 max-w-sm mx-auto">Upload your resume to unlock AI analysis, job matches, tailored practice and more.</p>
          <motion.button
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => navigate('/upload')}
            className="btn-primary inline-flex items-center gap-2"
          >
            Upload Resume <ArrowRight size={16} />
          </motion.button>
        </motion.div>
      )}
    </div>
  )
}
