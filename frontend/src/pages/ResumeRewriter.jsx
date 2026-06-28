import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { FileEdit, Download, Tag, CheckCircle, Loader2, AlertCircle, ArrowRight, Upload } from 'lucide-react'
import useStore from '../store/useStore'
import { rewriteResume, getUserId } from '../lib/api'
import ReactDiffViewer from 'react-diff-viewer-continued'
import SkillBadge from '../components/SkillBadge'
import axios from 'axios'

export default function ResumeRewriter() {
  const navigate = useNavigate()
  const { resume, jobs, rewrite, setRewriteResult, setRewriteLoading } = useStore()

  const [error, setError] = useState('')
  const [isDownloading, setIsDownloading] = useState(false)

  const [showVerifier, setShowVerifier] = useState(false)
  const [verifyFile, setVerifyFile] = useState(null)
  const [verifiedScore, setVerifiedScore] = useState(null)
  const [isVerifying, setIsVerifying] = useState(false)

  const selectedJob = jobs.selectedJob

  const rewriteData = {
    ...rewrite,
    ats_scores: rewrite.atsScores,
    keywords_added: rewrite.keywordsAdded
  }

  const handleVerifyScore = async () => {
    if (!verifyFile) return;
    setIsVerifying(true);

    try {
      const formData = new FormData();
      formData.append("file", verifyFile);
      formData.append("job_description", selectedJob?.description || "");

      const response = await axios.post(
        '/api/score-pdf',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );

      setVerifiedScore(response.data);
    } catch (error) {
      console.error("Score verification failed:", error);
    } finally {
      setIsVerifying(false);
    }
  };

  // Auto-trigger rewrite if we have a selected job but no rewrite yet
  const handleRewrite = useCallback(async () => {
    if (!resume.text && !resume.path) {
      setError('No resume found. Please upload and analyze a resume first.')
      return
    }

    setError('')
    setRewriteLoading(true)

    try {
      const userId = getUserId()
      const result = await rewriteResume({
        resumeText: resume.text,
        resumePath: resume.path,
        job: selectedJob || { title: 'Software Engineer', description: '' },
        userId,
      })
      setRewriteResult(result)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Rewrite failed. Please try again.')
    } finally {
      setRewriteLoading(false)
    }
  }, [resume, selectedJob, setRewriteResult, setRewriteLoading])

  const handleDownloadPDF = async () => {
    setIsDownloading(true);
    try {
      const response = await axios.post(
        `${BACKEND_URL}/api/rewrite/download-pdf`,
        {
          rewritten_pdf_path: rewriteData.rewrittenPdfPath || "",
          rewritten_text:     rewriteData.rewritten        || "",
          original_text:      rewriteData.original         || "",
          resume_path:        resume?.path                 || "",
        },
        { responseType: "blob", timeout: 60000 }
      );

      const blob = new Blob([response.data], { type: "application/pdf" });
      const url  = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href     = url;
      link.download = "rewritten_resume.pdf";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      setShowVerifier(true);
    } catch (err) {
      console.error("PDF download failed:", err);
      setError('Failed to download the rewritten PDF. Please ensure the backend is running.');
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="page-container py-10">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        {/* Header */}
        <div className="mb-8">
          <p className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase mb-2">Step 03</p>
          <h1 className="font-sans font-extrabold text-3xl sm:text-4xl text-[#111] tracking-tight mb-2">
            Resume <span className="bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] bg-clip-text text-transparent">Rewriter</span>
          </h1>
          <p className="text-[#555]">
            AI rewrites your resume to maximize fit for{' '}
            <strong className="text-[#111]">{selectedJob?.title || 'your selected role'}</strong>
            {selectedJob?.company ? ` at ${selectedJob.company}` : ''}.
          </p>
        </div>

        {/* Action bar */}
        <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-5 mb-6 flex flex-col sm:flex-row items-start sm:items-center gap-4">
          {/* Job info */}
          {selectedJob ? (
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-bold text-[#BBB] tracking-widest uppercase mb-1">Targeting Role</p>
              <p className="font-semibold text-[#111] truncate">{selectedJob.title}</p>
              {selectedJob.company && (
                <p className="text-sm text-[#555]">{selectedJob.company}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-[#D97706] flex items-center gap-2 flex-1">
              <AlertCircle size={14} />
              No job selected. <button onClick={() => navigate('/jobs')} className="text-[#6B5CE7] underline">Pick a job</button> first.
            </p>
          )}

          <div className="flex items-center gap-2">
            {rewrite.rewritten && (
              <motion.button
                onClick={handleDownloadPDF}
                disabled={isDownloading}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                           text-white rounded-xl font-bold text-sm transition-colors
                           disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shadow-md"
              >
                {isDownloading ? (
                  <>
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                      className="w-4 h-4 border-2 border-white border-t-transparent rounded-full"
                    />
                    Generating PDF...
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    Download as PDF
                  </>
                )}
              </motion.button>
            )}

            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={handleRewrite}
              disabled={rewrite.isLoading || !selectedJob}
              className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                         text-white rounded-xl font-bold text-sm transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shadow-md"
            >
              {rewrite.isLoading ? (
                <><Loader2 size={15} className="animate-spin" /> Rewriting...</>
              ) : (
                <><FileEdit size={15} /> {rewrite.rewritten ? 'Re-run' : 'Rewrite Resume'}</>
              )}
            </motion.button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-6 flex items-center gap-2 p-4 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#DC2626] text-sm">
            <AlertCircle size={15} /> {error}
          </motion.div>
        )}

        {/* Loading state */}
        {rewrite.isLoading && (
          <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-12 text-center">
            <Loader2 size={36} className="text-[#6B5CE7] animate-spin mx-auto mb-4" />
            <p className="font-semibold text-[#111] mb-1">Gemini is rewriting your resume...</p>
            <p className="text-sm text-[#555]">Adding keywords, quantifying achievements, and optimizing alignment</p>
          </div>
        )}

        {/* Results */}
        <AnimatePresence>
          {rewrite.rewritten && !rewrite.isLoading && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="space-y-5"
            >
              {/* ATS Score Bar */}
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-6 p-4 bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] mb-4"
              >
                <div className="text-center">
                  <div className="text-xs text-[#888] mb-1">Original ATS</div>
                  <div className="text-2xl font-mono font-bold text-[#D97706]">
                    {rewriteData.ats_scores?.original}%
                  </div>
                </div>

                <div className="flex-1 flex items-center gap-2">
                  <div className="flex-1 h-2 bg-[#F0EEFF] rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${rewriteData.ats_scores?.original}%` }}
                      transition={{ duration: 1, delay: 0.2 }}
                      className="h-full bg-[#D97706] rounded-full"
                    />
                  </div>
                  <span className="text-[#6B5CE7] font-bold text-sm">→</span>
                  <div className="flex-1 h-2 bg-[#F0EEFF] rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${rewriteData.ats_scores?.rewritten}%` }}
                      transition={{ duration: 1, delay: 0.5 }}
                      className="h-full bg-[#6B5CE7] rounded-full"
                    />
                  </div>
                </div>

                <div className="text-center">
                  <div className="text-xs text-[#888] mb-1">Rewritten ATS</div>
                  <div className="text-2xl font-mono font-bold text-[#16A34A]">
                    {rewriteData.ats_scores?.rewritten}%
                  </div>
                </div>

                <div className="text-center px-3 py-2 bg-[#DCFCE7] border border-[#BBF7D0] rounded-lg">
                  <div className="text-xs text-[#16A34A] mb-1">Improvement</div>
                  <div className="text-xl font-bold text-[#16A34A]">
                    +{rewriteData.ats_scores?.improvement}%
                  </div>
                </div>
              </motion.div>

              {/* Keywords Added */}
              <div className="flex flex-wrap gap-2 mb-4">
                {rewriteData.keywords_added?.map((kw, i) => (
                  <motion.span
                    key={kw}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: i * 0.05 }}
                    className="px-2.5 py-1 bg-[#E8E4FF] border border-[#D4CFFF]
                               text-[#6B5CE7] text-xs rounded-full font-mono font-medium"
                  >
                    + {kw}
                  </motion.span>
                ))}
              </div>

              {/* Changes summary */}
              {rewrite.changesSummary.length > 0 && (
                <div className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-5">
                  <h3 className="font-semibold text-[#111] mb-3 text-sm flex items-center gap-2">
                    <FileEdit size={14} className="text-[#6B5CE7]" /> Changes Made
                  </h3>
                  <ul className="space-y-1.5">
                    {rewrite.changesSummary.map((c, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-[#555]">
                        <span className="text-[#22C55E] mt-0.5 flex-shrink-0">→</span> {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Score Verifier — shown after download */}
              {showVerifier && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-5"
                >
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-[#6B5CE7] animate-pulse" />
                    <span className="text-sm text-[#111] font-medium">
                      Verify the rewritten PDF score
                    </span>
                  </div>
                  <p className="text-xs text-[#888] mb-3">
                    Upload the PDF you just downloaded to get its real ATS score — 
                    calculated by parsing the actual file, not estimates.
                  </p>
                  <label className="flex items-center gap-3 px-4 py-3 bg-[#FAFAFA]
                                     border-[1.5px] border-dashed border-[#D4CFFF] rounded-[10px]
                                     cursor-pointer hover:border-[#6B5CE7] transition-colors">
                    <Upload className="w-4 h-4 text-[#6B5CE7]" />
                    <span className="text-sm text-[#555]">
                      {verifyFile ? verifyFile.name : "Click to upload rewritten PDF"}
                    </span>
                    <input
                      type="file"
                      accept=".pdf"
                      className="hidden"
                      onChange={(e) => setVerifyFile(e.target.files[0])}
                    />
                  </label>

                  {verifyFile && (
                    <motion.button
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      onClick={handleVerifyScore}
                      disabled={isVerifying}
                      className="mt-3 w-full py-2.5 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                                 text-white text-sm font-bold rounded-xl transition-colors
                                 disabled:opacity-50 cursor-pointer shadow-md"
                    >
                      {isVerifying ? "Analyzing PDF..." : "Get Real ATS Score"}
                    </motion.button>
                  )}

                  {verifiedScore && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="mt-4 grid grid-cols-3 gap-3"
                    >
                      {/* Total ATS */}
                      <div className="col-span-3 flex items-center justify-between
                                      p-3 bg-[#DCFCE7] border border-[#BBF7D0] rounded-lg">
                        <span className="text-sm text-[#16A34A] font-medium">
                          Real ATS Score from PDF
                        </span>
                        <span className="text-2xl font-mono font-bold text-[#16A34A]">
                          {verifiedScore.ats.percentage}%
                        </span>
                      </div>

                      {/* Breakdown pills */}
                      {Object.entries(verifiedScore.ats.breakdown).map(([key, val]) => (
                        <div key={key}
                          className="p-2 bg-[#FAFAFA] border border-[#E8E4FF] rounded-lg text-center"
                        >
                          <div className="text-xs text-[#888] capitalize mb-1">
                            {key.replace('_', ' ')}
                          </div>
                          <div className="text-sm font-mono font-bold text-[#111]">
                            {val.score}/{val.max}
                          </div>
                        </div>
                      ))}

                      {/* Top issues */}
                      {verifiedScore.ats.top_issues?.length > 0 && (
                        <div className="col-span-3 mt-2">
                          <div className="text-xs text-[#888] mb-2 text-left">Top improvements remaining:</div>
                          {verifiedScore.ats.top_issues.map((issue, i) => (
                            <div key={i}
                              className="flex items-start gap-2 text-xs text-[#555] mb-1 text-left"
                            >
                              <span className="text-[#D97706] mt-0.5">→</span>
                              {issue.area}
                            </div>
                          ))}
                        </div>
                      )}
                    </motion.div>
                  )}
                </motion.div>
              )}

              {/* Diff viewer side-by-side grid */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* Left: Original */}
                <div className="flex flex-col h-[500px]">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-[#888]" />
                    <span className="text-sm text-[#555] font-medium">Original Resume</span>
                  </div>
                  <div className="flex-1 overflow-auto bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-4">
                    <pre className="text-sm text-[#333] font-mono whitespace-pre-wrap leading-relaxed">
                      {rewrite.original}
                    </pre>
                  </div>
                </div>
                
                {/* Right: Rewritten with diff */}
                <div className="flex flex-col h-[500px]">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-[#6B5CE7]" />
                    <span className="text-sm text-[#6B5CE7] font-medium">AI Rewritten Resume</span>
                    <span className="ml-auto text-xs text-[#888]">
                      {rewrite.keywordsAdded?.length} keywords added
                    </span>
                  </div>
                  <div className="flex-1 overflow-auto bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
                    <ReactDiffViewer
                      oldValue={rewrite.original}
                      newValue={rewrite.rewritten}
                      splitView={false}
                      useDarkTheme={false}
                      hideLineNumbers={false}
                      styles={{
                        variables: {
                          light: {
                            diffViewerBackground: '#FFFFFF',
                            addedBackground: '#DCFCE7',
                            addedColor: '#16A34A',
                            removedBackground: '#FEE2E2',
                            removedColor: '#DC2626',
                            wordAddedBackground: '#BBF7D0',
                            wordRemovedBackground: '#FECACA',
                            codeFoldBackground: '#F0EEFF',
                            codeFoldGutterBackground: '#F0EEFF',
                          }
                        }
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Next step CTA */}
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => navigate('/interview')}
                className="flex items-center gap-2 justify-center w-full py-4 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                           text-white rounded-xl font-bold text-sm cursor-pointer shadow-md transition-colors"
              >
                Practice the Interview <ArrowRight size={16} />
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Empty state */}
        {!rewrite.rewritten && !rewrite.isLoading && !error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="bg-white border border-[#E8E4FF] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] p-12 text-center">
            <FileEdit size={40} className="text-[#888] mx-auto mb-4" />
            <h2 className="font-sans font-semibold text-lg text-[#111] mb-2">Ready to rewrite?</h2>
            <p className="text-sm text-[#555] mb-6">
              {selectedJob
                ? 'Click "Rewrite Resume" to optimize for this role.'
                : 'Select a job from the Jobs page, then come back here.'}
            </p>
            {!selectedJob && (
              <motion.button
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => navigate('/jobs')}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                           text-white rounded-xl font-bold text-sm cursor-pointer shadow-md transition-colors"
              >
                Browse Jobs <ArrowRight size={15} />
              </motion.button>
            )}
          </motion.div>
        )}
      </motion.div>
    </div>
  )
}
