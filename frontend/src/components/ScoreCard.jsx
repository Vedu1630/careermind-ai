import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp, Star, Lightbulb, ThumbsUp, AlertCircle } from 'lucide-react'

// ── Count-up animation hook ────────────────────────────────────────────────
function useCountUp(target, duration = 1200) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    const start = Date.now()
    const tick = () => {
      const elapsed = Date.now() - start
      const progress = Math.min(elapsed / duration, 1)
      // Ease-out
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(eased * target))
      if (progress < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }, [target, duration])

  return value
}

// ── Sub score bar ─────────────────────────────────────────────────────────
function SubScoreBar({ label, score, color }) {
  return (
    <div>
      <div className="flex justify-between mb-1.5">
        <span className="text-xs text-text-secondary">{label}</span>
        <span className="text-xs font-mono font-semibold" style={{ color }}>{score}/10</span>
      </div>
      <div className="h-1.5 rounded-full bg-bg-elevated overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${score * 10}%` }}
          transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }}
        />
      </div>
    </div>
  )
}

// ── Overall score ring ─────────────────────────────────────────────────────
function OverallScoreRing({ score, size = 120 }) {
  const animated = useCountUp(score)
  const radius = size * 0.38
  const circumference = 2 * Math.PI * radius
  const strokeDash = (score / 10) * circumference
  const color = score >= 8 ? '#10B981' : score >= 6 ? '#F59E0B' : score >= 4 ? '#6366F1' : '#EF4444'

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="8" />
        <motion.circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - strokeDash }}
          transition={{ duration: 1.5, ease: 'easeOut' }}
          style={{ filter: `drop-shadow(0 0 8px ${color}60)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display font-bold text-3xl" style={{ color }}>{animated}</span>
        <span className="text-xs text-text-muted">/10</span>
      </div>
    </div>
  )
}

export default function ScoreCard({ scoring, onNext }) {
  const [hintOpen, setHintOpen] = useState(false)

  if (!scoring) return null

  const { score, clarity, relevance, feedback, better_answer_hint, strengths, weaknesses, transcript } = scoring

  const overallColor = score >= 8 ? '#10B981' : score >= 6 ? '#F59E0B' : '#6366F1'

  return (
    <motion.div
      initial={{ opacity: 0, y: 60 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 60 }}
      transition={{ type: 'spring', damping: 20, stiffness: 200 }}
      className="card"
    >
      <div className="flex flex-col sm:flex-row gap-6 items-center sm:items-start">
        {/* Score ring */}
        <div className="flex flex-col items-center gap-2">
          <OverallScoreRing score={score} />
          <span className="text-xs font-semibold text-text-muted">Overall Score</span>
        </div>

        {/* Details */}
        <div className="flex-1 space-y-4 w-full">
          {/* Sub-scores */}
          <div className="space-y-2.5">
            <SubScoreBar label="Clarity" score={clarity} color="#6366F1" />
            <SubScoreBar label="Relevance" score={relevance} color="#22D3EE" />
          </div>

          {/* Feedback */}
          {feedback && (
            <div className="p-3 rounded-xl bg-bg-elevated border border-border">
              <p className="text-sm text-text-secondary leading-relaxed">{feedback}</p>
            </div>
          )}

          {/* Strengths & Weaknesses */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {strengths?.length > 0 && (
              <div>
                <p className="section-label mb-2 flex items-center gap-1">
                  <ThumbsUp size={10} /> Strengths
                </p>
                <ul className="space-y-1">
                  {strengths.map((s, i) => (
                    <li key={i} className="text-xs text-success flex items-start gap-1.5">
                      <span className="mt-0.5">✓</span> {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {weaknesses?.length > 0 && (
              <div>
                <p className="section-label mb-2 flex items-center gap-1">
                  <AlertCircle size={10} /> To Improve
                </p>
                <ul className="space-y-1">
                  {weaknesses.map((w, i) => (
                    <li key={i} className="text-xs text-warning flex items-start gap-1.5">
                      <span className="mt-0.5">△</span> {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Better answer hint — collapsible */}
          {better_answer_hint && (
            <div className="border border-border/60 rounded-xl overflow-hidden">
              <button
                onClick={() => setHintOpen(!hintOpen)}
                className="w-full flex items-center justify-between px-3 py-2.5 text-xs font-semibold text-accent hover:bg-accent/5 transition-colors duration-150 cursor-pointer"
              >
                <span className="flex items-center gap-2"><Lightbulb size={12} /> Better Answer Hint</span>
                {hintOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </button>
              <AnimatePresence>
                {hintOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className="overflow-hidden"
                  >
                    <p className="px-3 pb-3 text-xs text-text-secondary leading-relaxed">
                      {better_answer_hint}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Transcript */}
          {transcript && (
            <div className="p-3 rounded-lg bg-bg/50 border border-border/50">
              <p className="section-label mb-1.5">Your Answer</p>
              <p className="text-xs text-text-secondary font-mono leading-relaxed italic">
                "{transcript}"
              </p>
            </div>
          )}

          {/* Next question button */}
          {onNext && (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={onNext}
              className="btn-primary w-full justify-center py-3"
            >
              <Star size={15} />
              Next Question
            </motion.button>
          )}
        </div>
      </div>
    </motion.div>
  )
}
