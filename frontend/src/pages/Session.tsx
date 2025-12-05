import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSession,
  extractStyle,
  runIterationStep,
  submitFeedback,
  applyProfileUpdate,
} from '../api/client'
import { StyleProfile, IterationStepResult } from '../types'
import SideBySide from '../components/SideBySide'
import StyleProfileView from '../components/StyleProfileView'
import FeedbackPanel from '../components/FeedbackPanel'
import ProgressIndicator from '../components/ProgressIndicator'

function Session() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const queryClient = useQueryClient()

  const [subject, setSubject] = useState('')
  const [creativityLevel, setCreativityLevel] = useState(50)
  const [currentIteration, setCurrentIteration] = useState<number | null>(null)
  const [latestResult, setLatestResult] = useState<IterationStepResult | null>(null)
  const [activeStep, setActiveStep] = useState<string | null>(null)

  const { data: session, isLoading } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: activeStep ? 2000 : false,
  })

  // Reset current iteration when session loads
  useEffect(() => {
    if (session?.iterations.length) {
      setCurrentIteration(session.iterations.length)
    }
  }, [session?.iterations.length])

  const extractMutation = useMutation({
    mutationFn: () => extractStyle(sessionId!),
    onMutate: () => setActiveStep('extracting'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
      setActiveStep(null)
    },
    onError: () => setActiveStep(null),
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
        <div className="flex items-center gap-2">
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

      {/* Progress Indicator */}
      {activeStep && <ProgressIndicator step={activeStep} />}

      {/* Main Content */}
      <div className="grid grid-cols-12 gap-6">
        {/* Left Sidebar - Iteration History */}
        <div className="col-span-2">
          <h3 className="text-sm font-medium text-slate-700 mb-3">Iterations</h3>
          <div className="space-y-2">
            {session.iterations.map((it) => (
              <button
                key={it.id}
                onClick={() => setCurrentIteration(it.iteration_num)}
                className={`w-full aspect-square rounded-lg overflow-hidden border-2 transition-colors ${
                  currentIteration === it.iteration_num
                    ? 'border-blue-500'
                    : 'border-transparent hover:border-slate-300'
                }`}
              >
                {it.image_b64 ? (
                  <img
                    src={it.image_b64}
                    alt={`Iteration ${it.iteration_num}`}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full bg-slate-200 flex items-center justify-center text-slate-400 text-xs">
                    #{it.iteration_num}
                  </div>
                )}
              </button>
            ))}
            {session.iterations.length === 0 && (
              <p className="text-xs text-slate-400">No iterations yet</p>
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
              <div className="flex gap-4">
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Enter subject to generate (e.g., a fox in a moonlit forest)"
                  className="flex-1 px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <button
                  onClick={() => iterateMutation.mutate()}
                  disabled={!subject.trim() || iterateMutation.isPending}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {iterateMutation.isPending ? 'Generating...' : 'Generate'}
                </button>
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
          {/* Style Profile */}
          {session.style_profile && (
            <StyleProfileView profile={session.style_profile.profile} />
          )}

          {/* Feedback Panel */}
          {latestResult && (
            <FeedbackPanel
              critique={latestResult.critique}
              onApprove={(notes) => {
                feedbackMutation.mutate({
                  iterationId: latestResult.iteration_id,
                  approved: true,
                  notes,
                })
                applyUpdateMutation.mutate(latestResult.updated_profile)
              }}
              onReject={(notes) => {
                feedbackMutation.mutate({
                  iterationId: latestResult.iteration_id,
                  approved: false,
                  notes,
                })
                setLatestResult(null)
              }}
              isLoading={feedbackMutation.isPending || applyUpdateMutation.isPending}
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
      {(extractMutation.isError || iterateMutation.isError) && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
          {(extractMutation.error as Error)?.message ||
            (iterateMutation.error as Error)?.message}
        </div>
      )}
    </div>
  )
}

export default Session
