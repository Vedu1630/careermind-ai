import { useNavigate } from 'react-router-dom'
import { FileSearch, Briefcase, Brain, Mic, Flame, Sparkles } from 'lucide-react'

const AGENTS = [
  {
    id: 'resume',
    label: 'Resume Analyzer',
    subtitle: 'Scan & Score',
    icon: FileSearch,
    color: '#6366F1', // Indigo
    to: '/upload',
    x: 250,
    y: 88,
  },
  {
    id: 'rewrite',
    label: 'Smart Rewriter',
    subtitle: 'Optimize CV',
    icon: Brain,
    color: '#10B981', // Emerald
    to: '/rewrite',
    x: 404,
    y: 200,
  },
  {
    id: 'jobs',
    label: 'Job Matcher',
    subtitle: 'Live Match',
    icon: Briefcase,
    color: '#22D3EE', // Cyan
    to: '/jobs',
    x: 345,
    y: 381,
  },
  {
    id: 'interview',
    label: 'Mock Interview',
    subtitle: 'Voice Practice',
    icon: Mic,
    color: '#F59E0B', // Amber
    to: '/interview',
    x: 155,
    y: 381,
  },
  {
    id: 'coach',
    label: 'English Coach',
    subtitle: 'Fluency Session',
    icon: Flame,
    color: '#EC4899', // Pink
    to: '/daily-coach',
    x: 96,
    y: 200,
  },
]

export default function ThreeDNet() {
  const navigate = useNavigate()

  return (
    <div
      className="relative w-full aspect-square max-w-[480px] mx-auto overflow-visible select-none flex items-center justify-center"
    >
      {/* ── Static Plate ── */}
      <div className="relative w-full h-full flex items-center justify-center">
        
        {/* ── Symmetrical Connection Lines (SVG Grid Backdrop) ── */}
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none z-0 overflow-visible"
          viewBox="0 0 500 500"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Faint background grid crosshairs */}
          <line x1="250" y1="30" x2="250" y2="470" stroke="rgba(255, 255, 255, 0.015)" strokeWidth="1" strokeDasharray="2, 10" />
          <line x1="30" y1="250" x2="470" y2="250" stroke="rgba(255, 255, 255, 0.015)" strokeWidth="1" strokeDasharray="2, 10" />
          
          {/* Symmetrical Pentagram circle paths */}
          <circle cx="250" cy="250" r="162" fill="none" stroke="rgba(255, 255, 255, 0.012)" strokeWidth="1" />
          <circle cx="250" cy="250" r="70" fill="none" stroke="rgba(255, 255, 255, 0.008)" strokeWidth="1" strokeDasharray="4, 8" />

          {/* Symmetrical Laser lines connecting each node to the core */}
          {AGENTS.map((agent) => (
            <g key={`laser-${agent.id}`}>
              {/* Base line */}
              <line
                x1="250"
                y1="250"
                x2={agent.x}
                y2={agent.y}
                stroke={agent.color}
                strokeWidth="1.2"
                strokeOpacity="0.15"
              />
              {/* Subtle accent light core line */}
              <line
                x1="250"
                y1="250"
                x2={agent.x}
                y2={agent.y}
                stroke={agent.color}
                strokeWidth="2"
                strokeOpacity="0.04"
                style={{ filter: `drop-shadow(0 0 6px ${agent.color})` }}
              />
            </g>
          ))}
        </svg>

        {/* ── Central AI Core Node ── */}
        <div
          className="absolute left-1/2 top-1/2 z-10 w-[76px] h-[76px] pointer-events-none rounded-full"
          style={{
            transform: 'translate3d(-50%, -50%, 0)',
            background: 'radial-gradient(circle at 30% 30%, rgba(99, 102, 241, 0.65) 0%, rgba(10, 11, 23, 0.96) 72%, transparent 100%)',
            border: '1.5px solid rgba(255, 255, 255, 0.12)',
            boxShadow: '0 0 30px -15px rgba(99, 102, 241, 0.7), inset 0 0 12px rgba(255, 255, 255, 0.05)',
            backdropFilter: 'blur(8px)',
          }}
        >
          {/* Inner ambient energy core */}
          <div 
            className="absolute inset-1.5 rounded-full opacity-30 filter blur-sm"
            style={{
              background: 'radial-gradient(circle, #22D3EE 0%, transparent 70%)',
            }}
          />
          {/* Sparkle emblem */}
          <div className="absolute inset-0 flex items-center justify-center text-white/20">
            <Sparkles size={16} />
          </div>
        </div>

        {/* ── 5 Symmetrical Agent Cards ── */}
        {AGENTS.map((agent) => {
          const Icon = agent.icon
          const pctX = (agent.x / 500) * 100
          const pctY = (agent.y / 500) * 100

          return (
            <div
              key={agent.id}
              onClick={() => navigate(agent.to)}
              className="absolute z-20 cursor-pointer select-none rounded-xl p-2 flex items-center gap-2.5 border transition-all duration-200 hover:bg-slate-900/50 hover:border-white/20 hover:shadow-[0_4px_20px_-10px_rgba(255,255,255,0.1)] -translate-x-1/2 -translate-y-1/2"
              style={{
                left: `${pctX}%`,
                top: `${pctY}%`,
                width: '166px',
                height: '56px',
                borderColor: 'rgba(255, 255, 255, 0.08)',
                background: 'rgba(8, 9, 21, 0.60)',
                backdropFilter: 'blur(12px)',
              }}
            >
              {/* Left Capsule: Icon */}
              <div
                className="w-8.5 h-8.5 rounded-lg flex items-center justify-center border transition-colors duration-200 flex-shrink-0"
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  borderColor: 'rgba(255, 255, 255, 0.05)',
                }}
              >
                <Icon 
                  size={15} 
                  style={{ color: agent.color }} 
                />
              </div>

              {/* Right: Title & Subtitle */}
              <div className="flex flex-col text-left min-w-0 flex-grow">
                <span 
                  className="text-[11.5px] font-bold tracking-wide text-text-primary truncate font-display"
                >
                  {agent.label}
                </span>
                <span className="text-[9px] text-text-muted font-semibold truncate mt-0.5">
                  {agent.subtitle}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
