import { useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle, XCircle, AlertCircle, Loader2, RefreshCw } from "lucide-react";
import api, { BACKEND_URL } from "../lib/api";

const STATUS_ICON = {
  ok:       <CheckCircle className="w-5 h-5 text-green-500"/>,
  error:    <XCircle className="w-5 h-5 text-red-500"/>,
  warning:  <AlertCircle className="w-5 h-5 text-amber-500"/>,
  loading:  <Loader2 className="w-5 h-5 text-[#6B5CE7] animate-spin"/>,
  idle:     <div className="w-5 h-5 rounded-full border-2 border-[#E8E4FF]"/>,
};

const getStatus = (val) => {
  if (!val) return "idle";
  const s = String(val);
  if (s.includes("✅")) return "ok";
  if (s.includes("❌")) return "error";
  if (s.includes("⚠️")) return "warning";
  return "ok";
};

export default function AgentStatus() {
  const [results,  setResults]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);
  const [lastRun,  setLastRun]  = useState(null);

  const runDiagnose = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/diagnose", { timeout: 60000 });
      setResults(res.data);
      setLastRun(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err.userMessage || "Cannot reach backend. Is it running?");
    } finally {
      setLoading(false);
    }
  };

  const agents = results ? [
    { label: "Gemini LLM (Resume/Jobs)", key: "gemini_llm",       desc: "Resume analysis, job scoring, and rewriting tasks" },
    { label: "Groq LLaMA 3 (Interview)", key: "groq_llm",         desc: "Mock interview questions and answer scoring" },
    { label: "Groq LLaMA 3 (Coach)",     key: "groq_coach",       desc: "Daily English coach live conversation agent" },
    { label: "Gemini Embeddings",        key: "gemini_embeddings", desc: "Vector embeddings for RAG" },
    { label: "ChromaDB Vector Store",    key: "chromadb",          desc: "Local vector database" },
    { label: "File Upload Directory",    key: "uploads_dir",       desc: "PDF storage" },
    { label: "Skills Knowledge Base",    key: "skills_kb",         desc: "RAG knowledge source" },
  ] : [];

  const envVars = results?.env_vars ? Object.entries(results.env_vars) : [];
  const summary = results?.SUMMARY || "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-4xl mx-auto px-6 py-8"
    >
      {/* Header */}
      <div className="mb-6">
        <div className="text-xs font-bold text-[#6B5CE7] tracking-widest mb-1">DIAGNOSTICS</div>
        <h1 className="text-3xl font-extrabold text-[#111] tracking-tight">
          Agent <span className="text-[#6B5CE7]">Status</span>
        </h1>
        <p className="text-[#888] text-sm mt-1">
          Test all AI agents and connections live
        </p>
      </div>

      {/* Backend URL */}
      <div className="bg-white border border-[#E8E4FF] rounded-xl p-4 mb-4
                      flex items-center justify-between">
        <div>
          <div className="text-xs text-[#888] mb-1">Backend URL</div>
          <code className="text-[13px] font-mono text-[#6B5CE7]">{BACKEND_URL}</code>
        </div>
        <button
          onClick={runDiagnose}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r
                     from-[#6B5CE7] to-[#8B7CF8] rounded-xl text-[13px]
                     font-bold text-white hover:opacity-90 transition-opacity
                     disabled:opacity-60"
        >
          {loading
            ? <><Loader2 className="w-4 h-4 animate-spin"/> Testing...</>
            : <><RefreshCw className="w-4 h-4"/> Run Diagnostics</>
          }
        </button>
      </div>

      {lastRun && (
        <p className="text-[11px] text-[#BBB] mb-4">Last checked: {lastRun}</p>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-2">
            <XCircle className="w-5 h-5 text-red-500 shrink-0"/>
            <p className="text-[13px] text-red-700 font-medium">{error}</p>
          </div>
        </div>
      )}

      {/* Summary banner */}
      {summary && (
        <div className={`rounded-xl p-4 mb-6 border ${
          summary.includes("✅ ALL")
            ? "bg-green-50 border-green-200"
            : summary.includes("❌")
              ? "bg-red-50 border-red-200"
              : "bg-amber-50 border-amber-200"
        }`}>
          <p className="text-[14px] font-bold text-center">{summary}</p>
        </div>
      )}

      {/* Environment Variables */}
      {envVars.length > 0 && (
        <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5 mb-4">
          <h3 className="text-[13px] font-bold text-[#111] mb-4 flex items-center gap-2">
            🔑 Environment Variables
          </h3>
          <div className="space-y-2">
            {envVars.map(([key, val]) => (
              <div key={key} className="flex items-start gap-3">
                {STATUS_ICON[getStatus(val)]}
                <div className="flex-1 min-w-0">
                  <span className="text-[12px] font-mono font-bold text-[#333]">{key}</span>
                  <p className="text-[11px] text-[#888] mt-0.5 break-all">
                    {typeof val === "object" ? JSON.stringify(val) : String(val)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Agent Results */}
      {agents.length > 0 && (
        <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5">
          <h3 className="text-[13px] font-bold text-[#111] mb-4 flex items-center gap-2">
            🤖 Agent Tests
          </h3>
          <div className="space-y-3">
            {agents.map(({ label, key, desc }) => {
              const val    = results[key];
              const status = val ? getStatus(val) : "idle";
              return (
                <motion.div
                  key={key}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`flex items-start gap-3 p-3 rounded-xl border ${
                    status === "ok"      ? "bg-green-50  border-green-100"  :
                    status === "error"   ? "bg-red-50    border-red-100"    :
                    status === "warning" ? "bg-amber-50  border-amber-100"  :
                    "bg-[#FAFAFA] border-[#F0EEFF]"
                  }`}
                >
                  <div className="shrink-0 mt-0.5">{STATUS_ICON[status]}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-semibold text-[#111]">{label}</div>
                    <div className="text-[11px] text-[#888]">{desc}</div>
                    {val && (
                      <div className="text-[11px] font-mono text-[#555] mt-1 break-all">
                        {String(val).replace(/[✅❌⚠️]/g, "").trim()}
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}

      {/* Initial state */}
      {!results && !loading && !error && (
        <div className="text-center py-16 bg-white border border-[#E8E4FF] rounded-2xl">
          <div className="text-5xl mb-4">🔍</div>
          <h3 className="text-[15px] font-bold text-[#111] mb-2">Ready to diagnose</h3>
          <p className="text-[13px] text-[#888] mb-6">
            Click "Run Diagnostics" to test all agents and connections
          </p>
          <button
            onClick={runDiagnose}
            className="px-6 py-3 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                       rounded-xl text-[14px] font-bold text-white
                       hover:opacity-90 transition-opacity"
          >
            Run Diagnostics →
          </button>
        </div>
      )}
    </motion.div>
  );
}
