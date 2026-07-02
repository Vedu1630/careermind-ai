import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, AlertCircle, Loader2, CheckCircle, RefreshCw } from "lucide-react";
import api, { BACKEND_URL, wakeUpBackend } from "../lib/api";
import { useStore } from "../store/useStore";

export default function ResumeUpload() {
  const { setResume, setAnalysisData } = useStore();
  const fileInputRef = useRef(null);

  const [dragOver,      setDragOver]      = useState(false);
  const [selectedFile,  setSelectedFile]  = useState(null);
  const [phase,         setPhase]         = useState("idle");
  // phases: idle | waking | uploading | analyzing | done | error
  const [statusMsg,     setStatusMsg]     = useState("");
  const [error,         setError]         = useState(null);
  const [analysisData,  setLocalAnalysis] = useState(null);

  // Wake up backend when page loads
  useEffect(() => {
    const isProduction = !BACKEND_URL.includes("localhost");
    if (isProduction) {
      // Silently wake backend in background so it's ready when user uploads
      wakeUpBackend((status) => {
        if (status === "waking") {
          console.log("Backend waking up in background...");
        }
      });
    }
  }, []);

  const processFile = useCallback(async (file) => {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please upload a PDF file only.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("File too large. Maximum size is 10MB.");
      return;
    }

    setSelectedFile(file);
    setError(null);
    setLocalAnalysis(null);

    const isProduction = !BACKEND_URL.includes("localhost");

    // Step 1: Wake up backend if production
    if (isProduction) {
      setPhase("waking");
      setStatusMsg("Connecting to backend...");

      const isReady = await wakeUpBackend((status) => {
        if (status === "waking") {
          setStatusMsg("Backend is waking up from sleep — this takes 30-60 seconds on first use...");
        } else if (status === "ready") {
          setStatusMsg("Backend ready!");
        } else if (status === "failed") {
          setStatusMsg("Backend unreachable");
        }
      });

      if (!isReady) {
        setPhase("error");
        setError(
          "Cannot reach the backend server. " +
          "Please wait 60 seconds and try again. " +
          "If the problem persists, check if the backend is deployed at dashboard.render.com"
        );
        return;
      }
    }

    // Step 2: Upload
    setPhase("uploading");
    setStatusMsg("Uploading your resume...");

    let filePath = null;
    let retryCount = 0;
    const MAX_UPLOAD_RETRIES = 3;

    while (retryCount < MAX_UPLOAD_RETRIES) {
      try {
        const formData = new FormData();
        formData.append("file", file);

        const uploadRes = await api.post("/api/upload-resume", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 60000,
        });

        filePath = uploadRes.data?.file_path;
        if (filePath) {
          console.log("✅ Upload successful:", filePath);
          break;
        } else {
          throw new Error("Upload succeeded but no file_path returned");
        }
      } catch (err) {
        retryCount++;
        console.warn(`Upload attempt ${retryCount} failed:`, err.message);

        if (retryCount >= MAX_UPLOAD_RETRIES) {
          setPhase("error");
          setError(err.userMessage || `Upload failed after ${MAX_UPLOAD_RETRIES} attempts: ${err.message}`);
          return;
        }

        setStatusMsg(`Upload attempt ${retryCount} failed, retrying...`);
        await new Promise(r => setTimeout(r, 2000 * retryCount));
      }
    }

    // Step 3: Save path to store
    setResume({ path: filePath, filename: file.name });

    // Step 4: Analyze
    setPhase("analyzing");
    setStatusMsg("AI is analyzing your resume...");

    // Small delay to ensure file write is flushed on server
    await new Promise(r => setTimeout(r, 800));

    let analyzeRetry = 0;
    const MAX_ANALYZE_RETRIES = 3;

    while (analyzeRetry < MAX_ANALYZE_RETRIES) {
      try {
        const analyzeRes = await api.post("/api/analyze", {
          resume_path:     filePath,
          job_description: "",
          user_id:         "anon",
        }, { timeout: 60000 });

        const data = analyzeRes.data;
        setLocalAnalysis(data);
        setAnalysisData?.(data);

        // Update store with verified path
        if (data?.resume_path) {
          setResume({ path: data.resume_path, filename: file.name });
        }

        setPhase("done");
        setStatusMsg("Analysis complete!");
        break;

      } catch (err) {
        analyzeRetry++;
        console.warn(`Analyze attempt ${analyzeRetry} failed:`, err.message);

        if (err.response?.status === 404 && analyzeRetry < MAX_ANALYZE_RETRIES) {
          // File not found — re-upload and retry
          setStatusMsg(`Re-uploading resume (attempt ${analyzeRetry + 1})...`);
          await new Promise(r => setTimeout(r, 1500));

          try {
            const formData2 = new FormData();
            formData2.append("file", file);
            const reUpload = await api.post("/api/upload-resume", formData2, {
              headers: { "Content-Type": "multipart/form-data" },
              timeout: 60000,
            });
            filePath = reUpload.data?.file_path || filePath;
            setResume({ path: filePath, filename: file.name });
            setStatusMsg("Retrying analysis...");
            await new Promise(r => setTimeout(r, 1000));
          } catch (reUploadErr) {
            console.error("Re-upload failed:", reUploadErr);
          }
          continue;
        }

        if (analyzeRetry >= MAX_ANALYZE_RETRIES) {
          setPhase("error");
          setError(err.userMessage || err.response?.data?.detail || "Analysis failed. Please try again.");
          return;
        }

        await new Promise(r => setTimeout(r, 2000 * analyzeRetry));
      }
    }
  }, [setResume, setAnalysisData]);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) processFile(file);
  };

  const handleRetry = () => {
    if (selectedFile) {
      processFile(selectedFile);
    } else {
      fileInputRef.current?.click();
    }
  };

  const isLoading = ["waking", "uploading", "analyzing"].includes(phase);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-4xl mx-auto px-6 py-8"
    >
      {/* Header */}
      <div className="mb-6">
        <div className="text-xs font-bold text-[#6B5CE7] tracking-widest mb-1">STEP 01</div>
        <h1 className="text-3xl font-extrabold text-[#111] tracking-tight">
          Upload Your <span className="text-[#6B5CE7]">Resume</span>
        </h1>
        <p className="text-[#888] text-sm mt-1">
          Upload your PDF resume and our AI will analyze it in seconds.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => !isLoading && fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-2xl p-12 text-center
                    transition-all cursor-pointer mb-4 ${
          dragOver
            ? "border-[#6B5CE7] bg-[#F0EEFF] scale-[1.01]"
            : isLoading
              ? "border-[#6B5CE7]/40 bg-[#F0EEFF]/30 cursor-not-allowed"
              : phase === "done"
                ? "border-[#22C55E]/50 bg-[#F0FDF4]"
                : "border-[#E8E4FF] bg-white hover:border-[#6B5CE7] hover:bg-[#F0EEFF]/50"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleFileSelect}
          disabled={isLoading}
        />

        {/* Icon */}
        <div className={`w-16 h-16 rounded-2xl flex items-center justify-center
                         mx-auto mb-4 ${
          phase === "done" ? "bg-[#DCFCE7]" : "bg-[#F0EEFF]"
        }`}>
          {phase === "done" ? (
            <CheckCircle className="w-8 h-8 text-[#22C55E]"/>
          ) : isLoading ? (
            <Loader2 className="w-8 h-8 text-[#6B5CE7] animate-spin"/>
          ) : (
            <Upload className="w-8 h-8 text-[#6B5CE7]"/>
          )}
        </div>

        {/* File name / status */}
        {selectedFile ? (
          <div>
            <p className="text-[15px] font-bold text-[#111] mb-1">
              {selectedFile.name}
            </p>
            <p className={`text-sm font-medium ${
              phase === "waking"    ? "text-amber-500" :
              phase === "uploading" ? "text-[#6B5CE7]" :
              phase === "analyzing" ? "text-[#6B5CE7]" :
              phase === "done"      ? "text-[#22C55E]" :
              "text-[#888]"
            }`}>
              {statusMsg || "Ready to analyze"}
            </p>

            {/* Progress dots */}
            {isLoading && (
              <div className="flex justify-center gap-1.5 mt-3">
                {[0,1,2].map(i => (
                  <motion.div key={i}
                    className="w-1.5 h-1.5 rounded-full bg-[#6B5CE7]"
                    animate={{ y: [0, -5, 0] }}
                    transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </div>
            )}

            {/* Phase indicator */}
            {isLoading && (
              <div className="flex items-center justify-center gap-3 mt-3">
                {["waking","uploading","analyzing"].map((p, i) => (
                  <div key={p} className="flex items-center gap-1.5">
                    <div className={`w-2 h-2 rounded-full transition-all ${
                      phase === p ? "bg-[#6B5CE7] animate-pulse scale-125" :
                      ["waking","uploading","analyzing"].indexOf(phase) > i
                        ? "bg-[#22C55E]"
                        : "bg-[#E8E4FF]"
                    }`}/>
                    <span className="text-xs text-[#888] capitalize">
                      {p === "waking" ? "Wake up" : p}
                    </span>
                    {i < 2 && <span className="text-[#E8E4FF] text-xs">→</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div>
            <p className="text-[15px] font-semibold text-[#333] mb-1">
              Drop your resume here
            </p>
            <p className="text-sm text-[#AAA]">or click to browse · PDF only</p>
          </div>
        )}
      </div>

      {/* Error */}
      <AnimatePresence>
        {phase === "error" && error && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="p-4 bg-red-50 border border-red-100 rounded-2xl mb-4"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5"/>
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-700 mb-1">Upload failed</p>
                <p className="text-sm text-red-600 leading-relaxed">{error}</p>

                {error.includes("sleep") || error.includes("wake") || error.includes("reach") ? (
                  <p className="text-xs text-red-500 mt-2 leading-relaxed">
                    💡 The backend server sleeps on Render's free tier after 15 min of inactivity.
                    The first upload after sleep takes 30-60 seconds. Click retry and wait.
                  </p>
                ) : null}

                <button
                  onClick={handleRetry}
                  className="mt-3 flex items-center gap-2 px-4 py-2 bg-red-600
                             hover:bg-red-700 text-white text-xs font-semibold
                             rounded-lg transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5"/>
                  {error.includes("reach") || error.includes("sleep")
                    ? "Wake up backend and retry"
                    : "Try again"
                  }
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Success — show analysis results */}
      {phase === "done" && analysisData && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Score rings */}
          <div className="grid grid-cols-2 gap-4">
            {[
              { label: "Overall Score", value: analysisData.overall_score,
                color: "#6B5CE7", track: "#E8E4FF" },
              { label: "ATS Score",     value: analysisData.ats_score,
                color: "#22C55E", track: "#DCFCE7" },
            ].map(({ label, value, color, track }) => {
              const r    = 44;
              const circ = 2 * Math.PI * r;
              const dash = circ * ((value || 0) / 100);
              return (
                <div key={label}
                  className="bg-white border border-[#E8E4FF] rounded-2xl p-5
                             flex items-center gap-4 shadow-[0_2px_12px_rgba(107,92,231,0.06)]"
                >
                  <svg width="100" height="100" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r={r}
                      fill="none" stroke={track} strokeWidth="7"/>
                    <motion.circle cx="50" cy="50" r={r}
                      fill="none" stroke={color} strokeWidth="7"
                      strokeLinecap="round"
                      strokeDasharray={circ}
                      initial={{ strokeDashoffset: circ }}
                      animate={{ strokeDashoffset: circ - dash }}
                      transition={{ duration: 1.2, ease: "easeOut" }}
                      transform="rotate(-90 50 50)"
                    />
                    <text x="50" y="46" textAnchor="middle"
                      fill={color} fontSize="18" fontWeight="800"
                      fontFamily="JetBrains Mono, monospace">
                      {value ?? "--"}
                    </text>
                    <text x="50" y="60" textAnchor="middle"
                      fill="#AAA" fontSize="10" fontFamily="Inter, sans-serif">
                      /100
                    </text>
                  </svg>
                  <div>
                    <div className="text-xs text-[#AAA] mb-1">{label}</div>
                    <div className="text-2xl font-extrabold font-mono" style={{color}}>
                      {value ?? "--"}
                    </div>
                    <div className={`text-xs font-semibold mt-1 ${
                      (value||0) >= 75 ? "text-[#22C55E]" :
                      (value||0) >= 55 ? "text-[#6B5CE7]" :
                      (value||0) >= 35 ? "text-amber-500" : "text-red-500"
                    }`}>
                      {(value||0) >= 75 ? "Excellent" :
                       (value||0) >= 55 ? "Good" :
                       (value||0) >= 35 ? "Fair" : "Needs Work"}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Skills found */}
          {analysisData.skills_found?.length > 0 && (
            <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
              <div className="text-xs font-bold text-[#BBB] tracking-widest mb-3">
                SKILLS DETECTED ({analysisData.skills_found.length})
              </div>
              <div className="flex flex-wrap gap-2">
                {analysisData.skills_found.map(skill => (
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
          {analysisData.skill_gaps?.length > 0 && (
            <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
              <div className="text-xs font-bold text-[#BBB] tracking-widest mb-3">
                SKILL GAPS TO ADDRESS
              </div>
              <div className="flex flex-wrap gap-2">
                {analysisData.skill_gaps.map(skill => (
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
          {analysisData.ats_breakdown && (
            <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
              <div className="text-xs font-bold text-[#BBB] tracking-widest mb-3">
                ATS SCORE BREAKDOWN
              </div>
              <div className="space-y-3">
                {Object.values(analysisData.ats_breakdown).map((item) => (
                  <div key={item.label} className="flex items-center gap-3">
                    <span className="text-xs text-[#555] w-44 shrink-0">{item.label}</span>
                    <div className="flex-1 h-2 bg-[#F0EEFF] rounded-full overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${(item.score/item.max)*100}%` }}
                        transition={{ duration: 0.8 }}
                        className={`h-full rounded-full ${
                          item.score/item.max >= 0.7 ? "bg-[#22C55E]" :
                          item.score/item.max >= 0.4 ? "bg-[#6B5CE7]" : "bg-red-400"
                        }`}
                      />
                    </div>
                    <span className="text-xs font-mono text-[#888] w-10 text-right">
                      {item.score}/{item.max}
                    </span>
                  </div>
                ))}
              </div>
              {/* Top issues */}
              {analysisData.top_issues?.length > 0 && (
                <div className="mt-4 pt-3 border-t border-[#F0EEFF]">
                  <div className="text-xs font-bold text-amber-500 mb-2">
                    Top improvements:
                  </div>
                  {analysisData.top_issues.map((issue, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-[#888] mb-1.5">
                      <span className="text-amber-400 shrink-0">→</span>
                      {issue.area}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Suggestions */}
          {analysisData.suggestions?.length > 0 && (
            <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
              <div className="text-xs font-bold text-[#BBB] tracking-widest mb-3">
                AI SUGGESTIONS
              </div>
              <div className="space-y-2">
                {analysisData.suggestions.map((s, i) => (
                  <div key={i} className="flex items-start gap-2.5 text-sm text-[#555]">
                    <div className="w-5 h-5 rounded-full bg-[#F0EEFF] flex items-center
                                    justify-center text-[#6B5CE7] text-xs font-bold shrink-0 mt-0.5">
                      {i+1}
                    </div>
                    {s}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Next step */}
          <div className="bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8] rounded-2xl p-5">
            <p className="text-white font-semibold mb-1">✅ Resume analyzed successfully!</p>
            <p className="text-white/70 text-sm mb-4">
              Go to Job Matches to find roles that fit your profile.
            </p>
            <a href="/jobs"
              className="inline-block px-5 py-2.5 bg-white text-[#6B5CE7]
                         font-bold text-sm rounded-xl hover:bg-[#F0EEFF] transition-colors">
              Find Job Matches →
            </a>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}
