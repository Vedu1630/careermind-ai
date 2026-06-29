import { useState, useRef, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Upload, FileText, CheckCircle, AlertCircle, ArrowRight, Loader2, Sparkles, TrendingUp, Zap, Target, Brain } from 'lucide-react'
import useStore from '../store/useStore'
import { uploadResume, analyzeResume, getOrCreateToken, getUserId } from '../lib/api'
import SkillBadge from '../components/SkillBadge'
import { useAgentStream } from '../hooks/useAgentStream'

// ── Animated score ring ───────────────────────────────────────────────────
function ScoreRing({ score, label, color = '#6B5CE7', size = 80 }) {
  const r = size * 0.38
  const circ = 2 * Math.PI * r
  const dash = (score / 100) * circ
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E8E4FF" strokeWidth="6" />
          <motion.circle
            cx={size / 2} cy={size / 2} r={r}
            fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: circ - dash }}
            transition={{ duration: 1.4, ease: 'easeOut', delay: 0.2 }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-sans font-extrabold text-base" style={{ color }}>{score}</span>
          <span className="text-xs text-[#888]">/100</span>
        </div>
      </div>
      <span className="text-xs text-[#888]">{label}</span>
    </div>
  )
}

// ── Section detection progress ─────────────────────────────────────────────
function SectionTag({ section }) {
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-[#E8E4FF] text-[#6B5CE7]"
    >
      ✓ {section}
    </motion.span>
  )
}

