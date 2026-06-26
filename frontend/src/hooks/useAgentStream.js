import { useEffect, useRef, useCallback } from 'react'
import useStore from '../store/useStore'
import { getUserId } from '../lib/api'

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.hostname}:8000`
const RECONNECT_DELAY = 3000
const MAX_RECONNECT_ATTEMPTS = 5

/**
 * useAgentStream — WebSocket hook for real-time agent event streaming.
 * Automatically reconnects on disconnect (up to MAX_RECONNECT_ATTEMPTS).
 *
 * Returns:
 *   events: array of agent event objects
 *   isConnected: boolean
 *   clearEvents: () => void
 */
export function useAgentStream() {
  const wsRef = useRef(null)
  const reconnectAttempts = useRef(0)
  const reconnectTimer = useRef(null)
  const isUnmounting = useRef(false)

  const { addAgentEvent, setAgentConnected, clearAgentEvents, agent } = useStore()

  const connect = useCallback(() => {
    if (isUnmounting.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const userId = getUserId()
    const wsUrl = `/ws/agent-stream?user_id=${userId}`

    // Use relative URL for same-origin, absolute for cross-origin
    const fullUrl = window.location.protocol === 'https:'
      ? `wss://${window.location.host}${wsUrl}`
      : `ws://${window.location.host}${wsUrl}`

    try {
      const ws = new WebSocket(fullUrl)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectAttempts.current = 0
        setAgentConnected(true)
        console.log('[AgentStream] Connected')
      }

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data)
          // Skip keepalive pings
          if (data.type === 'keepalive' || data.type === 'pong') return
          addAgentEvent({
            ...data,
            timestamp: data.timestamp || new Date().toISOString(),
          })
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = (evt) => {
        setAgentConnected(false)
        console.log('[AgentStream] Disconnected', evt.code)

        if (!isUnmounting.current && reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current++
          reconnectTimer.current = setTimeout(() => {
            console.log(`[AgentStream] Reconnecting (attempt ${reconnectAttempts.current})...`)
            connect()
          }, RECONNECT_DELAY * reconnectAttempts.current)
        }
      }

      ws.onerror = (err) => {
        console.warn('[AgentStream] WebSocket error:', err)
      }
    } catch (err) {
      console.error('[AgentStream] Connection failed:', err)
    }
  }, [addAgentEvent, setAgentConnected])

  useEffect(() => {
    isUnmounting.current = false
    connect()

    return () => {
      isUnmounting.current = true
      clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  return {
    events: agent.events,
    isConnected: agent.isConnected,
    clearEvents: clearAgentEvents,
  }
}
