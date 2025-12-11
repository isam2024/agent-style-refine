import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listExplorations, createExploration, deleteExploration, exploreStep } from '../api/client'
import { ExplorationSessionSummary, MutationStrategy } from '../types'
import ImageUpload from '../components/ImageUpload'
import StrategySelectionModal from '../components/StrategySelectionModal'

function ExplorationList() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [showStrategyModal, setShowStrategyModal] = useState(false)
  const [newName, setNewName] = useState('')
  const [newImage, setNewImage] = useState<string | null>(null)
  const [selectedStrategies, setSelectedStrategies] = useState<MutationStrategy[]>([
    'random_dimension',
    'what_if',
    'amplify',
  ])

  const { data: explorations, isLoading } = useQuery({
    queryKey: ['explorations'],
    queryFn: listExplorations,
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      // Create the session
      const session = await createExploration(newName, newImage!, selectedStrategies)
      // Auto-start first exploration step
      await exploreStep(session.id)
      return session
    },
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['explorations'] })
      setShowCreate(false)
      setNewName('')
      setNewImage(null)
      navigate(`/explore/${session.id}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteExploration(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['explorations'] })
    },
  })

  const handleImageSelect = useCallback((imageB64: string) => {
    setNewImage(imageB64)
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Style Explorer</h1>
          <p className="text-slate-600 mt-1">
            Divergent exploration - discover new style directions
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
        >
          New Exploration
        </button>
      </div>

      {/* Create Panel */}
      {showCreate && (
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-4">Start New Exploration</h2>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: Image and Name */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Reference Image
                </label>
                <ImageUpload onImageSelect={handleImageSelect} currentImage={newImage} />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Exploration Name
                </label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="My Style Exploration"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>

            {/* Right: Strategy Selection Summary */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Mutation Strategies
              </label>
              <p className="text-xs text-slate-500 mb-3">
                Select which strategies will be used during exploration
              </p>

              {/* Strategy summary card */}
              <div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-lg font-semibold text-purple-600">
                    {selectedStrategies.length} strategies selected
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowStrategyModal(true)}
                    className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm"
                  >
                    Select Strategies
                  </button>
                </div>

                {selectedStrategies.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 max-h-[200px] overflow-y-auto">
                    {selectedStrategies.slice(0, 20).map((strategy) => (
                      <span
                        key={strategy}
                        className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs"
                      >
                        {strategy.replace(/_/g, ' ')}
                      </span>
                    ))}
                    {selectedStrategies.length > 20 && (
                      <span className="px-2 py-1 bg-slate-200 text-slate-600 rounded text-xs">
                        +{selectedStrategies.length - 20} more
                      </span>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500 italic">
                    No strategies selected. Click "Select Strategies" to choose.
                  </p>
                )}
              </div>

              {/* Quick presets */}
              <div className="mt-4">
                <label className="block text-xs font-medium text-slate-500 mb-2">Quick Presets</label>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedStrategies(['random_dimension', 'what_if', 'amplify', 'diverge'])}
                    className="px-3 py-1 text-xs border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    Core (4)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedStrategies([
                      'chroma_band_shift', 'chromatic_noise', 'chromatic_temperature_split',
                      'color_role_reassignment', 'saturation_scalpel'
                    ])}
                    className="px-3 py-1 text-xs border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    Chromatic (5)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedStrategies([
                      'ambient_occlusion_variance', 'specular_flip', 'highlight_shift',
                      'shadow_recode', 'lighting_angle_shift'
                    ])}
                    className="px-3 py-1 text-xs border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    Lighting (5)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedStrategies([
                      'contour_simplify', 'contour_complexify', 'line_weight_modulation',
                      'edge_behavior_swap', 'boundary_echo'
                    ])}
                    className="px-3 py-1 text-xs border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    Contour (5)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedStrategies([
                      'time_shift', 'medium_swap', 'mood_shift', 'culture_shift'
                    ])}
                    className="px-3 py-1 text-xs border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    Style (4)
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 mt-6">
            <button
              onClick={() => {
                setShowCreate(false)
                setNewName('')
                setNewImage(null)
              }}
              className="px-4 py-2 text-slate-600 hover:text-slate-800"
            >
              Cancel
            </button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={!newName.trim() || !newImage || selectedStrategies.length === 0 || createMutation.isPending}
              className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {createMutation.isPending ? 'Starting exploration...' : 'Start Exploring'}
            </button>
          </div>
        </div>
      )}

      {/* Strategy Selection Modal */}
      <StrategySelectionModal
        isOpen={showStrategyModal}
        onClose={() => setShowStrategyModal(false)}
        selectedStrategies={selectedStrategies}
        onSelectionChange={setSelectedStrategies}
      />

      {/* Explorations List */}
      {isLoading ? (
        <div className="text-center py-12 text-slate-500">Loading explorations...</div>
      ) : !explorations || explorations.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm p-12 text-center">
          <div className="text-slate-400 text-5xl mb-4">🔮</div>
          <h3 className="text-lg font-semibold text-slate-800 mb-2">No explorations yet</h3>
          <p className="text-slate-600 mb-4">
            Start exploring style variations to discover new aesthetic directions
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            Create Your First Exploration
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {explorations.map((exploration) => (
            <ExplorationCard
              key={exploration.id}
              exploration={exploration}
              onClick={() => navigate(`/explore/${exploration.id}`)}
              onDelete={() => deleteMutation.mutate(exploration.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface ExplorationCardProps {
  exploration: ExplorationSessionSummary
  onClick: () => void
  onDelete: () => void
}

function ExplorationCard({ exploration, onClick, onDelete }: ExplorationCardProps) {
  const statusColors: Record<string, string> = {
    created: 'bg-slate-100 text-slate-600',
    exploring: 'bg-blue-100 text-blue-700',
    paused: 'bg-yellow-100 text-yellow-700',
    completed: 'bg-green-100 text-green-700',
  }

  return (
    <div
      className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden hover:shadow-md transition-shadow cursor-pointer"
      onClick={onClick}
    >
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold text-slate-800">{exploration.name}</h3>
            <div className="flex items-center gap-2 mt-1">
              <span className={`text-xs px-2 py-0.5 rounded ${statusColors[exploration.status] || statusColors.created}`}>
                {exploration.status}
              </span>
              <span className="text-xs text-slate-500">
                {exploration.total_snapshots} snapshots
              </span>
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              if (confirm('Delete this exploration?')) {
                onDelete()
              }
            }}
            className="text-slate-400 hover:text-red-600 p-1"
          >
            ×
          </button>
        </div>
        <div className="text-xs text-slate-500 mt-3">
          Created {new Date(exploration.created_at).toLocaleDateString()}
        </div>
      </div>
    </div>
  )
}

export default ExplorationList
