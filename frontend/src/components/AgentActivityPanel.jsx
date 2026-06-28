import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, ChevronLeft, Brain, Zap, CheckCircle, AlertCircle, Loader2, Wifi, WifiOff, Trash2 } from 'lucide-react'
import { useAgentStream } from '../hooks/useAgentStream'

const AGENT_ICONS = {
  'Resume Analyzer': '📄',
  'Job Scraper': '🔍',
  'Resume Rewriter': '✏️',
  'Mock Interviewer': '🎤',
  'CareerMind AI': '🧠',
}

const STATUS_CONFIG = {
  thinking: { bg: 'bg-[#FEF3C7]', text: 'text-[#D97706]', dot: 'bg-[#D97706]', label: 'Thinking' },
  working:  { bg: 'bg-[#E8E4FF]', text: 'text-[#6B5CE7]', dot: 'bg-[#6B5CE7]', label: 'Working' },
  done:     { bg: 'bg-[#DCFCE7]', text: 'text-[#16A34A]', dot: 'bg-[#16A34A]', label: 'Done' },
  error:    { bg: 'bg-[#FEE2E2]', text: 'text-[#DC2626]', dot: 'bg-[#DC2626]', label: 'Error' },
  connected:{ bg: 'bg-[#DCFCE7]', text: 'text-[#16A34A]', dot: 'bg-[#16A34A]', label: 'Connected' },
}

function AgentEventItem({ event, index }) {
  const config = STATUS_CONFIG[event.status] || STATUS_CONFIG.working
  const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }) : ''

  return (
    <motion.div
      initial={{ opacity: 0, x: 20, height: 0 }}
      animate={{ opacity: 1, x: 0, height: 'auto' }}
      transition={{ duration: 0.3, delay: index * 0.02 }}
      className="flex gap-2.5 py-2.5 border-b border-[#F0EEFF] last:border-0"
    >
      {/* Status dot */}
      <div className="flex-shrink-0 mt-1">
        <div className={`w-1.5 h-1.5 rounded-full ${config.dot} ${event.status === 'thinking' || event.status === 'working' ? 'animate-pulse' : ''}`} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-xs font-semibold text-[#111] truncate">{event.agent}</span>
          <span className={`text-xs font-medium ${config.text}`}>· {config.label}</span>
        </div>
        <p className="text-xs text-[#555] leading-relaxed break-words">{event.message}</p>
        {time && <p className="text-[10px] text-[#BBB] mt-0.5">{time}</p>}
      </div>
    </motion.div>
  )
}

export default function AgentActivityPanel() {
  const [collapsed, setCollapsed] = useState(true)
  const [provider, setProvider] = useState("gemini")
  const { events, isConnected, clearEvents } = useAgentStream()
  const bottomRef = useRef(null)

  // Fetch active provider
  useEffect(() => {
    const apiurl = import.meta.env.VITE_API_URL || "";
    fetch(`${apiurl}/api/health`)
      .then(r => r.json())
      .then(d => {
        if (d.llm_provider) {
          setProvider(d.llm_provider);
        }
      })
      .catch(() => {});
  }, []);

  // Auto-scroll to newest event
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <>
      {/* Toggle button — always visible */}
      <motion.button
        onClick={() => setCollapsed(!collapsed)}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        className="fixed right-4 top-24 z-40 flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#E8E4FF] shadow-card cursor-pointer transition-all duration-200 hover:border-[#6B5CE7] hover:shadow-purple"
        aria-label="Toggle agent panel"
      >
        {collapsed ? <ChevronLeft size={14} className="text-[#888]" /> : <ChevronRight size={14} className="text-[#888]" />}
        <Brain size={14} className={isConnected ? 'text-[#22C55E]' : 'text-[#888]'} />
        {!collapsed && (
          <span className="text-xs font-semibold text-[#555] hidden sm:block">Agents</span>
        )}
        {events.length > 0 && collapsed && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#6B5CE7] text-white text-xs flex items-center justify-center font-bold">
            {Math.min(events.length, 9)}
          </span>
        )}
      </motion.button>

      {/* Panel */}
      <AnimatePresence>
        {!collapsed && (
          <motion.aside
            initial={{ opacity: 0, x: 320 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 320 }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed right-4 top-36 z-30 w-72 bg-white border border-[#E8E4FF] rounded-2xl overflow-hidden shadow-purple"
            style={{ maxHeight: 'calc(100vh - 160px)' }}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-[#E8E4FF] flex items-center justify-between">
              <div className="flex items-center gap-1.5 min-w-0">
                <div className="w-6 h-6 rounded-lg flex items-center justify-center bg-gradient-to-br from-[#6B5CE7] to-[#8B7CF8] flex-shrink-0">
                  <Brain size={12} className="text-white" />
                </div>
                <span className="text-sm font-bold text-[#111] truncate">Agent Activity</span>
                <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                  provider === "groq"
                    ? "bg-amber-100 text-amber-800 border border-amber-200"
                    : "bg-emerald-100 text-emerald-800 border border-emerald-200"
                }`}>
                  {provider === "groq" ? "⚡ Groq" : "✨ Gemini"}
                </span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* Connection indicator */}
                <div className={`flex items-center gap-1 text-xs ${isConnected ? 'text-[#22C55E]' : 'text-[#888]'}`}>
                  {isConnected ? <Wifi size={11} /> : <WifiOff size={11} />}
                  <span>{isConnected ? 'Live' : 'Offline'}</span>
                </div>
                {/* Clear */}
                {events.length > 0 && (
                  <button onClick={clearEvents} className="p-1 rounded-md text-[#888] hover:text-[#EF4444] hover:bg-[#FEE2E2] transition-colors" title="Clear events">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>

            {/* Events list */}
            <div className="overflow-y-auto no-scrollbar px-3" style={{ maxHeight: 'calc(100vh - 240px)' }}>
              {events.length === 0 ? (
                <div className="py-10 text-center">
                  <div className="w-10 h-10 rounded-full bg-[#F0EEFF] flex items-center justify-center mx-auto mb-3">
                    <Zap size={18} className="text-[#888]" />
                  </div>
                  <p className="text-xs text-[#888]">
                    {isConnected
                      ? 'Waiting for agent activity...'
                      : 'Connecting to agent stream...'}
                  </p>
                </div>
              ) : (
                <div className="py-1">
                  <AnimatePresence initial={false}>
                    {events.map((event, i) => (
                      <AgentEventItem key={event.id || i} event={event} index={0} />
                    ))}
                  </AnimatePresence>
                  <div ref={bottomRef} />
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 border-t border-[#E8E4FF]">
              <p className="text-xs text-[#BBB] text-center">
                {events.length} event{events.length !== 1 ? 's' : ''}
              </p>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
