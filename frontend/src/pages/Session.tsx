import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSession,
  extractStyle,
  reextractStyle,
  runIterationStep,
  submitFeedback,
  applyProfileUpdate,
  finalizeStyle,
} from '../api/client'
import { StyleProfile, IterationStepResult } from '../types'
import SideBySide from '../components/SideBySide'
import StyleProfileView from '../components/StyleProfileView'
import FeedbackPanel from '../components/FeedbackPanel'
import LogWindow from '../components/LogWindow'
import TrainingInsights from '../components/TrainingInsights'

function Session() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  // Load persisted subject from localStorage
  const getPersistedSubject = () => {
    if (!sessionId) return ''
    return localStorage.getItem(`session_subject_${sessionId}`) || ''
  }

  const [subject, setSubject] = useState(getPersistedSubject)
  const [creativityLevel, setCreativityLevel] = useState(50)
  const [currentIteration, setCurrentIteration] = useState<number | null>(null)
  const [latestResult, setLatestResult] = useState<IterationStepResult | null>(null)
  const [activeStep, setActiveStep] = useState<string | null>(null)
  const [showFinalizeModal, setShowFinalizeModal] = useState(false)
  const [styleName, setStyleName] = useState('')
  const [styleDescription, setStyleDescription] = useState('')

  const { data: session, isLoading } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: activeStep ? 2000 : false,
  })

  // Persist subject to localStorage whenever it changes
  useEffect(() => {
    if (sessionId && subject) {
      localStorage.setItem(`session_subject_${sessionId}`, subject)
    }
  }, [sessionId, subject])

  // Reset current iteration when session loads
  useEffect(() => {
    if (session?.iterations.length) {
      setCurrentIteration(session.iterations.length)
    }
  }, [session?.iterations.length])

  // Pre-fill subject: use suggested test prompt (only when no iterations yet)
  useEffect(() => {
    if (!subject && session) {
      // Use suggested test prompt for first iteration
      if (session.style_profile?.profile?.suggested_test_prompt) {
        setSubject(session.style_profile.profile.suggested_test_prompt)
      }
    }
  }, [session?.style_profile?.profile?.suggested_test_prompt])

  const extractMutation = useMutation({
    mutationFn: () => extractStyle(sessionId!),
    onMutate: () => setActiveStep('extracting'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
      setActiveStep(null)
    },
    onError: () => setActiveStep(null),
  })

  const reextractMutation = useMutation({
    mutationFn: () => reextractStyle(sessionId!),
    onMutate: () => setActiveStep('extracting'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
      setActiveStep(null)
    },
    onError: () => setActiveStep(null),
  })

  const finalizeMutation = useMutation({
    mutationFn: () =>
      finalizeStyle(sessionId!, styleName, styleDescription || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['styles'] })
      setShowFinalizeModal(false)
      navigate('/styles')
    },
  })

  const iterateMutation = useMutation({
    mutationFn: () =>
      runIterationStep(sessionId!, subject, creativityLevel),
    onMutate: () => setActiveStep('generating'),
    onSuccess: (result) => {
      setLatestResult(result)
      setCurrentIteration(result.iteration_num)
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
      setActiveStep(null)
    },
    onError: () => setActiveStep(null),
  })

  const feedbackMutation = useMutation({
    mutationFn: ({
      iterationId,
      approved,
      notes,
    }: {
      iterationId: string
      approved: boolean
      notes?: string
    }) => submitFeedback(iterationId, approved, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    },
  })

  const applyUpdateMutation = useMutation({
    mutationFn: (profile: StyleProfile) =>
      applyProfileUpdate(sessionId!, profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
      setLatestResult(null)
    },
  })

  // Handle feedback and auto-continue the loop
  const handleApprove = async (notes?: string) => {
    if (!latestResult) return

    // Submit feedback
    await feedbackMutation.mutateAsync({
      iterationId: latestResult.iteration_id,
      approved: true,
      notes,
    })

    // Apply the updated profile
    await applyUpdateMutation.mutateAsync(latestResult.updated_profile)

    // Auto-trigger next iteration
    setLatestResult(null)
    iterateMutation.mutate()
  }

  const handleReject = async (notes?: string) => {
    if (!latestResult) return

    // Submit feedback (don't apply profile update)
    await feedbackMutation.mutateAsync({
      iterationId: latestResult.iteration_id,
      approved: false,
      notes,
    })

    // Auto-trigger next iteration with same subject
    setLatestResult(null)
    iterateMutation.mutate()
  }

  if (isLoading) {
    return <div className="text-center py-12 text-slate-500">Loading session...</div>
  }

  if (!session) {
    return <div className="text-center py-12 text-red-500">Session not found</div>
  }

  const hasStyleProfile = !!session.style_profile
  const selectedIteration =
    currentIteration !== null
      ? session.iterations.find((i) => i.iteration_num === currentIteration)
      : session.iterations[session.iterations.length - 1]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">{session.name}</h2>
          <p className="text-slate-500 mt-1">
            {hasStyleProfile
              ? `Style Profile v${session.style_profile?.version} • ${session.iterations.length} iterations`
              : 'Style not yet extracted'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {hasStyleProfile && (
            <>
              <button
                onClick={() => reextractMutation.mutate()}
                disabled={reextractMutation.isPending}
                className="px-3 py-1.5 text-sm border border-slate-300 text-slate-600 rounded-lg hover:bg-slate-50 disabled:opacity-50"
              >
                Re-extract
              </button>
              <button
                onClick={() => {
                  setStyleName(session.style_profile?.profile.style_name || session.name)
                  setShowFinalizeModal(true)
                }}
                className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700"
              >
                Finalize Style
              </button>
            </>
          )}
          <span
            className={`px-2 py-1 text-xs rounded-full ${
              session.status === 'ready'
                ? 'bg-green-100 text-green-700'
                : session.status === 'error'
                ? 'bg-red-100 text-red-700'
                : 'bg-yellow-100 text-yellow-700'
            }`}
          >
            {session.status}
          </span>
        </div>
      </div>

      {/* Log Window - shows during any active operation */}
      <LogWindow
        sessionId={sessionId!}
        isActive={!!activeStep}
      />

      {/* Main Content */}
      <div className="grid grid-cols-12 gap-6">
        {/* Left Sidebar - Iteration History (Breadcrumb) */}
        <div className="col-span-2">
          <h3 className="text-sm font-medium text-slate-700 mb-3">
            History ({session.iterations.length})
          </h3>
          <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
            {session.iterations.map((it) => {
              const overallScore = it.scores?.overall ?? null
              const isSelected = currentIteration === it.iteration_num

              return (
                <button
                  key={it.id}
                  onClick={() => setCurrentIteration(it.iteration_num)}
                  className={`w-full text-left rounded-lg overflow-hidden border-2 transition-all ${
                    isSelected
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-slate-200 hover:border-slate-300 bg-white'
                  }`}
                >
                  {/* Thumbnail */}
                  <div className="aspect-square relative">
                    {it.image_b64 ? (
                      <img
                        src={it.image_b64}
                        alt={`Iteration ${it.iteration_num}`}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-slate-100 flex items-center justify-center text-slate-400">
                        <span className="text-lg font-bold">#{it.iteration_num}</span>
                      </div>
                    )}
                    {/* Iteration number badge */}
                    <div className="absolute top-1 left-1 bg-black/60 text-white text-xs px-1.5 py-0.5 rounded">
                      #{it.iteration_num}
                    </div>
                    {/* Score badge */}
                    {overallScore !== null && (
                      <div
                        className={`absolute top-1 right-1 text-xs px-1.5 py-0.5 rounded font-medium ${
                          overallScore >= 80
                            ? 'bg-green-500 text-white'
                            : overallScore >= 60
                            ? 'bg-yellow-500 text-white'
                            : 'bg-red-500 text-white'
                        }`}
                      >
                        {overallScore}%
                      </div>
                    )}
                    {/* Approval indicator */}
                    {it.approved !== null && (
                      <div
                        className={`absolute bottom-1 right-1 w-4 h-4 rounded-full flex items-center justify-center text-white text-xs ${
                          it.approved ? 'bg-green-500' : 'bg-red-500'
                        }`}
                      >
                        {it.approved ? '✓' : '✗'}
                      </div>
                    )}
                  </div>
                  {/* Metadata */}
                  <div className="p-2 border-t border-slate-100">
                    {it.prompt_used && (
                      <p className="text-xs text-slate-500 line-clamp-2" title={it.prompt_used}>
                        {it.prompt_used.slice(0, 60)}...
                      </p>
                    )}
                    {it.feedback && (
                      <p className="text-xs text-blue-600 mt-1 italic line-clamp-1">
                        "{it.feedback}"
                      </p>
                    )}
                  </div>
                </button>
              )
            })}
            {session.iterations.length === 0 && (
              <div className="text-center py-8 text-slate-400">
                <p className="text-sm">No iterations yet</p>
                <p className="text-xs mt-1">Generate an image to start</p>
              </div>
            )}
          </div>
        </div>

        {/* Center - Side by Side Comparison */}
        <div className="col-span-6">
          {!hasStyleProfile ? (
            <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
              {session.original_image_b64 ? (
                <>
                  <img
                    src={session.original_image_b64}
                    alt="Original"
                    className="max-h-64 mx-auto rounded-lg mb-4"
                  />
                  <p className="text-slate-600 mb-4">
                    Extract the visual style from this image to begin
                  </p>
                  <button
                    onClick={() => extractMutation.mutate()}
                    disabled={extractMutation.isPending}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                  >
                    {extractMutation.isPending ? 'Extracting...' : 'Extract Style'}
                  </button>
                </>
              ) : (
                <p className="text-slate-500">No original image found</p>
              )}
            </div>
          ) : (
            <SideBySide
              originalImage={session.original_image_b64}
              generatedImage={selectedIteration?.image_b64 || null}
              iterationNum={selectedIteration?.iteration_num}
            />
          )}

          {/* Generation Controls */}
          {hasStyleProfile && (
            <div className="mt-4 bg-white rounded-xl border border-slate-200 p-4">
              <div className="space-y-3">
                <div className="relative">
                  <textarea
                    value={subject}
                    onChange={(e) => {
                      setSubject(e.target.value)
                      // Auto-expand textarea
                      e.target.style.height = 'auto'
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
                    }}
                    onFocus={(e) => {
                      // Ensure proper height on focus
                      e.target.style.height = 'auto'
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
                    }}
                    placeholder="Enter subject to generate (e.g., a fox in a moonlit forest, a cozy cabin in snowy mountains at dusk)"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none overflow-hidden min-h-[60px]"
                    rows={2}
                  />
                  <span className="absolute bottom-2 right-2 text-xs text-slate-400">
                    {subject.length} chars
                  </span>
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={() => iterateMutation.mutate()}
                    disabled={!subject.trim() || iterateMutation.isPending}
                    className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                  >
                    {iterateMutation.isPending ? 'Generating...' : 'Generate Image'}
                  </button>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-4">
                <label className="text-sm text-slate-600">Creativity:</label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={creativityLevel}
                  onChange={(e) => setCreativityLevel(Number(e.target.value))}
                  className="flex-1"
                />
                <span className="text-sm text-slate-500 w-8">{creativityLevel}</span>
              </div>
            </div>
          )}
        </div>

        {/* Right Sidebar - Style Profile & Feedback */}
        <div className="col-span-4 space-y-4">
          {/* Training Insights */}
          {session.iterations.length > 0 && (
            <TrainingInsights iterations={session.iterations} />
          )}

          {/* Style Profile */}
          {session.style_profile && (
            <StyleProfileView profile={session.style_profile.profile} />
          )}

          {/* Feedback Panel */}
          {latestResult && (
            <FeedbackPanel
              critique={latestResult.critique}
              onApprove={handleApprove}
              onReject={handleReject}
              isLoading={feedbackMutation.isPending || applyUpdateMutation.isPending || iterateMutation.isPending}
            />
          )}

          {/* Iteration Details */}
          {selectedIteration && !latestResult && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-medium text-slate-700 mb-3">
                Iteration #{selectedIteration.iteration_num}
              </h3>
              {selectedIteration.scores && (
                <div className="space-y-2 mb-4">
                  <p className="text-xs text-slate-500 uppercase">Match Scores</p>
                  {Object.entries(selectedIteration.scores).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-2">
                      <span className="text-xs text-slate-600 capitalize w-24">
                        {key.replace('_', ' ')}
                      </span>
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full"
                          style={{ width: `${value}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-500 w-8">{value}</span>
                    </div>
                  ))}
                </div>
              )}
              {selectedIteration.prompt_used && (
                <div>
                  <p className="text-xs text-slate-500 uppercase mb-1">Prompt Used</p>
                  <p className="text-xs text-slate-600 bg-slate-50 p-2 rounded">
                    {selectedIteration.prompt_used}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Error Display */}
      {(extractMutation.isError || iterateMutation.isError || reextractMutation.isError || finalizeMutation.isError) && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
          {(extractMutation.error as Error)?.message ||
            (iterateMutation.error as Error)?.message ||
            (reextractMutation.error as Error)?.message ||
            (finalizeMutation.error as Error)?.message}
        </div>
      )}

      {/* Finalize Style Modal */}
      {showFinalizeModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">
              Finalize Style
            </h3>
            <p className="text-sm text-slate-500 mb-4">
              Save this trained style to your library for use in prompt writing.
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Style Name
                </label>
                <input
                  type="text"
                  value={styleName}
                  onChange={(e) => setStyleName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-purple-500"
                  placeholder="e.g., Moody Watercolor"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Description (optional)
                </label>
                <textarea
                  value={styleDescription}
                  onChange={(e) => setStyleDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-purple-500 resize-none h-20"
                  placeholder="Describe when to use this style..."
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowFinalizeModal(false)}
                className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => finalizeMutation.mutate()}
                disabled={!styleName.trim() || finalizeMutation.isPending}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {finalizeMutation.isPending ? 'Saving...' : 'Save to Library'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Session
