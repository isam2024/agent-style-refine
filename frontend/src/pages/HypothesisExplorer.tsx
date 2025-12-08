import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getSession, getHypothesisSet, exploreHypotheses, selectHypothesis, stopHypothesisExploration } from '../api/client'
import { StyleHypothesis, HypothesisExploreResponse, WSMessage } from '../types'
import LogWindow from '../components/LogWindow'

interface ProgressState {
  stage: string
  percent: number
  message: string
}

// Helper function to extract relative path from absolute path
function extractRelativePath(absolutePath: string): string {
  // Path format: /path/to/outputs/{session_id}/hypothesis_tests/{filename}.png
  // We need: {session_id}/hypothesis_tests/{filename}.png
  const parts = absolutePath.split('/')
  const outputsIndex = parts.findIndex(p => p === 'outputs')
  if (outputsIndex >= 0 && outputsIndex < parts.length - 1) {
    return parts.slice(outputsIndex + 1).join('/')
  }
  // Fallback: return as-is and log
  console.warn('Could not extract relative path from:', absolutePath)
  return absolutePath
}

function HypothesisExplorer() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [exploreResult, setExploreResult] = useState<HypothesisExploreResponse | null>(null)
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null)
  const [expandedHypothesis, setExpandedHypothesis] = useState<string | null>(null)
  const [messages, setMessages] = useState<WSMessage[]>([])
  const [progress, setProgress] = useState<ProgressState | null>(null)
  const [isExploring, setIsExploring] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // Progressive results during exploration
  const [liveHypotheses, setLiveHypotheses] = useState<any[]>([])
  const [liveTestResults, setLiveTestResults] = useState<{[hypothesisId: string]: any[]}>({})
  const [currentTestingHypothesis, setCurrentTestingHypothesis] = useState<string | null>(null)

  // WebSocket connection
  useEffect(() => {
    if (!sessionId || !isExploring) {
      console.log('[HypothesisExplorer] WebSocket NOT connecting:', { sessionId, isExploring })
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/${sessionId}`
    console.log('[HypothesisExplorer] Connecting WebSocket to:', wsUrl)

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('[HypothesisExplorer] ✅ WebSocket connected to:', wsUrl)
    }

    ws.onmessage = (event) => {
      console.log('[HypothesisExplorer] 📨 Received message:', event.data)
      try {
        const data = JSON.parse(event.data) as WSMessage
        console.log('[HypothesisExplorer] 📦 Parsed message:', data)
        setMessages(prev => [...prev, data])

        if (data.event === 'progress' && data.data) {
          setProgress({
            stage: (data.data as any).stage || '',
            percent: (data.data as any).percent || 0,
            message: (data.data as any).message || '',
          })
        }

        // Handle progressive hypothesis results
        if (data.event === 'hypotheses_extracted' && data.data) {
          console.log('[HypothesisExplorer] 📋 Hypotheses extracted:', data.data)
          setLiveHypotheses((data.data as any).hypotheses || [])
        }

        if (data.event === 'hypothesis_testing_start' && data.data) {
          console.log('[HypothesisExplorer] 🧪 Testing hypothesis:', data.data)
          setCurrentTestingHypothesis((data.data as any).hypothesis_id)
        }

        if (data.event === 'hypothesis_test_result' && data.data) {
          console.log('[HypothesisExplorer] 🖼️ Test result:', data.data)
          const { hypothesis_id, test_result } = data.data as any
          setLiveTestResults(prev => ({
            ...prev,
            [hypothesis_id]: [...(prev[hypothesis_id] || []), test_result]
          }))
        }

        if (data.event === 'hypothesis_testing_complete' && data.data) {
          console.log('[HypothesisExplorer] ✅ Hypothesis testing complete:', data.data)
          setCurrentTestingHypothesis(null)
        }
      } catch (e) {
        console.error('[HypothesisExplorer] ❌ Failed to parse WebSocket message:', e)
      }
    }

    ws.onerror = (error) => {
      console.error('[HypothesisExplorer] ❌ WebSocket error:', error)
    }

    ws.onclose = () => {
      console.log('[HypothesisExplorer] 🔌 WebSocket disconnected from:', wsUrl)
    }

    wsRef.current = ws

    return () => {
      console.log('[HypothesisExplorer] 🧹 Cleanup: closing WebSocket')
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  }, [sessionId, isExploring])

  const exploreMutation = useMutation({
    mutationFn: () => {
      console.log('[HypothesisExplorer] 🚀 exploreMutation.mutate() called!', new Error().stack)
      setIsExploring(true)
      return exploreHypotheses(sessionId!, 3)
    },
    onSuccess: (result) => {
      console.log('[HypothesisExplorer] ✅ Exploration completed successfully')
      setExploreResult(result)
      setIsExploring(false)
      if (result.selected_hypothesis) {
        setSelectedHypothesisId(result.selected_hypothesis.id)
      }
    },
    onError: () => {
      console.log('[HypothesisExplorer] ❌ Exploration failed')
      setIsExploring(false)
    },
  })

  const selectMutation = useMutation({
    mutationFn: (hypothesisId: string) => {
      console.log('[HypothesisExplorer] 🎯 Selecting hypothesis:', hypothesisId)
      return selectHypothesis(sessionId!, hypothesisId)
    },
    onSuccess: () => {
      console.log('[HypothesisExplorer] ✅ Selection successful - NOT navigating')
      // Refresh the hypothesis set to show selection
      queryClient.invalidateQueries({ queryKey: ['hypothesisSet', sessionId] })
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
      // Don't auto-navigate - let user review selection and manually go to training
    },
  })

  // Query to load existing hypothesis results (for sessions that already explored)
  const { data: session, isLoading: sessionLoading } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: !!sessionId,
  })

  // Query to load existing hypothesis set if session has completed exploration
  // Load if status is 'hypothesis_ready' (exploration done, not selected yet)
  // OR 'ready' (hypothesis was already selected)
  const { data: existingHypothesisSet, isLoading: hypothesisSetLoading } = useQuery({
    queryKey: ['hypothesisSet', sessionId],
    queryFn: () => getHypothesisSet(sessionId!),
    enabled: !!sessionId && (session?.status === 'hypothesis_ready' || session?.status === 'ready'),
  })

  // Load existing results if available
  useEffect(() => {
    console.log('[HypothesisExplorer] 📊 Load check:', {
      hasExistingSet: !!existingHypothesisSet,
      hasExploreResult: !!exploreResult,
      sessionId
    })
    if (existingHypothesisSet && !exploreResult) {
      console.log('[HypothesisExplorer] 📦 Loading existing hypothesis results')
      setExploreResult({
        session_id: sessionId!,
        hypotheses: existingHypothesisSet.hypotheses,
        selected_hypothesis: existingHypothesisSet.hypotheses.find((h: StyleHypothesis) => h.id === existingHypothesisSet.selected_hypothesis_id) || null,
        auto_selected: false,
        test_images_generated: existingHypothesisSet.hypotheses.reduce((sum: number, h: StyleHypothesis) => sum + h.test_results.length, 0),
      })
    }
  }, [existingHypothesisSet, sessionId, exploreResult])

  // Auto-start exploration when page loads (DISABLED - manual start only)
  // This is disabled because we load existing results automatically
  // To enable auto-start for new sessions, uncomment the code below
  /*
  useEffect(() => {
    // Only start once per page load, and only if no existing results
    if (
      sessionId &&
      !sessionLoading &&
      !exploreResult &&
      !exploreMutation.isPending &&
      !isExploring &&
      !explorationStartedRef.current &&
      session?.status !== 'hypothesis_ready' &&
      !existingHypothesisSet &&
      !hypothesisSetLoading
    ) {
      console.log('[HypothesisExplorer] 🚀 Starting exploration (first time only)')
      explorationStartedRef.current = true
      exploreMutation.mutate()
    }
  }, [sessionId, session, sessionLoading, existingHypothesisSet, hypothesisSetLoading])
  */

  const handleSelect = () => {
    if (selectedHypothesisId) {
      selectMutation.mutate(selectedHypothesisId)
    }
  }

  const handleStopExploration = async () => {
    if (!sessionId) return

    try {
      // Call backend to cancel operations
      await stopHypothesisExploration(sessionId)
      console.log('[HypothesisExplorer] 🛑 Stop request sent to backend')

      // Update UI state
      setIsExploring(false)

      // WebSocket will close automatically in cleanup
    } catch (error) {
      console.error('[HypothesisExplorer] Failed to stop exploration:', error)
      // Still update UI state even if API call fails
      setIsExploring(false)
    }
  }

  const handleStartExploration = () => {
    console.log('[HypothesisExplorer] 🔄 handleStartExploration called', { isExploring, isPending: exploreMutation.isPending })
    if (!isExploring && !exploreMutation.isPending) {
      console.log('[HypothesisExplorer] ✅ Starting exploration via handleStartExploration')
      exploreMutation.mutate()
    }
  }

  if (exploreMutation.isPending || isExploring) {
    return (
      <>
        <LogWindow
          sessionId={sessionId!}
          isActive={true}
          onComplete={() => {
            setIsExploring(false)
          }}
        />

        <div className="max-w-6xl mx-auto space-y-6">
          {/* Progress Bar with Stop Button */}
          {progress && (
            <div className="bg-white rounded-lg shadow-sm p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-slate-700">{progress.message}</span>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-slate-500">{progress.percent}%</span>
                  <button
                    onClick={handleStopExploration}
                    className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
                  >
                    Stop
                  </button>
                </div>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress.percent}%` }}
                />
              </div>
            </div>
          )}

          {/* Live Hypotheses Display */}
          {liveHypotheses.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-slate-800">
                Testing {liveHypotheses.length} Hypotheses
              </h3>

              <div className="grid grid-cols-1 gap-4">
                {liveHypotheses.map((hyp: any, idx: number) => {
                  const testResults = liveTestResults[hyp.id] || []
                  const isTesting = currentTestingHypothesis === hyp.id

                  return (
                    <div
                      key={hyp.id}
                      className={`bg-white rounded-lg shadow-sm border-2 transition-all ${
                        isTesting ? 'border-blue-500 ring-2 ring-blue-200' : 'border-slate-200'
                      }`}
                    >
                      <div className="p-4">
                        <div className="flex items-start justify-between mb-3">
                          <div>
                            <h4 className="font-semibold text-slate-800 flex items-center gap-2">
                              <span className="text-slate-400">#{idx + 1}</span>
                              {hyp.interpretation}
                              {isTesting && (
                                <span className="animate-pulse text-blue-600 text-sm">Testing...</span>
                              )}
                            </h4>
                          </div>
                          <span className="text-xs bg-slate-100 px-2 py-1 rounded">
                            {testResults.length} / 3 tests
                          </span>
                        </div>

                        {/* Test Images Grid */}
                        {testResults.length > 0 && (
                          <div className="grid grid-cols-3 gap-3 mt-3">
                            {testResults.map((test: any, testIdx: number) => (
                              <div key={testIdx} className="relative group">
                                <div className="aspect-square bg-slate-100 rounded overflow-hidden">
                                  <img
                                    src={`/api/files/${extractRelativePath(test.generated_image_path)}`}
                                    alt={test.test_subject}
                                    className="w-full h-full object-cover"
                                    onError={(e) => {
                                      e.currentTarget.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect fill="%23ddd" width="100" height="100"/%3E%3C/svg%3E'
                                    }}
                                  />
                                  {/* Score Badge */}
                                  <div className="absolute top-1 right-1 bg-black/70 text-white text-xs font-bold px-2 py-0.5 rounded">
                                    {Math.round((test.scores.visual_consistency + test.scores.subject_independence) / 2)}%
                                  </div>
                                </div>
                                <div className="text-xs text-slate-600 mt-1 text-center">
                                  {test.test_subject}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </>
    )
  }

  if (exploreMutation.isError) {
    return (
      <>
        <LogWindow
          sessionId={sessionId!}
          isActive={true}
          onComplete={() => {
            setIsExploring(false)
          }}
        />

        <div className="max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-red-900 mb-2">Exploration Failed</h2>
          <p className="text-red-700">{(exploreMutation.error as Error).message}</p>
          <button
            onClick={() => {
              console.log('[HypothesisExplorer] 🔄 Retry button clicked')
              exploreMutation.mutate()
            }}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Retry
          </button>
        </div>
        </div>
      </>
    )
  }

  if (!exploreResult) {
    // If session is hypothesis_ready, we should have loaded existingHypothesisSet by now
    // Only show start button for truly new sessions (not hypothesis_ready)
    if (session && session.status !== 'hypothesis_ready' && !sessionLoading && !hypothesisSetLoading && !existingHypothesisSet) {
      console.log('[HypothesisExplorer] 🎬 Showing start button for new session')
      return (
        <>
          <LogWindow
            sessionId={sessionId!}
            isActive={true}
            onComplete={() => {
              setIsExploring(false)
            }}
          />

          <div className="max-w-4xl mx-auto">
            <div className="bg-white rounded-xl shadow-sm p-8 text-center">
              <h2 className="text-2xl font-bold text-slate-800 mb-4">Ready to Explore Hypotheses</h2>
              <p className="text-slate-600 mb-6">
                Generate multiple style interpretations and test each one to find the best match.
              </p>
              <button
                onClick={() => {
                  console.log('[HypothesisExplorer] 👆 Start button clicked')
                  exploreMutation.mutate()
                }}
                disabled={exploreMutation.isPending || isExploring}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {exploreMutation.isPending || isExploring ? 'Exploring...' : 'Start Exploration'}
              </button>
            </div>
          </div>
        </>
      )
    }

    return (
      <>
        <LogWindow
          sessionId={sessionId!}
          isActive={true}
          onComplete={() => {
            setIsExploring(false)
          }}
        />

        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-xl shadow-sm p-8 text-center text-slate-500">
            Loading existing results...
          </div>
        </div>
      </>
    )
  }

  const sortedHypotheses = [...exploreResult.hypotheses].sort((a, b) => b.confidence - a.confidence)

  return (
    <div className="space-y-6">
      <LogWindow
        sessionId={sessionId!}
        isActive={true}
        onComplete={() => {
          setIsExploring(false)
        }}
      />

      <div className="max-w-6xl mx-auto space-y-6">
        {/* Debug Controls */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-yellow-800">Debug Controls</span>
              <span className="text-xs text-yellow-600">
                Session: {sessionId?.slice(0, 8)}... | Messages: {messages.length}
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleStartExploration}
                disabled={isExploring || exploreMutation.isPending}
                className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Re-run Exploration
              </button>
              <button
                onClick={() => {
                  setExploreResult(null)
                  setMessages([])
                  setProgress(null)
                }}
                className="px-3 py-1 text-sm bg-slate-600 text-white rounded hover:bg-slate-700"
              >
                Reset View
              </button>
            </div>
          </div>
        </div>

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
            {existingHypothesisSet?.selected_hypothesis_id ? (
              <span className="text-green-600 font-medium">
                ✓ Hypothesis confirmed: {sortedHypotheses.find(h => h.id === existingHypothesisSet.selected_hypothesis_id)?.interpretation}
              </span>
            ) : selectedHypothesisId ? (
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
              {existingHypothesisSet?.selected_hypothesis_id ? 'Back to Home' : 'Cancel'}
            </button>
            {existingHypothesisSet?.selected_hypothesis_id ? (
              <button
                onClick={() => navigate(`/session/${sessionId}`)}
                className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
              >
                Continue to Training →
              </button>
            ) : (
              <button
                onClick={handleSelect}
                disabled={!selectedHypothesisId || selectMutation.isPending}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {selectMutation.isPending ? 'Confirming...' : 'Confirm Selection'}
              </button>
            )}
          </div>
        </div>
      </div>
      </div>
    </div>
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
              <div className="flex-1 flex items-center gap-2">
                <h3 className="text-lg font-semibold text-slate-800">{hypothesis.interpretation}</h3>
                {hypothesis.confidence_tier && (
                  <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${
                    hypothesis.confidence_tier === 'best_match'
                      ? 'bg-green-100 text-green-700'
                      : hypothesis.confidence_tier === 'plausible_alternative'
                      ? 'bg-yellow-100 text-yellow-700'
                      : 'bg-orange-100 text-orange-700'
                  }`}>
                    {hypothesis.confidence_tier === 'best_match'
                      ? 'Best Match'
                      : hypothesis.confidence_tier === 'plausible_alternative'
                      ? 'Plausible'
                      : 'Edge Case'}
                  </span>
                )}
              </div>
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
              <h4 className="font-medium text-slate-800 mb-2">Test Results ({hypothesis.test_results.length} images)</h4>
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                {hypothesis.test_results.map((test, idx) => (
                  <div key={idx} className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                    {/* Test Image */}
                    <div className="aspect-square bg-slate-100 relative group">
                      <img
                        src={`/api/files/${extractRelativePath(test.generated_image_path)}`}
                        alt={test.test_subject}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          console.error('Failed to load image:', test.generated_image_path)
                          // If image fails to load, show placeholder
                          e.currentTarget.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect fill="%23ddd" width="100" height="100"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999"%3ENo Image%3C/text%3E%3C/svg%3E'
                        }}
                      />
                      {/* Overall Score Badge */}
                      <div className="absolute top-2 right-2 bg-black/70 text-white text-xs font-bold px-2 py-1 rounded">
                        {Math.round((test.scores.visual_consistency + test.scores.subject_independence) / 2)}%
                      </div>
                    </div>
                    {/* Test Info */}
                    <div className="p-3">
                      <div className="text-xs font-medium text-slate-700 mb-2">{test.test_subject}</div>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-slate-500">Consistency:</span>
                          <span className={`font-medium ${
                            test.scores.visual_consistency >= 70 ? 'text-green-600' :
                            test.scores.visual_consistency >= 50 ? 'text-yellow-600' : 'text-red-600'
                          }`}>
                            {Math.round(test.scores.visual_consistency)}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Independence:</span>
                          <span className={`font-medium ${
                            test.scores.subject_independence >= 70 ? 'text-green-600' :
                            test.scores.subject_independence >= 50 ? 'text-yellow-600' : 'text-red-600'
                          }`}>
                            {Math.round(test.scores.subject_independence)}%
                          </span>
                        </div>
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