// ── Animated Analysis Loader (SaaS Style) ──────────────────────────────────
function AnalysisLoader() {
  const [stepIdx, setStepIdx] = useState(0);
  const steps = [
    "Extracting text from your PDF resume...",
    "Analyzing your technical and behavioral skills...",
    "Assessing ATS compatibility and formatting...",
    "Mapping potential career paths and roles...",
    "Generating tailored professional suggestions...",
    "Finalizing your career profile dashboard..."
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setStepIdx(prev => (prev + 1) % steps.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [steps.length]);

  return (
    <div className="flex flex-col items-center justify-center py-8 cursor-default" onClick={(e) => e.stopPropagation()}>
      <motion.div
        animate={{ 
          scale: [1, 1.08, 0.94, 1.08, 1],
          rotate: 360 
        }}
        transition={{ 
          scale: { repeat: Infinity, duration: 3, ease: "easeInOut" },
          rotate: { repeat: Infinity, duration: 12, ease: "linear" }
        }}
        className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 shadow-[0_4px_20px_rgba(107,92,231,0.15)] bg-gradient-to-br from-[#6B5CE7]/10 to-[#8B7CF8]/15 border border-[#6B5CE7]/20"
      >
        <Brain size={28} className="text-[#6B5CE7]" />
      </motion.div>
      <div className="text-center max-w-sm px-4">
        <p className="font-sans font-bold text-[#111] text-base mb-1.5">Analyzing your career...</p>
        <div className="min-h-[32px] flex items-center justify-center">
          <AnimatePresence mode="wait">
            <motion.p
              key={stepIdx}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.3 }}
              className="text-xs text-[#6B5CE7] font-medium font-sans leading-relaxed"
            >
              {steps[stepIdx]}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export default function ResumeUpload() {
  const navigate = useNavigate()
  const { setResumePath, setResumeAnalysis, resume } = useStore()
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('idle') // idle | uploading | analyzing | done | error
  const [progress, setProgress] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const fileInputRef = useRef(null)

  const { events } = useAgentStream()
  const terminalEndRef = useRef(null)

  // Filter events for the Resume Analyzer agent stream
  const resumeEvents = events.filter(
    ev => ev.agent === 'Resume Analyzer' || ev.agent === 'CareerMind AI'
  )

  // Auto-scroll the terminal logs
  useEffect(() => {
    if (status === 'analyzing') {
      terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [resumeEvents.length, status])

  const analysis = resume.analysis
  const analysisData = analysis

  const processFile = useCallback(async (selectedFile) => {
    if (!selectedFile || !selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setErrorMsg('Please upload a PDF file.')
      setStatus('error')
      return
    }

    setResumeAnalysis(null)
    setFile(selectedFile)
    setStatus('uploading')
    setProgress(10)
    setErrorMsg('')

    try {
      // Ensure auth token
      await getOrCreateToken()
      const userId = getUserId()

      // Upload PDF
      setProgress(30)
      const uploadResult = await uploadResume(selectedFile, userId)
      setResumePath(uploadResult.file_path, selectedFile.name)
      setProgress(50)

      // Analyze
      setStatus('analyzing')
      setProgress(60)
      const analysisResult = await analyzeResume({
        filePath: uploadResult.file_path,
        userId,
      })
      setProgress(100)
      setResumeAnalysis(analysisResult)
      setStatus('done')
    } catch (err) {
      console.error('Upload/analyze error:', err)
      setErrorMsg(err?.response?.data?.detail || err.message || 'Analysis failed. Please try again.')
      setStatus('error')
    }
  }, [setResumePath, setResumeAnalysis])

  // Drag handlers
  const onDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const onDragLeave = () => setDragging(false)
  const onDrop = (e) => {
    e.preventDefault(); setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) processFile(f)
  }
  const onFileInput = (e) => {
    const f = e.target.files?.[0]
    if (f) processFile(f)
  }

  const isLoading = status === 'uploading' || status === 'analyzing'

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        {/* Header */}
        <div className="mb-8">
          <p className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase mb-2">Step 01</p>
          <h1 className="font-sans font-extrabold text-3xl sm:text-4xl text-[#111] tracking-tight mb-2">
            Upload Your <span className="bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] bg-clip-text text-transparent">Resume</span>
          </h1>
          <p className="text-[#555]">Upload your PDF resume and our AI will analyze it in seconds.</p>
        </div>

        {/* Drop zone */}
        <AnimatePresence mode="wait">
          {status !== 'done' && (
            <motion.div
              key="uploader"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <div
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                onClick={() => !isLoading && fileInputRef.current?.click()}
                className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-12 transition-all duration-300 cursor-pointer mb-6 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.06)] ${
                  dragging
                    ? 'border-[#6B5CE7] bg-[#F0EEFF] scale-[1.01]'
                    : isLoading
                    ? 'border-[#E8E4FF] cursor-not-allowed opacity-60'
                    : 'border-[#E8E4FF] hover:border-[#6B5CE7] hover:bg-[#FAFAFF]'
                }`}
                style={{ minHeight: 240 }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={onFileInput}
                  className="hidden"
                />

                {isLoading ? (
                  status === 'analyzing' ? (
                    <AnalysisLoader />
                  ) : (
                    <div className="flex flex-col items-center justify-center py-6">
                      <motion.div
                        animate={{ scale: [1, 1.05, 0.95, 1] }}
                        transition={{ repeat: Infinity, duration: 2 }}
                        className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                        style={{ background: 'linear-gradient(135deg, rgba(107,92,231,0.15), rgba(139,124,248,0.15))' }}
                      >
                        <Loader2 size={28} className="text-[#6B5CE7] animate-spin" />
                      </motion.div>
                      <div className="text-center">
                        <p className="font-semibold text-[#111] mb-1">Uploading Resume...</p>
                        <p className="text-sm text-[#555] font-mono">Saving your PDF file securely</p>
                      </div>
                    </div>
                  )
                ) : (
                  <div className="flex flex-col items-center justify-center">
                    <motion.div
                      animate={dragging ? { scale: 1.2 } : { scale: 1 }}
                      className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                      style={{ background: 'linear-gradient(135deg, rgba(107,92,231,0.15), rgba(139,124,248,0.15))' }}
                    >
                      <Upload size={28} className="text-[#6B5CE7]" />
                    </motion.div>
                    <div className="text-center">
                      <p className="font-semibold text-[#111] mb-1">
                        {file ? file.name : 'Drop your resume here'}
                      </p>
                      <p className="text-sm text-[#888]">or click to browse · PDF only</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Progress bar */}
              {isLoading && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-6">
                  <div className="flex justify-between text-xs text-[#888] mb-2">
                    <span>{status === 'uploading' ? 'Uploading PDF' : 'Running AI analysis'}</span>
                    <span>{progress}%</span>
                  </div>
                  <div className="h-1.5 bg-[#F0EEFF] rounded-full overflow-hidden">
                    <motion.div
                      className="h-full rounded-full bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]"
                      animate={{ width: `${progress}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </motion.div>
              )}

              {/* Error */}
              {status === 'error' && (
                <motion.div
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  className="flex items-center gap-2 p-4 rounded-xl bg-[#FEE2E2] border border-red-200 text-[#DC2626] text-sm"
                >
                  <AlertCircle size={16} />
                  {errorMsg}
                </motion.div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Analysis Results ──────────────────────────────────────────── */}
        <AnimatePresence>
          {analysis && (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="space-y-6"
            >
              {/* Score cards row */}
              <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-6">
                <div className="flex items-center gap-2 mb-6">
                  <Sparkles size={18} className="text-[#6B5CE7]" />
                  <h2 className="font-sans font-semibold text-lg text-[#111]">Analysis Results</h2>
                  <span className={`ml-auto inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${
                    analysis.experience_level === 'senior' ? 'bg-[#DCFCE7] text-[#16A34A]' :
                    analysis.experience_level === 'mid' ? 'bg-[#E8E4FF] text-[#6B5CE7]' : 'bg-[#E8E4FF] text-[#6B5CE7]'
                  }`}>
                    {analysis.experience_level} level
                  </span>
                </div>

                {/* Two animated score rings — both recalculated from actual PDF */}
                <div className="grid grid-cols-2 gap-4 mt-4">
                  {[
                    {
                      label: "Overall Score",
                      value: analysisData?.overall_score,
                      grade: analysisData?.overall_grade,
                      color: "#6B5CE7",
                      trackColor: "#E8E4FF"
                    },
                    {
                      label: "ATS Score",
                      value: analysisData?.ats_score,
                      grade: analysisData?.ats_breakdown ? "ATS" : "",
                      color: "#8B7CF8",
                      trackColor: "#E8E4FF"
                    }
                  ].map(({ label, value, grade, color, trackColor }) => {
                    const radius = 54;
                    const circumference = 2 * Math.PI * radius;
                    const dash = value ? (value / 100) * circumference : 0;

                    return (
                      <motion.div
                        key={label}
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="flex flex-col items-center p-4 bg-[#FAFAFF]
                                   border border-[#E8E4FF] rounded-xl"
                      >
                        <svg width="130" height="130" viewBox="0 0 130 130">
                          {/* Track */}
                          <circle
                            cx="65" cy="65" r={radius}
                            fill="none"
                            stroke={trackColor}
                            strokeWidth="8"
                          />
                          {/* Animated fill */}
                          <motion.circle
                            cx="65" cy="65" r={radius}
                            fill="none"
                            stroke={color}
                            strokeWidth="8"
                            strokeLinecap="round"
                            strokeDasharray={circumference}
                            initial={{ strokeDashoffset: circumference }}
                            animate={{ strokeDashoffset: circumference - dash }}
                            transition={{ duration: 1.2, ease: "easeOut", delay: 0.3 }}
                            transform="rotate(-90 65 65)"
                          />
                          {/* Score number */}
                          <text
                            x="65" y="60"
                            textAnchor="middle"
                            dominantBaseline="middle"
                            fill={color}
                            fontSize="22"
                            fontWeight="800"
                            fontFamily="Inter, sans-serif"
                          >
                            {value ?? "--"}
                          </text>
                          <text
                            x="65" y="78"
                            textAnchor="middle"
                            fill="#888888"
                            fontSize="11"
                            fontFamily="Inter, sans-serif"
                          >
                            /100
                          </text>
                        </svg>

                        <span className="text-sm text-[#555] mt-1">{label}</span>

                        {grade && (
                          <span className={`mt-2 px-2 py-0.5 rounded-full text-xs font-medium
                            ${grade === "Excellent" ? "bg-[#DCFCE7] text-[#16A34A] border border-green-200" :
                              grade === "Good"      ? "bg-[#E8E4FF] text-[#6B5CE7] border border-[#E8E4FF]" :
                              grade === "Fair"      ? "bg-[#FEF3C7] text-[#D97706] border border-amber-200" :
                                                      "bg-[#FEE2E2] text-[#DC2626] border border-red-200"}`}
                          >
                            {grade}
                          </span>
                        )}
                      </motion.div>
                    );
                  })}
                </div>

                {/* Overall Score Breakdown — collapsible */}
                {analysisData?.overall_breakdown && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="mt-4 p-4 bg-[#FAFAFF] border border-[#E8E4FF] rounded-xl"
                  >
                    <div className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase mb-3">
                      Score Breakdown
                    </div>
                    <div className="space-y-2">
                      {Object.values(analysisData.overall_breakdown).map((item) => (
                        <div key={item.label} className="flex items-center gap-3">
                          <span className="text-xs text-[#555] w-36 shrink-0">{item.label}</span>
                          <div className="flex-1 h-1.5 bg-[#F0EEFF] rounded-full overflow-hidden">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${(item.score / item.max) * 100}%` }}
                              transition={{ duration: 0.8, ease: "easeOut" }}
                              className="h-full rounded-full bg-[#6B5CE7]"
                            />
                          </div>
                          <span className="text-xs font-mono text-[#555] w-10 text-right">
                            {item.score}/{item.max}
                          </span>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {/* ATS Score Breakdown */}
                {analysisData?.ats_breakdown && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="mt-4 p-4 bg-[#FAFAFF] border border-[#E8E4FF] rounded-xl"
                  >
                    <div className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase mb-3">
                      ATS Score Breakdown
                    </div>
                    <div className="space-y-3">
                      {[
                        { label: "Keyword Match", score: analysisData.ats_breakdown.keywords, max: 40, color: "bg-[#8B7CF8]" },
                        { label: "Required Sections", score: analysisData.ats_breakdown.sections, max: 25, color: "bg-[#6B5CE7]" },
                        { label: "Quantified Achievements", score: analysisData.ats_breakdown.quantification, max: 20, color: "bg-[#22C55E]" },
                        { label: "Format Quality", score: analysisData.ats_breakdown.format, max: 15, color: "bg-orange-400" },
                      ].map(({ label, score, max, color }) => (
                        <div key={label}>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-[#555]">{label}</span>
                            <span className="font-semibold text-[#111]">{score}/{max}</span>
                          </div>
                          <div className="h-1.5 bg-[#F0EEFF] rounded-full overflow-hidden">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${(score / max) * 100}%` }}
                              transition={{ duration: 0.8, ease: "easeOut" }}
                              className={`h-full rounded-full ${color}`}
                            />
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Missing keywords */}
                    {analysisData.missing_keywords?.length > 0 && (
                      <div className="mt-4 border-t border-[#F0EEFF] pt-3">
                        <p className="text-xs font-semibold text-red-500 mb-2 flex items-center gap-1">
                          ⚠️ Missing Keywords ({analysisData.missing_keywords.length})
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {analysisData.missing_keywords.slice(0, 12).map(kw => (
                            <span key={kw} className="text-[10px] bg-red-50 text-red-600 px-2 py-0.5 rounded-full border border-red-100">
                              {kw}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ATS feedback */}
                    {analysisData.feedback?.length > 0 && (
                      <div className="mt-3 border-t border-[#F0EEFF] pt-2 space-y-1">
                        {analysisData.feedback.map((f, i) => (
                          <p key={i} className="text-[11px] text-[#555]">• {f}</p>
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}
              </div>

              {/* Skills found */}
              {analysis.skills_found?.length > 0 && (
                <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <Target size={16} className="text-[#22C55E]" />
                    <h3 className="font-semibold text-[#111]">Skills Detected</h3>
                    <span className="ml-auto inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-[#DCFCE7] text-[#16A34A]">{analysis.skills_found.length} found</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {analysis.skills_found.map((skill) => (
                      <motion.div key={skill} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
                        <SkillBadge skill={skill} variant="matched" />
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}

              {/* Skill gaps */}
              {analysis.skill_gaps?.length > 0 && (
                <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <TrendingUp size={16} className="text-[#D97706]" />
                    <h3 className="font-semibold text-[#111]">Skill Gaps to Address</h3>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {analysis.skill_gaps.map((skill) => (
                      <SkillBadge key={skill} skill={skill} variant="gap" />
                    ))}
                  </div>
                </div>
              )}

              {/* Sections detected */}
              {analysis.sections_detected?.length > 0 && (
                <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-6">
                  <h3 className="font-semibold text-[#111] mb-4 flex items-center gap-2">
                    <FileText size={16} className="text-[#8B7CF8]" /> Sections Detected
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {analysis.sections_detected.map((s) => <SectionTag key={s} section={s} />)}
                  </div>
                </div>
              )}

              {/* Suggestions */}
              {analysis.suggestions?.length > 0 && (
                <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-6">
                  <h3 className="font-semibold text-[#111] mb-4 flex items-center gap-2">
                    <Zap size={16} className="text-[#6B5CE7]" /> AI Suggestions
                  </h3>
                  <ul className="space-y-2">
                    {analysis.suggestions.map((s, i) => (
                      <motion.li
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className="flex items-start gap-2 text-sm text-[#555]"
                      >
                        <span className="text-[#6B5CE7] mt-0.5">→</span> {s}
                      </motion.li>
                    ))}
                  </ul>
                </div>
              )}

              {/* CTA */}
              <div className="flex flex-col sm:flex-row gap-3">
                <motion.button
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => navigate('/jobs')}
                  className="flex-1 flex items-center justify-center gap-2 py-4 px-6 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] text-white font-bold rounded-xl shadow-md hover:shadow-lg transition-shadow"
                >
                  Find Matching Jobs <ArrowRight size={16} />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => { setStatus('idle'); setFile(null); setResumeAnalysis(null); }}
                  className="py-4 px-6 bg-white border border-[#E8E4FF] text-[#6B5CE7] font-semibold rounded-xl hover:border-[#6B5CE7] transition-colors"
                >
                  Upload Different Resume
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
