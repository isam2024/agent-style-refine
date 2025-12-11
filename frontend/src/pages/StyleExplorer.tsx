import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getExploration,
  getExplorationTree,
  exploreStep,
  autoExplore,
  batchExplore,
  toggleSnapshotFavorite,
  snapshotToStyle,
  setCurrentSnapshot,
  resetExplorationStatus,
} from '../api/client'
import { ExplorationSnapshot, MutationStrategy, WSMessage } from '../types'
import LogWindow from '../components/LogWindow'
import ExplorationTreeView from '../components/ExplorationTree'
import StrategySelectionModal, { ALL_STRATEGIES, STRATEGY_PRESETS } from '../components/StrategySelectionModal'

// Helper function to extract relative path from absolute path
function extractRelativePath(absolutePath: string): string {
  const parts = absolutePath.split('/')
  const outputsIndex = parts.findIndex(p => p === 'outputs')
  if (outputsIndex >= 0 && outputsIndex < parts.length - 1) {
    return parts.slice(outputsIndex + 1).join('/')
  }
  return absolutePath
}

// Build a lookup map from ALL_STRATEGIES for display
const STRATEGY_LOOKUP = ALL_STRATEGIES.reduce((acc, s) => {
  acc[s.key] = { name: s.name, description: s.description }
  return acc
}, {} as Record<string, { name: string; description: string }>)

// Get display name for a strategy
function getStrategyDisplayName(strategyKey: string): string {
  return STRATEGY_LOOKUP[strategyKey]?.name || strategyKey.replace(/_/g, ' ')
}

