import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MapPin, Briefcase, ExternalLink, FileEdit, CheckCircle, AlertTriangle, Clock, Wifi, ChevronDown, ChevronUp } from 'lucide-react'
import SkillBadge from './SkillBadge'

// ── Circular match score ring ─────────────────────────────────────────────
function ScoreRing({ score }) {
  const radius = 28
  const circumference = 2 * Math.PI * radius
  const strokeDash = (score / 100) * circumference
  const color = score >= 75 ? '#16A34A' : score >= 50 ? '#D97706' : '#EF4444'

  return (
    <div className="relative w-16 h-16 flex-shrink-0">
      <svg width="64" height="64" viewBox="0 0 64 64" className="-rotate-90">
        {/* Background ring */}
        <circle cx="32" cy="32" r={radius} fill="none" stroke="#E8E4FF" strokeWidth="5" />
        {/* Score ring */}
        <motion.circle
          cx="32" cy="32" r={radius}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - strokeDash }}
          transition={{ duration: 1.2, ease: 'easeOut', delay: 0.2 }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xs font-bold font-sans" style={{ color }}>
          {score}%
        </span>
      </div>
    </div>
  )
}

const FIT_CONFIG = {
  strong: { label: 'Strong Match', color: 'text-[#16A34A]', bg: 'bg-[#DCFCE7] border-[#BBF7D0]' },
  partial: { label: 'Partial Match', color: 'text-[#D97706]', bg: 'bg-[#FEF3C7] border-[#FDE68A]' },
  weak: { label: 'Weak Match', color: 'text-[#EF4444]', bg: 'bg-[#FEE2E2] border-[#FECACA]' },
}

export default function JobCard({ scoredJob, onRewrite, delay = 0 }) {
  const { job, match_score, matched_skills, missing_skills, recommendation, fit_level } = scoredJob
  const fitConfig = FIT_CONFIG[fit_level] || FIT_CONFIG.partial
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      whileHover={{ y: -4, transition: { duration: 0.2 } }}
      onClick={() => setIsExpanded(!isExpanded)}
      className="card p-6 bg-white border border-[#E8E4FF] rounded-2xl group cursor-pointer flex flex-col gap-4 overflow-hidden select-none transition-all duration-250 shadow-sm hover:shadow-md"
      style={{ borderColor: match_score >= 75 ? 'rgba(22, 163, 74, 0.3)' : undefined }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-sans font-bold text-base text-[#111111] truncate mb-1 group-hover:text-[#6B5CE7] transition-all duration-200">
            {job.title}
          </h3>
          <div className="flex items-center gap-2 text-sm text-[#555555]">
            <Briefcase size={14} className="text-[#888888]" />
            <span className="truncate">{job.company}</span>
          </div>
        </div>
        <ScoreRing score={match_score} />
      </div>

      {/* Meta */}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-[#888888]">
        {job.location && (
          <span className="flex items-center gap-1">
            <MapPin size={12} /> {job.location}
          </span>
        )}
        {job.salary && job.salary !== 'Not disclosed' && (
          <span className="flex items-center gap-1">
            💰 {job.salary}
          </span>
        )}
        {job.employment_type && (
          <span className="flex items-center gap-1">
            <Clock size={12} /> {job.employment_type}
          </span>
        )}
        {job.is_remote && (
          <span className="flex items-center gap-1">
            <Wifi size={12} /> Remote
          </span>
        )}
      </div>

      {/* Fit level badge + Toggle indicator */}
      <div className="flex items-center justify-between">
        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border ${fitConfig.bg} ${fitConfig.color}`}>
          {fit_level === 'strong' && <CheckCircle size={12} />}
          {fit_level === 'weak' && <AlertTriangle size={12} />}
          {fitConfig.label}
        </span>
        
        <div className="text-[#888888] group-hover:text-[#555555] transition-colors flex items-center gap-1 text-xs font-medium">
          <span className="font-sans text-[11px] opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            {isExpanded ? 'Collapse' : 'Details'}
          </span>
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {/* Skills */}
      <div className="space-y-3">
        {matched_skills?.length > 0 && (
          <div>
            <p className="section-label mb-1.5 text-[#BBB] uppercase text-[10px] tracking-wider">Matched Skills</p>
            <div className="flex flex-wrap gap-1.5">
              {matched_skills.slice(0, 5).map((skill) => (
                <SkillBadge key={skill} skill={skill} variant="matched" />
              ))}
            </div>
          </div>
        )}
        {missing_skills?.length > 0 && (
          <div>
            <p className="section-label mb-1.5 text-[#BBB] uppercase text-[10px] tracking-wider">Skills to Develop</p>
            <div className="flex flex-wrap gap-1.5">
              {missing_skills.slice(0, 4).map((skill) => (
                <SkillBadge key={skill} skill={skill} variant="missing" />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Recommendation */}
      {recommendation && (
        <p className="text-xs text-[#555555] leading-relaxed border-t border-[#E8E4FF] pt-3">
          {recommendation}
        </p>
      )}

      {/* Description Drawer (Expands In-Place) */}
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            onClick={(e) => e.stopPropagation()}
            className="border-t border-[#E8E4FF] pt-3.5 mt-1 text-xs text-[#555555] leading-relaxed space-y-2 cursor-default"
          >
            <p className="section-label font-bold text-[10px] text-[#888888] tracking-wider uppercase">Job Description</p>
            <p className="whitespace-pre-wrap font-sans bg-[#FAFAFA] p-3 rounded-xl border border-[#E8E4FF] max-h-64 overflow-y-auto no-scrollbar text-[#111111]">
              {job.description || 'No job description provided.'}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-[#E8E4FF] mt-auto" onClick={(e) => e.stopPropagation()}>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => onRewrite?.(scoredJob)}
          className="flex-1 btn-primary py-2 text-sm justify-center inline-flex items-center gap-1.5 font-semibold"
        >
          <FileEdit size={14} />
          Rewrite Resume
        </motion.button>
        {job.apply_link && job.source !== 'demo' && (
          <motion.a
            href={job.apply_link}
            target="_blank"
            rel="noopener noreferrer"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="btn-secondary py-2 text-sm inline-flex items-center gap-1.5 font-semibold"
          >
            <ExternalLink size={14} />
            Apply
          </motion.a>
        )}
      </div>
    </motion.div>
  )
}
