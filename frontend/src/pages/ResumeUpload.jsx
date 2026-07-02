import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload, AlertCircle, Loader2, CheckCircle,
  RefreshCw, ChevronRight, Wifi, WifiOff
} from "lucide-react";
import api, { BACKEND_URL, waitForBackend } from "../lib/api";
import { useStore } from "../store/useStore";
import { useNavigate } from "react-router-dom";

// ── PHASES ────────────────────────────────────────────────────────
// idle       → no file selected
// selected   → file chosen, not started
// connecting → waking up backend (polling)
// uploading  → sending file to backend
// analyzing  → AI analyzing resume
// done       → analysis complete
// error      → something failed

export default function ResumeUpload() {
  const navigate = useNavigate();
  const { setResume } = useStore();

  const fileInputRef      = useRef(null);
  const fileRef           = useRef(null); // keep file for retry

  const [dragOver,     setDragOver]    = useState(false);
  const [phase,        setPhase]       = useState("idle");
  const [fileName,     setFileName]    = useState("");
  const [errorMsg,     setErrorMsg]    = useState("");
  const [analysis,     setAnalysis]    = useState(null);

  // Connecting progress
  const [waitSeconds,  setWaitSeconds] = useState(0);
  const [maxSeconds,   setMaxSeconds]  = useState(120);

  const isProduction = !BACKEND_URL.includes("localhost");

  // ── Main upload flow ───────────────────────────────────────────
  const runUpload = useCallback(async (file) => {
    if (!file) return;

    fileRef.current = file;
    setFileName(file.name);
    setPhase("selected");
    setErrorMsg("");
    setAnalysis(null);

    // Validate
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setPhase("error");
      setErrorMsg("Please upload a PDF file. Other formats are not supported.");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setPhase("error");
      setErrorMsg("File is too large (max 15MB). Please compress your PDF.");
      return;
    }
    if (file.size < 1000) {
      setPhase("error");
      setErrorMsg("File seems too small. Please check your PDF is not empty.");
      return;
    }

    // ── STEP 1: Connect to backend ─────────────────────────────
    if (isProduction) {
      setPhase("connecting");
      setWaitSeconds(0);

      // First quick check — maybe backend is already awake
      let alreadyAwake = false;
      try {
        const quick = await Promise.race([
          fetch(`${BACKEND_URL}/health`),
          new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 5000))
        ]);
        if (quick.ok) alreadyAwake = true;
      } catch {
        alreadyAwake = false;
      }

      if (!alreadyAwake) {
        // Backend sleeping — poll until awake
        const awake = await waitForBackend(
          (secs, max) => {
            setWaitSeconds(secs);
            setMaxSeconds(max);
          },
          120 // wait up to 2 minutes
        );

        if (!awake) {
          setPhase("error");
          setErrorMsg(
            "Backend did not respond within 2 minutes. " +
            "The server may be down. Check dashboard.render.com for your service status."
          );
          return;
        }
      }
    }

    // ── STEP 2: Upload file ────────────────────────────────────
    setPhase("uploading");

    let filePath = null;
    const MAX_UPLOAD_TRIES = 3;

    for (let attempt = 1; attempt <= MAX_UPLOAD_TRIES; attempt++) {
      try {
        const formData = new FormData();
        formData.append("file", file);

        const res = await api.post("/api/upload-resume", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 60000,
        });

        filePath = res.data?.file_path;
        if (!filePath) throw new Error("No file_path in upload response");

        console.log("✅ Uploaded:", filePath);
        break;

      } catch (err) {
        console.warn(`Upload attempt ${attempt}/${MAX_UPLOAD_TRIES} failed:`, err.message);

        if (attempt === MAX_UPLOAD_TRIES) {
          setPhase("error");
          setErrorMsg(
            err.userMessage ||
            `Upload failed after ${MAX_UPLOAD_TRIES} attempts. ` +
            "Check your internet connection and try again."
          );
          return;
        }

        // Wait before retry
        await new Promise(r => setTimeout(r, 2000 * attempt));
      }
    }

    // Save to store
    setResume({ path: filePath, filename: file.name });

    // Small delay for disk write
    await new Promise(r => setTimeout(r, 500));

    // ── STEP 3: Analyze ────────────────────────────────────────
    setPhase("analyzing");

    const MAX_ANALYZE_TRIES = 3;

    for (let attempt = 1; attempt <= MAX_ANALYZE_TRIES; attempt++) {
      try {
        const res = await api.post("/api/analyze", {
          resume_path:     filePath,
          job_description: "",
          user_id:         "anon",
        }, { timeout: 90000 });

        const data = res.data;
        if (!data) throw new Error("Empty response from analyze endpoint");

        setAnalysis(data);

        // Update path if backend returned a verified one
        if (data.resume_path) {
          setResume({ path: data.resume_path, filename: file.name });
        }

        setPhase("done");
        return;

      } catch (err) {
        console.warn(`Analyze attempt ${attempt}/${MAX_ANALYZE_TRIES} failed:`, err.message);

        // If file not found — re-upload
        if (err.response?.status === 404 && attempt < MAX_ANALYZE_TRIES) {
          console.log("File not found — re-uploading...");
          try {
            const fd2 = new FormData();
            fd2.append("file", file);
            const reup = await api.post("/api/upload-resume", fd2, {
              headers: { "Content-Type": "multipart/form-data" },
              timeout: 60000,
            });
            if (reup.data?.file_path) {
              filePath = reup.data.file_path;
              setResume({ path: filePath, filename: file.name });
            }
            await new Promise(r => setTimeout(r, 1000));
            continue;
          } catch (reupErr) {
            console.error("Re-upload failed:", reupErr.message);
          }
        }

        if (attempt === MAX_ANALYZE_TRIES) {
          setPhase("error");
          setErrorMsg(
            err.userMessage ||
            err.response?.data?.detail ||
            "Analysis failed. Your resume was uploaded but AI analysis could not complete. Please try again."
          );
          return;
        }

        await new Promise(r => setTimeout(r, 2000 * attempt));
      }
    }
  }, [isProduction, setResume]);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) runUpload(file);
    // Reset input so same file can be selected again
    e.target.value = "";
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) runUpload(file);
  };

  const handleRetry = () => {
    if (fileRef.current) {
      runUpload(fileRef.current);
    } else {
      fileInputRef.current?.click();
    }
  };

  const isLoading = ["connecting","uploading","analyzing"].includes(phase);

  // ── RENDER ─────────────────────────────────────────────────────
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-4xl mx-auto px-6 py-8"
    >
      {/* Header */}
      <div className="mb-6">
        <div className="text-xs font-bold text-[#6B5CE7] tracking-widest mb-1 uppercase">
          Step 01
        </div>
        <h1 className="text-3xl font-extrabold text-[#111] tracking-tight">
          Upload Your{" "}
          <span className="text-[#6B5CE7]">Resume</span>
        </h1>
        <p className="text-[#888] text-sm mt-1">
          Upload your PDF resume and our AI will analyze it in seconds.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => !isLoading && fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-2xl p-14 text-center
                    transition-all select-none ${
          isLoading
            ? "border-[#6B5CE7]/40 bg-[#F0EEFF]/20 cursor-not-allowed"
            : dragOver
              ? "border-[#6B5CE7] bg-[#F0EEFF] cursor-copy scale-[1.01]"
              : phase === "done"
                ? "border-[#22C55E]/40 bg-[#F0FDF4] cursor-pointer"
                : phase === "error"
                  ? "border-red-200 bg-red-50/30 cursor-pointer"
                  : "border-[#E8E4FF] bg-white hover:border-[#6B5CE7] hover:bg-[#F0EEFF]/30 cursor-pointer"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleFileChange}
        />

        {/* Icon */}
        <div className={`w-16 h-16 rounded-2xl flex items-center justify-center
                         mx-auto mb-5 transition-all ${
          phase === "done"       ? "bg-[#DCFCE7]" :
          phase === "error"      ? "bg-red-100" :
          phase === "connecting" ? "bg-amber-50" :
          "bg-[#F0EEFF]"
        }`}>
          {phase === "done" ? (
            <CheckCircle className="w-8 h-8 text-[#22C55E]"/>
          ) : phase === "error" ? (
            <WifiOff className="w-8 h-8 text-red-400"/>
          ) : isLoading ? (
            <Loader2 className="w-8 h-8 text-[#6B5CE7] animate-spin"/>
          ) : (
            <Upload className="w-8 h-8 text-[#6B5CE7]"/>
          )}
        </div>

        {/* Text */}
        {phase === "idle" ? (
          <>
            <p className="text-[15px] font-semibold text-[#333] mb-1">
              Drop your resume here
            </p>
            <p className="text-sm text-[#AAA]">or click to browse · PDF only</p>
          </>
        ) : (
          <>
            <p className="text-[15px] font-bold text-[#111] mb-2">{fileName}</p>

            {phase === "selected" && (
              <p className="text-sm text-[#6B5CE7]">Starting upload...</p>
            )}

            {phase === "connecting" && (
              <div>
                <p className="text-sm font-semibold text-amber-600 mb-2">
                  Waking up backend server...
                </p>
                <p className="text-xs text-[#888] mb-3">
                  Render free tier sleeps after 15 min. First start takes 30-90 seconds.
                </p>
                {/* Progress bar */}
                <div className="max-w-xs mx-auto">
                  <div className="flex justify-between text-xs text-[#AAA] mb-1">
                    <span>Waiting...</span>
                    <span>{waitSeconds}s / {maxSeconds}s</span>
                  </div>
                  <div className="h-2 bg-[#E8E4FF] rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-amber-400 to-[#6B5CE7] rounded-full"
                      animate={{ width: `${Math.min((waitSeconds / maxSeconds) * 100, 95)}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                  <p className="text-xs text-amber-500 mt-2">
                    {waitSeconds < 30
                      ? "Sending wake-up signal..."
                      : waitSeconds < 60
                        ? "Almost there..."
                        : "Taking longer than usual, still trying..."
                    }
                  </p>
                </div>
              </div>
            )}

            {phase === "uploading" && (
              <p className="text-sm text-[#6B5CE7] font-medium">
                Uploading your resume...
              </p>
            )}

            {phase === "analyzing" && (
              <p className="text-sm text-[#6B5CE7] font-medium">
                AI is analyzing your resume...
              </p>
            )}

            {phase === "done" && (
              <p className="text-sm text-[#22C55E] font-semibold">
                ✅ Analysis complete!
              </p>
            )}

            {/* Animated dots for loading states */}
            {isLoading && (
              <div className="flex justify-center gap-1.5 mt-4">
                {[0, 1, 2].map(i => (
                  <motion.div key={i}
                    className={`w-2 h-2 rounded-full ${
                      phase === "connecting" ? "bg-amber-400" : "bg-[#6B5CE7]"
                    }`}
                    animate={{ y: [0, -6, 0] }}
                    transition={{
                      duration: 0.7,
                      repeat: Infinity,
                      delay: i * 0.15,
                    }}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Error card */}
      <AnimatePresence>
        {phase === "error" && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4 p-5 bg-red-50 border border-red-100 rounded-2xl"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5"/>
              <div className="flex-1">
                <p className="text-[14px] font-bold text-red-700 mb-1">
                  Upload failed
                </p>
                <p className="text-sm text-red-600 leading-relaxed mb-4">
                  {errorMsg}
                </p>

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={handleRetry}
                    className="flex items-center gap-2 px-4 py-2.5 bg-[#6B5CE7]
                               hover:bg-[#5A4DD6] text-white text-sm font-semibold
                               rounded-xl transition-colors"
                  >
                    <RefreshCw className="w-4 h-4"/>
                    Try Again
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-4 py-2.5 bg-white
                               border border-red-200 text-red-600 text-sm font-semibold
                               rounded-xl hover:bg-red-50 transition-colors"
                  >
                    <Upload className="w-4 h-4"/>
                    Choose Different File
                  </button>
                  {isProduction && (
                    <a
                      href="https://dashboard.render.com"
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 px-4 py-2.5 bg-white
                                 border border-[#E8E4FF] text-[#888] text-sm
                                 rounded-xl hover:bg-[#F0EEFF] transition-colors"
                    >
                      <Wifi className="w-4 h-4"/>
                      Check Render Status
                    </a>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Analysis results */}
      <AnimatePresence>
        {phase === "done" && analysis && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-6 space-y-4"
          >
            {/* Score rings */}
            <div className="grid grid-cols-2 gap-4">
              {[
                {
                  label: "Overall Score",
                  value: analysis.overall_score ?? analysis.ats_score ?? 0,
                  color: "#6B5CE7",
                  track: "#E8E4FF",
                },
                {
                  label: "ATS Score",
                  value: analysis.ats_score ?? 0,
                  color: "#22C55E",
                  track: "#DCFCE7",
                },
              ].map(({ label, value, color, track }) => {
                const r    = 44;
                const circ = 2 * Math.PI * r;
                const dash = circ * (Math.min(value, 100) / 100);
                const grade =
                  value >= 75 ? "Excellent" :
                  value >= 55 ? "Good" :
                  value >= 35 ? "Fair" : "Needs Work";

                return (
                  <div key={label}
                    className="bg-white border border-[#E8E4FF] rounded-2xl p-5
                               flex items-center gap-4
                               shadow-[0_2px_12px_rgba(107,92,231,0.06)]"
                  >
                    <svg width="100" height="100" viewBox="0 0 100 100">
                      <circle cx="50" cy="50" r={r}
                        fill="none" stroke={track} strokeWidth="7"/>
                      <motion.circle
                        cx="50" cy="50" r={r}
                        fill="none"
                        stroke={color}
                        strokeWidth="7"
                        strokeLinecap="round"
                        strokeDasharray={circ}
                        initial={{ strokeDashoffset: circ }}
                        animate={{ strokeDashoffset: circ - dash }}
                        transition={{ duration: 1.2, ease: "easeOut", delay: 0.2 }}
                        transform="rotate(-90 50 50)"
                      />
                      <text x="50" y="46" textAnchor="middle"
                        fill={color} fontSize="18" fontWeight="800"
                        fontFamily="JetBrains Mono, monospace">
                        {value}
                      </text>
                      <text x="50" y="60" textAnchor="middle"
                        fill="#BBB" fontSize="10" fontFamily="Inter, sans-serif">
                        / 100
                      </text>
                    </svg>
                    <div>
                      <div className="text-xs text-[#AAA] mb-1">{label}</div>
                      <div className="text-2xl font-extrabold font-mono" style={{ color }}>
                        {value}
                      </div>
                      <div className="text-xs font-semibold mt-1" style={{ color }}>
                        {grade}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Skills found */}
            {analysis.skills_found?.length > 0 && (
              <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
                <div className="text-xs font-bold text-[#BBB] tracking-widest mb-3 uppercase">
                  Skills Detected ({analysis.skills_found.length})
                </div>
                <div className="flex flex-wrap gap-2">
                  {analysis.skills_found.map(skill => (
                    <span key={skill}
                      className="px-2.5 py-1 bg-[#E8E4FF] text-[#6B5CE7]
                                 text-xs font-semibold rounded-full">
                      ✓ {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Skill gaps */}
            {analysis.skill_gaps?.length > 0 && (
              <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
                <div className="text-xs font-bold text-[#BBB] tracking-widest mb-3 uppercase">
                  Skill Gaps
                </div>
                <div className="flex flex-wrap gap-2">
                  {analysis.skill_gaps.map(skill => (
                    <span key={skill}
                      className="px-2.5 py-1 bg-[#FEF3C7] text-[#D97706]
                                 text-xs font-semibold rounded-full">
                      + {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* ATS Breakdown */}
            {analysis.ats_breakdown && (
              <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
                <div className="text-xs font-bold text-[#BBB] tracking-widest mb-4 uppercase">
                  ATS Score Breakdown
                </div>
                <div className="space-y-3">
                  {Object.values(analysis.ats_breakdown).map(item => {
                    const pct = Math.round((item.score / item.max) * 100);
                    return (
                      <div key={item.label} className="flex items-center gap-3">
                        <span className="text-xs text-[#555] w-44 shrink-0">
                          {item.label}
                        </span>
                        <div className="flex-1 h-2 bg-[#F0EEFF] rounded-full overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.8, ease: "easeOut" }}
                            className={`h-full rounded-full ${
                              pct >= 70 ? "bg-[#22C55E]" :
                              pct >= 40 ? "bg-[#6B5CE7]" : "bg-red-400"
                            }`}
                          />
                        </div>
                        <span className="text-xs font-mono text-[#888] w-12 text-right">
                          {item.score}/{item.max}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {analysis.top_issues?.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-[#F0EEFF]">
                    <div className="text-xs font-bold text-amber-500 mb-2 uppercase tracking-wide">
                      Top improvements needed
                    </div>
                    {analysis.top_issues.map((issue, i) => (
                      <div key={i}
                        className="flex items-start gap-2 text-xs text-[#666] mb-2"
                      >
                        <span className="text-amber-400 shrink-0 mt-0.5">→</span>
                        {issue.area}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Suggestions */}
            {analysis.suggestions?.length > 0 && (
              <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
                <div className="text-xs font-bold text-[#BBB] tracking-widest mb-3 uppercase">
                  AI Suggestions
                </div>
                <div className="space-y-2.5">
                  {analysis.suggestions.map((s, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <div className="w-5 h-5 rounded-full bg-[#E8E4FF] flex items-center
                                      justify-center text-[#6B5CE7] text-xs font-bold shrink-0 mt-0.5">
                        {i + 1}
                      </div>
                      <p className="text-sm text-[#555] leading-relaxed">{s}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Next step CTA */}
            <div className="bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                            rounded-2xl p-6 flex items-center justify-between">
              <div>
                <p className="text-white font-bold text-[15px] mb-1">
                  Resume analyzed successfully!
                </p>
                <p className="text-white/70 text-sm">
                  Find jobs that match your profile and tailor your resume.
                </p>
              </div>
              <button
                onClick={() => navigate("/jobs")}
                className="flex items-center gap-2 px-5 py-3 bg-white text-[#6B5CE7]
                           font-bold text-sm rounded-xl hover:bg-[#F0EEFF]
                           transition-colors shrink-0 ml-4"
              >
                Find Jobs
                <ChevronRight className="w-4 h-4"/>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