function StyleExplorer() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [selectedSnapshot, setSelectedSnapshot] = useState<ExplorationSnapshot | null>(null)
  const [isExploring, setIsExploring] = useState(false)
  const [selectedStrategy, setSelectedStrategy] = useState<MutationStrategy | undefined>(undefined)
  const [autoSteps, setAutoSteps] = useState(5)
  const [exportModalOpen, setExportModalOpen] = useState(false)
  const [exportName, setExportName] = useState('')
  const [showLog, setShowLog] = useState(false)
  const [viewMode, setViewMode] = useState<'gallery' | 'tree'>('gallery')
  const [batchModalOpen, setBatchModalOpen] = useState(false)
  const [batchStrategies, setBatchStrategies] = useState<MutationStrategy[]>(STRATEGY_PRESETS.core.strategies)
  const [batchIterations, setBatchIterations] = useState(1)
  const [showStrategySelectionModal, setShowStrategySelectionModal] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)

  // Fetch exploration session
  const { data: session, isLoading, refetch } = useQuery({
    queryKey: ['exploration', sessionId],
    queryFn: () => getExploration(sessionId!),
    enabled: !!sessionId,
  })

  // Fetch tree data when in tree view
  const { data: treeData } = useQuery({
    queryKey: ['exploration-tree', sessionId],
    queryFn: () => getExplorationTree(sessionId!),
    enabled: !!sessionId && viewMode === 'tree',
  })

  // Restore exploring state if session is actively in progress
  // Note: 'paused' means ready to explore, 'exploring' means actively running
  useEffect(() => {
    if (session?.status === 'exploring') {
      setIsExploring(true)
      setShowLog(true)
    } else if (session?.status === 'paused' || session?.status === 'created') {
      setIsExploring(false)
    }
  }, [session?.status])

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!sessionId || !isExploring) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/${sessionId}`

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('[StyleExplorer] WebSocket connected')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSMessage
        console.log('[StyleExplorer] WS message:', data.event)
      } catch (e) {
        console.error('[StyleExplorer] Failed to parse WS message:', e)
      }
    }

    ws.onclose = () => {
      console.log('[StyleExplorer] WebSocket disconnected')
    }

    wsRef.current = ws

    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  }, [sessionId, isExploring])

  // Single step exploration
  const exploreMutation = useMutation({
    mutationFn: () => {
      setIsExploring(true)
      setShowLog(true)
      return exploreStep(sessionId!, selectedStrategy, selectedSnapshot?.id)
    },
    onSuccess: () => {
      setIsExploring(false)
      // Invalidate and refetch to get fresh data
      queryClient.invalidateQueries({ queryKey: ['exploration', sessionId] })
      queryClient.invalidateQueries({ queryKey: ['exploration-tree', sessionId] })
    },
    onError: () => {
      setIsExploring(false)
    },
  })

  // Auto exploration
  const autoExploreMutation = useMutation({
    mutationFn: () => {
      setIsExploring(true)
      setShowLog(true)
      return autoExplore(sessionId!, autoSteps)
    },
    onSuccess: (result) => {
      setIsExploring(false)
      // Invalidate and refetch to get fresh data
      queryClient.invalidateQueries({ queryKey: ['exploration', sessionId] })
      queryClient.invalidateQueries({ queryKey: ['exploration-tree', sessionId] })
      console.log(`Auto-explore complete: ${result.snapshots_created} snapshots, best score: ${result.best_score}`)
    },
    onError: () => {
      setIsExploring(false)
    },
  })

  // Toggle favorite
  const favoriteMutation = useMutation({
    mutationFn: (snapshotId: string) => toggleSnapshotFavorite(snapshotId),
    onSuccess: () => {
      refetch()
    },
  })

  // Set current snapshot
  const setCurrentMutation = useMutation({
    mutationFn: (snapshotId: string) => setCurrentSnapshot(sessionId!, snapshotId),
    onSuccess: () => {
      refetch()
    },
  })

  // Export to style
  const exportMutation = useMutation({
    mutationFn: () => snapshotToStyle(selectedSnapshot!.id, exportName),
    onSuccess: () => {
      setExportModalOpen(false)
      setExportName('')
      queryClient.invalidateQueries({ queryKey: ['styles'] })
    },
  })

  // Batch explore
  const batchMutation = useMutation({
    mutationFn: () => {
      setIsExploring(true)
      setShowLog(true)
      return batchExplore(sessionId!, batchStrategies, batchIterations, selectedSnapshot?.id)
    },
    onSuccess: (result) => {
      setIsExploring(false)
      setBatchModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['exploration', sessionId] })
      queryClient.invalidateQueries({ queryKey: ['exploration-tree', sessionId] })
      console.log(`Batch explore complete: ${result.successful} successful, ${result.failed} failed`)
    },
    onError: () => {
      setIsExploring(false)
      setBatchModalOpen(false)
    },
  })

  // Reset stuck status
  const resetStatusMutation = useMutation({
    mutationFn: () => resetExplorationStatus(sessionId!),
    onSuccess: () => {
      setIsExploring(false)
      refetch()
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Loading exploration...</div>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
        <h2 className="text-lg font-semibold text-red-900">Exploration not found</h2>
        <button
          onClick={() => navigate('/explore')}
          className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
        >
          Back to Explorations
        </button>
      </div>
    )
  }

  const sortedSnapshots = [...(session.snapshots || [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )

  return (
    <div className="space-y-6">
      {showLog && (
        <LogWindow
          sessionId={sessionId!}
          isActive={isExploring}
          onComplete={() => setIsExploring(false)}
          onClose={() => setShowLog(false)}
        />
      )}

      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">{session.name}</h1>
            <p className="text-slate-600 mt-1">
              {session.total_snapshots} snapshots explored | Max depth: {
                session.snapshots?.length
                  ? Math.max(...session.snapshots.map(s => s.depth))
                  : 0
              }
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/explore')}
              className="px-4 py-2 text-slate-600 hover:text-slate-800"
            >
              Back
            </button>
          </div>
        </div>

        {/* Reference Image */}
        {session.reference_image_b64 && (
          <div className="mt-4 flex items-start gap-4">
            <div className="w-24 h-24 bg-slate-100 rounded-lg overflow-hidden flex-shrink-0">
              <img
                src={`data:image/png;base64,${session.reference_image_b64}`}
                alt="Reference"
                className="w-full h-full object-cover"
              />
            </div>
            <div className="text-sm text-slate-600">
              <div className="font-medium">Reference Style</div>
              <div className="mt-1">{session.base_style_profile?.style_name}</div>
            </div>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Exploration Controls</h2>

        <div className="flex flex-wrap gap-4 items-end">
          {/* Strategy Selection */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Mutation Strategy
            </label>
            <select
              value={selectedStrategy || ''}
              onChange={(e) => setSelectedStrategy(e.target.value as MutationStrategy || undefined)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Random from preferences</option>
              {ALL_STRATEGIES.map((strategy) => (
                <option key={strategy.key} value={strategy.key}>{strategy.name}</option>
              ))}
            </select>
          </div>

          {/* Single Step */}
          <button
            onClick={() => exploreMutation.mutate()}
            disabled={isExploring}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isExploring ? 'Exploring...' : 'Explore Step'}
          </button>

          {/* Auto Explore */}
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={autoSteps}
              onChange={(e) => setAutoSteps(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
              className="w-16 px-2 py-2 border border-slate-300 rounded-lg text-center"
              min={1}
              max={20}
            />
            <button
              onClick={() => autoExploreMutation.mutate()}
              disabled={isExploring}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Auto-Explore
            </button>
          </div>

          {/* Batch Explore */}
          <button
            onClick={() => setBatchModalOpen(true)}
            disabled={isExploring}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Batch Explore
          </button>

          {/* Reset Status - show when stuck */}
          {session.status === 'exploring' && (
            <button
              onClick={() => resetStatusMutation.mutate()}
              disabled={resetStatusMutation.isPending}
              className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50"
              title="Reset session status if stuck"
            >
              {resetStatusMutation.isPending ? 'Resetting...' : 'Reset Status'}
            </button>
          )}
        </div>

        {/* Branch from snapshot */}
        {selectedSnapshot && (
          <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-start justify-between gap-4">
              <div className="text-sm text-blue-800 flex-1">
                <div className="font-medium mb-1">Branching from:</div>
                <div className="text-blue-700">{selectedSnapshot.mutation_description}</div>
              </div>
              <button
                onClick={() => setSelectedSnapshot(null)}
                className="text-blue-600 hover:text-blue-800 text-sm shrink-0"
              >
                Clear
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Snapshots View */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-800">
            {viewMode === 'gallery' ? 'Exploration Gallery' : 'Exploration Tree'} ({sortedSnapshots.length})
          </h2>
          <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
            <button
              onClick={() => setViewMode('gallery')}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                viewMode === 'gallery'
                  ? 'bg-white text-slate-800 shadow-sm'
                  : 'text-slate-600 hover:text-slate-800'
              }`}
            >
              Gallery
            </button>
            <button
              onClick={() => setViewMode('tree')}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                viewMode === 'tree'
                  ? 'bg-white text-slate-800 shadow-sm'
                  : 'text-slate-600 hover:text-slate-800'
              }`}
            >
              Tree
            </button>
          </div>
        </div>

        {sortedSnapshots.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            No snapshots yet. Click "Explore Step" to start exploring!
          </div>
        ) : viewMode === 'gallery' ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {sortedSnapshots.map((snapshot) => (
              <SnapshotCard
                key={snapshot.id}
                snapshot={snapshot}
                isSelected={selectedSnapshot?.id === snapshot.id}
                isCurrent={session.current_snapshot_id === snapshot.id}
                onSelect={() => setSelectedSnapshot(snapshot)}
                onFavorite={() => favoriteMutation.mutate(snapshot.id)}
                onSetCurrent={() => setCurrentMutation.mutate(snapshot.id)}
                onExport={() => {
                  setSelectedSnapshot(snapshot)
                  setExportModalOpen(true)
                }}
              />
            ))}
          </div>
        ) : treeData ? (
          <ExplorationTreeView
            tree={treeData}
            selectedNodeId={selectedSnapshot?.id}
            onSelectNode={(nodeId) => {
              const snapshot = sortedSnapshots.find(s => s.id === nodeId)
              if (snapshot) setSelectedSnapshot(snapshot)
            }}
            snapshotImages={
              // Build a map of snapshot ID to base64 image
              sortedSnapshots.reduce((acc, snap) => {
                if (snap.image_b64) acc[snap.id] = snap.image_b64
                return acc
              }, {} as Record<string, string>)
            }
          />
        ) : (
          <div className="text-center py-12 text-slate-500">
            Loading tree...
          </div>
        )}
      </div>

      {/* Export Modal */}
      {exportModalOpen && selectedSnapshot && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">Export to Style Library</h3>
            <input
              type="text"
              value={exportName}
              onChange={(e) => setExportName(e.target.value)}
              placeholder="Style name..."
              className="w-full px-3 py-2 border border-slate-300 rounded-lg mb-4"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setExportModalOpen(false)}
                className="px-4 py-2 text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => exportMutation.mutate()}
                disabled={!exportName.trim() || exportMutation.isPending}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {exportMutation.isPending ? 'Exporting...' : 'Export'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Batch Explore Modal */}
      {batchModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
            <h3 className="text-lg font-semibold text-slate-800 mb-2">Batch Explore</h3>
            <p className="text-sm text-slate-600 mb-4">
              Run multiple strategies at once from {selectedSnapshot ? 'selected snapshot' : 'current position'}.
              Each strategy creates a separate branch.
            </p>

            {/* Strategy Selection Summary */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50 mb-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-lg font-semibold text-purple-600">
                  {batchStrategies.length} strategies selected
                </span>
                <button
                  type="button"
                  onClick={() => setShowStrategySelectionModal(true)}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm"
                >
                  Select Strategies
                </button>
              </div>

              {batchStrategies.length > 0 ? (
                <div className="flex flex-wrap gap-1.5 max-h-[150px] overflow-y-auto">
                  {batchStrategies.slice(0, 15).map((strategy) => (
                    <span
                      key={strategy}
                      className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs"
                    >
                      {getStrategyDisplayName(strategy)}
                    </span>
                  ))}
                  {batchStrategies.length > 15 && (
                    <span className="px-2 py-1 bg-slate-200 text-slate-600 rounded text-xs">
                      +{batchStrategies.length - 15} more
                    </span>
                  )}
                </div>
              ) : (
                <p className="text-sm text-slate-500 italic">
                  No strategies selected. Click "Select Strategies" to choose.
                </p>
              )}
            </div>

            {/* Quick Presets */}
            <div className="mb-4">
              <label className="block text-xs font-medium text-slate-500 mb-2">Quick Presets</label>
              <div className="flex flex-wrap gap-2">
                {Object.entries(STRATEGY_PRESETS).map(([key, preset]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setBatchStrategies(preset.strategies)}
                    className="px-3 py-1 text-xs border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    {preset.name} ({preset.strategies.length})
                  </button>
                ))}
              </div>
            </div>

            {/* Iterations */}
            <div className="mb-4 flex items-center gap-3">
              <label className="text-sm font-medium text-slate-700">
                Iterations per strategy:
              </label>
              <input
                type="number"
                value={batchIterations}
                onChange={(e) => setBatchIterations(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))}
                className="w-20 px-3 py-2 border border-slate-300 rounded-lg text-center"
                min={1}
                max={10}
              />
              <span className="text-sm text-slate-500">
                = {batchStrategies.length * batchIterations} total images
              </span>
            </div>

            {batchStrategies.length * batchIterations > 50 && (
              <div className="mb-4 p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700">
                Warning: Generating {batchStrategies.length * batchIterations} images may take a while.
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button
                onClick={() => setBatchModalOpen(false)}
                className="px-4 py-2 text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => batchMutation.mutate()}
                disabled={batchStrategies.length === 0 || batchMutation.isPending}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {batchMutation.isPending ? 'Running...' : `Run ${batchStrategies.length * batchIterations} Images`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Strategy Selection Modal */}
      <StrategySelectionModal
        isOpen={showStrategySelectionModal}
        onClose={() => setShowStrategySelectionModal(false)}
        selectedStrategies={batchStrategies}
        onSelectionChange={setBatchStrategies}
        title="Select Batch Strategies"
        description="Choose which strategies to run in batch exploration"
      />
    </div>
  )
}

interface SnapshotCardProps {
  snapshot: ExplorationSnapshot
  isSelected: boolean
  isCurrent: boolean
  onSelect: () => void
  onFavorite: () => void
  onSetCurrent: () => void
  onExport: () => void
}

function SnapshotCard({
  snapshot,
  isSelected,
  isCurrent,
  onSelect,
  onFavorite,
  onSetCurrent,
  onExport,
}: SnapshotCardProps) {
  const strategyName = getStrategyDisplayName(snapshot.mutation_strategy)

  const imageSrc = snapshot.image_b64
    ? `data:image/png;base64,${snapshot.image_b64}`
    : `/api/files/${extractRelativePath(snapshot.generated_image_path)}`

  return (
    <div
      className={`bg-white rounded-lg border-2 overflow-hidden transition-all cursor-pointer ${
        isSelected
          ? 'border-blue-500 ring-2 ring-blue-200'
          : isCurrent
          ? 'border-green-500'
          : 'border-slate-200 hover:border-slate-300'
      }`}
      onClick={onSelect}
    >
      {/* Image */}
      <div className="aspect-square bg-slate-100 relative group">
        <img
          src={imageSrc}
          alt={snapshot.mutation_description}
          className="w-full h-full object-cover"
          onError={(e) => {
            e.currentTarget.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect fill="%23ddd" width="100" height="100"/%3E%3C/svg%3E'
          }}
        />

        {/* Score badge */}
        {snapshot.scores && (
          <div className="absolute top-2 right-2 bg-black/70 text-white text-xs font-bold px-2 py-1 rounded">
            {Math.round(snapshot.scores.combined)}
          </div>
        )}

        {/* Favorite indicator */}
        {snapshot.is_favorite && (
          <div className="absolute top-2 left-2 text-yellow-400 text-lg">★</div>
        )}

        {/* Current indicator */}
        {isCurrent && (
          <div className="absolute bottom-2 left-2 bg-green-500 text-white text-xs px-2 py-0.5 rounded">
            Current
          </div>
        )}

        {/* Depth indicator */}
        <div className="absolute bottom-2 right-2 bg-black/50 text-white text-xs px-2 py-0.5 rounded">
          D{snapshot.depth}
        </div>

        {/* Hover actions */}
        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); onFavorite() }}
            className="p-2 bg-white rounded-full hover:bg-yellow-100"
            title={snapshot.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
          >
            {snapshot.is_favorite ? '★' : '☆'}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onSetCurrent() }}
            className="p-2 bg-white rounded-full hover:bg-green-100"
            title="Set as current (branch point)"
          >
            ↪
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onExport() }}
            className="p-2 bg-white rounded-full hover:bg-purple-100"
            title="Export to style library"
          >
            ↗
          </button>
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <div className="inline-block text-xs px-2 py-0.5 rounded bg-purple-100 text-purple-700">
          {strategyName}
        </div>
        <div className="text-xs text-slate-600 mt-1 line-clamp-2">
          {snapshot.mutation_description.replace(/^[^:]+:\s*/, '')}
        </div>

        {/* Scores */}
        {snapshot.scores && (
          <div className="flex gap-2 mt-2 text-xs">
            <span className="text-blue-600" title="Novelty">N:{Math.round(snapshot.scores.novelty)}</span>
            <span className="text-green-600" title="Coherence">C:{Math.round(snapshot.scores.coherence)}</span>
            <span className="text-purple-600" title="Interest">I:{Math.round(snapshot.scores.interest)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default StyleExplorer
