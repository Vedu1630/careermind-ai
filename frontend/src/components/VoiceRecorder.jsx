import { motion, AnimatePresence } from 'framer-motion'
import { Mic, MicOff, Square, Send, AlertCircle } from 'lucide-react'
import { useVoiceRecorder } from '../hooks/useVoiceRecorder'

// ── Waveform bars ─────────────────────────────────────────────────────────
function WaveformBars({ decibels, isRecording }) {
  const numBars = 20
  const normalized = Math.min(1, (decibels + 100) / 100)

  return (
    <div className="flex items-center justify-center gap-0.5 h-12">
      {Array.from({ length: numBars }).map((_, i) => {
        const base = 0.1
        const variation = Math.sin((i + Date.now() / 200) * 0.8) * 0.3
        const barHeight = isRecording
          ? Math.max(0.1, normalized * (0.6 + variation))
          : base
        return (
          <motion.div
            key={i}
            className={`w-1 rounded-full ${isRecording ? 'bg-danger' : 'bg-text-muted'}`}
            animate={{
              height: `${Math.max(4, barHeight * 48)}px`,
              opacity: isRecording ? 0.7 + Math.random() * 0.3 : 0.3,
            }}
            transition={{
              duration: 0.15,
              repeat: isRecording ? Infinity : 0,
              repeatType: 'reverse',
              delay: i * 0.02,
            }}
          />
        )
      })}
    </div>
  )
}

export default function VoiceRecorder({ onSubmit, isLoading }) {
  const {
    startRecording,
    stopRecording,
    clearRecording,
    audioBlob,
    audioUrl,
    isRecording,
    duration,
    decibels,
    error,
  } = useVoiceRecorder()

  const formatDuration = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

  const handleSubmit = () => {
    if (audioBlob && onSubmit) {
      onSubmit(audioBlob)
    }
  }

  return (
    <div className="card flex flex-col gap-5 items-center">
      {/* Waveform / static bars */}
      <div className="w-full">
        <WaveformBars decibels={decibels} isRecording={isRecording} />
      </div>

      {/* Duration */}
      {(isRecording || audioBlob) && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className={`font-mono text-2xl font-bold ${isRecording ? 'text-danger' : 'text-text-primary'}`}
        >
          {formatDuration(duration)}
        </motion.div>
      )}

      {/* Main button */}
      <div className="flex items-center gap-4">
        {!isRecording && !audioBlob && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={startRecording}
            disabled={isLoading}
            className="w-20 h-20 rounded-full flex items-center justify-center text-white cursor-pointer transition-all"
            style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}
            title="Start recording"
          >
            <Mic size={30} />
          </motion.button>
        )}

        {isRecording && (
          <motion.button
            animate={{ scale: [1, 1.08, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={stopRecording}
            className="w-20 h-20 rounded-full flex items-center justify-center text-white cursor-pointer"
            style={{ background: 'linear-gradient(135deg, #EF4444, #DC2626)', boxShadow: '0 0 30px rgba(239,68,68,0.5)' }}
            title="Stop recording"
          >
            <Square size={26} fill="white" />
          </motion.button>
        )}

        {audioBlob && !isRecording && (
          <div className="flex items-center gap-3">
            {/* Re-record */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => { clearRecording(); }}
              className="w-12 h-12 rounded-full flex items-center justify-center btn-secondary cursor-pointer"
              title="Re-record"
            >
              <MicOff size={18} />
            </motion.button>

            {/* Submit */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={handleSubmit}
              disabled={isLoading}
              className="w-20 h-20 rounded-full flex items-center justify-center text-white cursor-pointer"
              style={{ background: 'linear-gradient(135deg, #10B981, #059669)', boxShadow: '0 0 25px rgba(16,185,129,0.4)' }}
              title="Submit answer"
            >
              {isLoading ? (
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                >
                  <Send size={22} />
                </motion.div>
              ) : (
                <Send size={22} />
              )}
            </motion.button>
          </div>
        )}
      </div>

      {/* Audio playback */}
      <AnimatePresence>
        {audioUrl && !isRecording && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="w-full"
          >
            <audio
              src={audioUrl}
              controls
              className="w-full h-8"
              style={{ accentColor: '#6366F1' }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status text */}
      <p className="text-sm text-text-muted text-center">
        {isLoading
          ? 'Transcribing & scoring your answer...'
          : isRecording
          ? 'Recording — speak clearly, then click stop'
          : audioBlob
          ? 'Review your answer, then submit'
          : 'Click the mic to start your answer'}
      </p>

      {/* Error */}
      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 text-sm text-danger p-3 rounded-xl bg-danger/10 border border-danger/20 w-full"
        >
          <AlertCircle size={14} />
          {error}
        </motion.div>
      )}
    </div>
  )
}
