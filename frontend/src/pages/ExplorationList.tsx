import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listExplorations, createExploration, deleteExploration, exploreStep } from '../api/client'
import { ExplorationSessionSummary, MutationStrategy } from '../types'
import ImageUpload from '../components/ImageUpload'

function ExplorationList() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
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

  const toggleStrategy = (strategy: MutationStrategy) => {
    setSelectedStrategies((prev) =>
      prev.includes(strategy)
        ? prev.filter((s) => s !== strategy)
        : [...prev, strategy]
    )
  }

  const allStrategies: { key: MutationStrategy; name: string; description: string; category: string }[] = [
    // Core mutations
    { key: 'random_dimension', name: 'Random Dimension', description: 'Push random style dimensions to extremes', category: 'Core' },
    { key: 'what_if', name: 'What If?', description: 'VLM-guided creative mutations', category: 'Core' },
    { key: 'crossover', name: 'Crossover', description: 'Blend with different art styles', category: 'Core' },
    { key: 'inversion', name: 'Inversion', description: 'Flip characteristics to opposites', category: 'Core' },
    { key: 'amplify', name: 'Amplify', description: 'Exaggerate existing traits', category: 'Core' },
    { key: 'diverge', name: 'Diverge', description: 'Extract-and-deviate: analyze then break from it', category: 'Core' },
    { key: 'refine', name: 'Refine', description: 'Moderate extremes toward balance', category: 'Core' },
    // Style transformations
    { key: 'time_shift', name: 'Time Shift', description: 'Transport to a different era (Art Deco, 80s Memphis, etc.)', category: 'Style' },
    { key: 'medium_swap', name: 'Medium Swap', description: 'Change artistic medium (oil, watercolor, pencil, etc.)', category: 'Style' },
    { key: 'mood_shift', name: 'Mood Shift', description: 'Transform emotional tone (serene, anxious, joyful, etc.)', category: 'Style' },
    { key: 'culture_shift', name: 'Culture Shift', description: 'Apply cultural aesthetics (Japanese, Moroccan, Celtic, etc.)', category: 'Style' },
    // Composition mutations
    { key: 'scale_warp', name: 'Scale Warp', description: 'Change perspective/scale (macro, cosmic, miniature)', category: 'Composition' },
    { key: 'decay', name: 'Decay', description: 'Add entropy/aging (weathered, rusted, overgrown)', category: 'Composition' },
    { key: 'remix', name: 'Remix', description: 'Shuffle elements between style sections', category: 'Composition' },
    { key: 'constrain', name: 'Constrain', description: 'Apply strict limits (monochrome, basic shapes)', category: 'Composition' },
    { key: 'chaos', name: 'Chaos', description: 'Multiple random mutations at once', category: 'Composition' },
    // Spatial mutations
    { key: 'topology_fold', name: 'Topology Fold', description: 'Warp spatial logic (mobius, recursive, tesseract)', category: 'Spatial' },
    { key: 'silhouette_shift', name: 'Silhouette Shift', description: 'Transform shape language (angular, organic, crystalline)', category: 'Spatial' },
    { key: 'perspective_drift', name: 'Perspective Drift', description: 'Shift viewpoint (fish-eye, orthographic, anamorphic)', category: 'Spatial' },
    { key: 'axis_swap', name: 'Axis Swap', description: 'Rotate orientation (diagonal, spiral, radial)', category: 'Spatial' },
    // Physics mutations
    { key: 'physics_bend', name: 'Physics Bend', description: 'Alter physical laws (zero-g, liquid time, reverse entropy)', category: 'Physics' },
    { key: 'chromatic_gravity', name: 'Chromatic Gravity', description: 'Colors become forces (bleeding, pooling, orbiting)', category: 'Physics' },
    { key: 'material_transmute', name: 'Material Transmute', description: 'Transform surfaces (glass, mercury, velvet)', category: 'Physics' },
    { key: 'temporal_exposure', name: 'Temporal Exposure', description: 'Layer time (motion blur, frozen moment, time-lapse)', category: 'Physics' },
    // Pattern mutations
    { key: 'motif_splice', name: 'Motif Splice', description: 'Inject recurring patterns (fractals, tessellation)', category: 'Pattern' },
    { key: 'rhythm_overlay', name: 'Rhythm Overlay', description: 'Add visual cadence (syncopated, crescendo)', category: 'Pattern' },
    { key: 'harmonic_balance', name: 'Harmonic Balance', description: 'Apply compositional harmony (golden ratio, rule of thirds)', category: 'Pattern' },
    { key: 'symmetry_break', name: 'Symmetry Break', description: 'Disrupt or introduce symmetry (bilateral, rotational)', category: 'Pattern' },
    // Density mutations
    { key: 'density_shift', name: 'Density Shift', description: 'Adjust visual density (sparse, cluttered, gradient)', category: 'Density' },
    { key: 'dimensional_shift', name: 'Dimensional Shift', description: 'Flatten or deepen space (isometric, 2.5D)', category: 'Density' },
    { key: 'micro_macro_swap', name: 'Micro/Macro Swap', description: 'Flip detail scale (micro becomes macro)', category: 'Density' },
    { key: 'essence_strip', name: 'Essence Strip', description: 'VLM-guided reduction to pure essence', category: 'Density' },
    // Narrative mutations
    { key: 'narrative_resonance', name: 'Narrative Resonance', description: 'Apply story archetypes (hero\'s journey, tragedy)', category: 'Narrative' },
    { key: 'archetype_mask', name: 'Archetype Mask', description: 'Overlay universal symbols (shadow, trickster, sage)', category: 'Narrative' },
    { key: 'anomaly_inject', name: 'Anomaly Inject', description: 'VLM-guided surreal intrusion (impossible object)', category: 'Narrative' },
    { key: 'spectral_echo', name: 'Spectral Echo', description: 'Add ghostly afterimages and traces', category: 'Narrative' },
    // Environment mutations
    { key: 'climate_morph', name: 'Climate Morph', description: 'Apply weather/atmosphere (fog, rain, aurora)', category: 'Environment' },
    { key: 'biome_shift', name: 'Biome Shift', description: 'Transport to different ecosystem (deep sea, volcanic)', category: 'Environment' },
    // Technical mutations
    { key: 'algorithmic_wrinkle', name: 'Algorithmic Wrinkle', description: 'Add computational artifacts (dithering, scanlines)', category: 'Technical' },
    { key: 'symbolic_reduction', name: 'Symbolic Reduction', description: 'Reduce to symbolic representation (hieroglyphic, emoji)', category: 'Technical' },
  ]

  // Group strategies by category for display
  const strategyCategories = allStrategies.reduce((acc, strategy) => {
    if (!acc[strategy.category]) acc[strategy.category] = []
    acc[strategy.category].push(strategy)
    return acc
  }, {} as Record<string, typeof allStrategies>)

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

            {/* Right: Strategy Selection */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Mutation Strategies ({selectedStrategies.length} selected)
              </label>
              <p className="text-xs text-slate-500 mb-3">
                Select which strategies will be used during exploration
              </p>
              <div className="max-h-[500px] overflow-y-auto space-y-4 pr-2">
                {Object.entries(strategyCategories).map(([category, strategies]) => (
                  <div key={category}>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-semibold text-slate-600">{category}</h4>
                      <button
                        type="button"
                        onClick={() => {
                          const categoryKeys = strategies.map(s => s.key)
                          const allSelected = categoryKeys.every(k => selectedStrategies.includes(k))
                          if (allSelected) {
                            setSelectedStrategies(prev => prev.filter(s => !categoryKeys.includes(s)))
                          } else {
                            setSelectedStrategies(prev => [...new Set([...prev, ...categoryKeys])])
                          }
                        }}
                        className="text-xs text-purple-600 hover:text-purple-700"
                      >
                        {strategies.every(s => selectedStrategies.includes(s.key)) ? 'Deselect all' : 'Select all'}
                      </button>
                    </div>
                    <div className="space-y-1">
                      {strategies.map((strategy) => (
                        <label
                          key={strategy.key}
                          className={`flex items-start gap-3 p-2 rounded-lg border cursor-pointer transition-colors ${
                            selectedStrategies.includes(strategy.key)
                              ? 'border-purple-500 bg-purple-50'
                              : 'border-slate-200 hover:border-slate-300'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedStrategies.includes(strategy.key)}
                            onChange={() => toggleStrategy(strategy.key)}
                            className="mt-0.5"
                          />
                          <div>
                            <div className="font-medium text-slate-800 text-sm">{strategy.name}</div>
                            <div className="text-xs text-slate-500">{strategy.description}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
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
