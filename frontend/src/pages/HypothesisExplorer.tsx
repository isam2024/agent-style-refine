import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { exploreHypotheses, selectHypothesis } from '../api/client'
import { StyleHypothesis, HypothesisExploreResponse, WSMessage } from '../types'
import LogWindow from '../components/LogWindow'

interface ProgressState {
  stage: string
  percent: number
  message: string
}

function HypothesisExplorer() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [exploreResult, setExploreResult] = useState<HypothesisExploreResponse | null>(null)
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null)
  const [expandedHypothesis, setExpandedHypothesis] = useState<string | null>(null)
  const [messages, setMessages] = useState<WSMessage[]>([])
  const [progress, setProgress] = useState<ProgressState | null>(null)
  const [isExploring, setIsExploring] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // WebSocket connection
  useEffect(() => {
    if (!sessionId || !isExploring) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${protocol}//${host}/ws/${sessionId}`)

    ws.onopen = () => {
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSMessage
        setMessages(prev => [...prev, data])

        if (data.event === 'progress' && data.data) {
          setProgress({
            stage: (data.data as any).stage || '',
            percent: (data.data as any).percent || 0,
            message: (data.data as any).message || '',
          })
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
    }

    wsRef.current = ws

    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  }, [sessionId, isExploring])

  const exploreMutation = useMutation({
    mutationFn: () => {
      setIsExploring(true)
      return exploreHypotheses(sessionId!, 3)
    },
    onSuccess: (result) => {
      setExploreResult(result)
      setIsExploring(false)
      if (result.selected_hypothesis) {
        setSelectedHypothesisId(result.selected_hypothesis.id)
      }
    },
    onError: () => {
      setIsExploring(false)
    },
  })

  const selectMutation = useMutation({
    mutationFn: (hypothesisId: string) => selectHypothesis(sessionId!, hypothesisId),
    onSuccess: () => {
      // Navigate to training session after selection
      navigate(`/session/${sessionId}`)
    },
  })

  // Auto-start exploration when page loads
  useEffect(() => {
    if (sessionId && !exploreResult && !exploreMutation.isPending) {
      exploreMutation.mutate()
    }
  }, [sessionId])

  const handleSelect = () => {
    if (selectedHypothesisId) {
      selectMutation.mutate(selectedHypothesisId)
    }
  }

  const getLatestLog = () => {
    const logMessages = messages.filter(m => m.event === 'log')
    if (logMessages.length === 0) return null
    const latest = logMessages[logMessages.length - 1]
    return latest.data as { message: string; level: string; source: string }
  }

  const latestLog = getLatestLog()

  if (exploreMutation.isPending) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="bg-white rounded-xl shadow-sm p-8">
          <div className="text-center space-y-4">
            <div className="inline-block">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
            <h2 className="text-xl font-semibold text-slate-800">Exploring Hypotheses...</h2>

            {progress && (
              <div className="space-y-2">
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${progress.percent}%` }}
                  />
                </div>
                <p className="text-sm text-slate-600">{progress.message}</p>
              </div>
            )}

            {latestLog && (
              <div className="text-sm text-slate-500 max-w-md mx-auto">
                <p className="font-mono text-xs bg-slate-50 p-3 rounded border border-slate-200">
                  {latestLog.message}
                </p>
              </div>
            )}

            <p className="text-slate-500 text-sm">
              Generating multiple style interpretations and testing each one.
              <br />
              This may take several minutes...
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (exploreMutation.isError) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-red-900 mb-2">Exploration Failed</h2>
          <p className="text-red-700">{(exploreMutation.error as Error).message}</p>
          <button
            onClick={() => exploreMutation.mutate()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!exploreResult) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-xl shadow-sm p-8 text-center text-slate-500">
          Loading...
        </div>
      </div>
    )
  }

  const sortedHypotheses = [...exploreResult.hypotheses].sort((a, b) => b.confidence - a.confidence)

  return (
    <>
      <LogWindow
        sessionId={sessionId!}
        isActive={isExploring}
        onComplete={() => {
          setIsExploring(false)
        }}
      />

      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-2xl font-bold text-slate-800 mb-2">Hypothesis Exploration Complete</h2>
        <p className="text-slate-600">
          {exploreResult.hypotheses.length} interpretations generated and tested with{' '}
          {exploreResult.test_images_generated} test images
        </p>
        {exploreResult.auto_selected && exploreResult.selected_hypothesis && (
          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-900">
              ✓ Auto-selected: <span className="font-medium">{exploreResult.selected_hypothesis.interpretation}</span>
            </p>
          </div>
        )}
      </div>

      {/* Hypotheses Grid */}
      <div className="grid grid-cols-1 gap-4">
        {sortedHypotheses.map((hypothesis, index) => (
          <HypothesisCard
            key={hypothesis.id}
            hypothesis={hypothesis}
            rank={index + 1}
            isSelected={selectedHypothesisId === hypothesis.id}
            isExpanded={expandedHypothesis === hypothesis.id}
            onSelect={() => setSelectedHypothesisId(hypothesis.id)}
            onToggleExpand={() => setExpandedHypothesis(
              expandedHypothesis === hypothesis.id ? null : hypothesis.id
            )}
          />
        ))}
      </div>

      {/* Selection Actions */}
      <div className="bg-white rounded-xl shadow-sm p-6 sticky bottom-0">
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-600">
            {selectedHypothesisId ? (
              <span>Selected: <span className="font-medium">
                {sortedHypotheses.find(h => h.id === selectedHypothesisId)?.interpretation}
              </span></span>
            ) : (
              <span>Select a hypothesis to continue</span>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => navigate('/')}
              className="px-4 py-2 text-slate-600 hover:text-slate-800"
            >
              Cancel
            </button>
            <button
              onClick={handleSelect}
              disabled={!selectedHypothesisId || selectMutation.isPending}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {selectMutation.isPending ? 'Confirming...' : 'Confirm Selection'}
            </button>
          </div>
        </div>
      </div>
      </div>
    </>
  )
}

interface HypothesisCardProps {
  hypothesis: StyleHypothesis
  rank: number
  isSelected: boolean
  isExpanded: boolean
  onSelect: () => void
  onToggleExpand: () => void
}

function HypothesisCard({ hypothesis, rank, isSelected, isExpanded, onSelect, onToggleExpand }: HypothesisCardProps) {
  const confidencePercent = Math.round(hypothesis.confidence * 100)
  const avgConsistency = hypothesis.test_results.length > 0
    ? Math.round(
        hypothesis.test_results.reduce((sum, t) => sum + t.scores.visual_consistency, 0) /
        hypothesis.test_results.length
      )
    : 0
  const avgIndependence = hypothesis.test_results.length > 0
    ? Math.round(
        hypothesis.test_results.reduce((sum, t) => sum + t.scores.subject_independence, 0) /
        hypothesis.test_results.length
      )
    : 0

  return (
    <div
      className={`bg-white rounded-xl shadow-sm border-2 transition-all ${
        isSelected ? 'border-blue-500 ring-2 ring-blue-200' : 'border-slate-200'
      }`}
    >
      <div
        className="p-6 cursor-pointer"
        onClick={onSelect}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-100 text-slate-700 font-semibold text-sm">
                #{rank}
              </div>
              <h3 className="text-lg font-semibold text-slate-800">{hypothesis.interpretation}</h3>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Confidence:</span>
                <span className="font-medium text-slate-900">{confidencePercent}%</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Consistency:</span>
                <span className="font-medium text-slate-900">{avgConsistency}%</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Independence:</span>
                <span className="font-medium text-slate-900">{avgIndependence}%</span>
              </div>
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onToggleExpand()
            }}
            className="px-3 py-1 text-sm text-slate-600 hover:text-slate-800 hover:bg-slate-50 rounded"
          >
            {isExpanded ? 'Hide Details' : 'Show Details'}
          </button>
        </div>

        {/* Confidence Bar */}
        <div className="w-full bg-slate-100 rounded-full h-2 mb-4">
          <div
            className={`h-2 rounded-full transition-all ${
              confidencePercent >= 70 ? 'bg-green-500' : confidencePercent >= 50 ? 'bg-yellow-500' : 'bg-orange-500'
            }`}
            style={{ width: `${confidencePercent}%` }}
          />
        </div>

        {/* Supporting Evidence Preview */}
        {hypothesis.supporting_evidence.length > 0 && !isExpanded && (
          <div className="text-sm text-slate-600">
            <span className="font-medium">Evidence:</span> {hypothesis.supporting_evidence[0]}
            {hypothesis.supporting_evidence.length > 1 && <span className="text-slate-400"> +{hypothesis.supporting_evidence.length - 1} more</span>}
          </div>
        )}
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="border-t border-slate-200 p-6 space-y-4 bg-slate-50">
          {/* Supporting Evidence */}
          <div>
            <h4 className="font-medium text-slate-800 mb-2">Supporting Evidence</h4>
            <ul className="space-y-1">
              {hypothesis.supporting_evidence.map((evidence, idx) => (
                <li key={idx} className="text-sm text-slate-600 flex gap-2">
                  <span className="text-green-600">✓</span>
                  <span>{evidence}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Uncertain Aspects */}
          {hypothesis.uncertain_aspects.length > 0 && (
            <div>
              <h4 className="font-medium text-slate-800 mb-2">Uncertain Aspects</h4>
              <ul className="space-y-1">
                {hypothesis.uncertain_aspects.map((aspect, idx) => (
                  <li key={idx} className="text-sm text-slate-600 flex gap-2">
                    <span className="text-yellow-600">?</span>
                    <span>{aspect}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Test Results */}
          {hypothesis.test_results.length > 0 && (
            <div>
              <h4 className="font-medium text-slate-800 mb-2">Test Results</h4>
              <div className="grid grid-cols-3 gap-3">
                {hypothesis.test_results.map((test, idx) => (
                  <div key={idx} className="bg-white rounded-lg p-3 border border-slate-200">
                    <div className="text-xs font-medium text-slate-700 mb-2">{test.test_subject}</div>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-slate-500">Consistency:</span>
                        <span className="font-medium">{Math.round(test.scores.visual_consistency)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Independence:</span>
                        <span className="font-medium">{Math.round(test.scores.subject_independence)}%</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Core Invariants */}
          <div>
            <h4 className="font-medium text-slate-800 mb-2">Core Style Invariants</h4>
            <ul className="space-y-1">
              {hypothesis.profile.core_invariants.map((invariant, idx) => (
                <li key={idx} className="text-sm text-slate-600 flex gap-2">
                  <span className="text-blue-600">•</span>
                  <span>{invariant}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

export default HypothesisExplorer
