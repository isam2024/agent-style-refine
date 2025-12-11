import { useEffect, useRef, useState } from 'react'

interface LogEntry {
  id: number
  message: string
  level: 'info' | 'success' | 'warning' | 'error'
  step?: string
  timestamp: number
}

interface ProgressState {
  step: string
  progress: number | null
  message: string | null
}

interface LogWindowProps {
  sessionId: string
  isActive: boolean
  onClose?: () => void
  onComplete?: () => void
}

function LogWindow({ sessionId, isActive, onClose, onComplete }: LogWindowProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [progress, setProgress] = useState<ProgressState | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)
  const idCounter = useRef(0)

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // WebSocket connection
  useEffect(() => {
    if (!isActive || !sessionId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${protocol}//${host}/ws/${sessionId}`)

    ws.onopen = () => {
      setConnected(true)
      addLog('Connected to server', 'info')
      // Check if we're reconnecting to an already-running operation
      if (logs.length === 0) {
        addLog('Note: If operation was already running, some previous logs may be missing', 'warning')
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.event === 'log') {
          addLog(data.data.message, data.data.level, data.data.step)
        } else if (data.event === 'progress') {
          setProgress({
            step: data.data.step,
            progress: data.data.progress,
            message: data.data.message,
          })
          if (data.data.message) {
            addLog(data.data.message, 'info', data.data.step)
          }
        } else if (data.event === 'error') {
          addLog(data.data.error, 'error')
          setProgress(null)
        } else if (data.event === 'complete') {
          addLog('Operation completed', 'success')
          setProgress(null)
          // Trigger final data refresh in parent component
          if (onComplete) {
            onComplete()
          }
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onclose = () => {
      setConnected(false)
      addLog('Disconnected from server', 'warning')
    }

    ws.onerror = () => {
      addLog('WebSocket error', 'error')
    }

    wsRef.current = ws

    // Ping to keep connection alive
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      clearInterval(pingInterval)
      ws.close()
    }
  }, [sessionId, isActive])

  const addLog = (message: string, level: LogEntry['level'], step?: string) => {
    setLogs((prev) => [
      ...prev.slice(-100), // Keep last 100 logs
      {
        id: idCounter.current++,
        message,
        level,
        step,
        timestamp: Date.now(),
      },
    ])
  }

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const getLevelColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'success':
        return 'text-green-400'
      case 'warning':
        return 'text-yellow-400'
      case 'error':
        return 'text-red-400'
      default:
        return 'text-slate-300'
    }
  }

  const getLevelIcon = (level: LogEntry['level']) => {
    switch (level) {
      case 'success':
        return '✓'
      case 'warning':
        return '⚠'
      case 'error':
        return '✗'
      default:
        return '•'
    }
  }

  // Show log window if active OR if there are logs to display
  if (!isActive && logs.length === 0) return null

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              connected ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span className="text-sm font-medium text-slate-300">Activity Log</span>
        </div>
        <div className="flex items-center gap-2">
          {progress && (
            <span className="text-xs text-slate-400">
              {progress.step}
              {progress.progress !== null && ` (${progress.progress}%)`}
            </span>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 text-sm"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      {progress && progress.progress !== null && (
        <div className="h-1 bg-slate-800">
          <div
            className="h-full bg-blue-500 transition-all duration-300"
            style={{ width: `${progress.progress}%` }}
          />
        </div>
      )}

      {/* Log Content */}
      <div className="h-48 overflow-y-auto p-2 font-mono text-xs">
        {logs.length === 0 ? (
          <div className="text-slate-500 text-center py-8">
            Waiting for activity...
          </div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="flex gap-2 py-0.5 hover:bg-slate-800/50">
              <span className="text-slate-500 shrink-0">
                {formatTime(log.timestamp)}
              </span>
              <span className={`shrink-0 ${getLevelColor(log.level)}`}>
                {getLevelIcon(log.level)}
              </span>
              {log.step && (
                <span className="text-blue-400 shrink-0">[{log.step}]</span>
              )}
              <span className={getLevelColor(log.level)}>{log.message}</span>
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  )
}

export default LogWindow
