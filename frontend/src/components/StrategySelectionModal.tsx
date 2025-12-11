import { useState, useMemo } from 'react'
import { MutationStrategy } from '../types'

// Strategy definitions organized into 6 condensed categories
const STRATEGY_CATEGORIES: {
  id: string
  name: string
  description: string
  color: string
  strategies: { key: MutationStrategy; name: string; description: string }[]
}[] = [
  {
    id: 'core',
    name: 'Core & Style',
    description: 'Fundamental mutations, era/medium/mood shifts, and cultural transformations',
    color: 'bg-purple-500',
    strategies: [
      // Core mutations
      { key: 'random_dimension', name: 'Random Dimension', description: 'Push random style dimensions to extremes' },
      { key: 'what_if', name: 'What If?', description: 'VLM-guided creative mutations' },
      { key: 'crossover', name: 'Crossover', description: 'Blend with different art styles' },
      { key: 'inversion', name: 'Inversion', description: 'Flip characteristics to opposites' },
      { key: 'amplify', name: 'Amplify', description: 'Exaggerate existing traits' },
      { key: 'diverge', name: 'Diverge', description: 'Extract-and-deviate: analyze then break' },
      { key: 'refine', name: 'Refine', description: 'Moderate extremes toward balance' },
      { key: 'chaos', name: 'Chaos', description: 'Multiple random mutations at once' },
      // Style transformations
      { key: 'time_shift', name: 'Time Shift', description: 'Transport to a different era' },
      { key: 'medium_swap', name: 'Medium Swap', description: 'Change artistic medium' },
      { key: 'mood_shift', name: 'Mood Shift', description: 'Transform emotional tone' },
      { key: 'culture_shift', name: 'Culture Shift', description: 'Apply cultural aesthetics' },
      // Narrative
      { key: 'narrative_resonance', name: 'Narrative Resonance', description: 'Apply story archetypes' },
      { key: 'archetype_mask', name: 'Archetype Mask', description: 'Overlay universal symbols' },
      { key: 'anomaly_inject', name: 'Anomaly Inject', description: 'VLM-guided surreal intrusion' },
      { key: 'spectral_echo', name: 'Spectral Echo', description: 'Ghostly afterimages' },
    ],
  },
  {
    id: 'color',
    name: 'Color & Light',
    description: 'Chromatic shifts, lighting behavior, shadows, highlights, and bloom effects',
    color: 'bg-amber-500',
    strategies: [
      // Chromatic
      { key: 'chroma_band_shift', name: 'Chroma Band Shift', description: 'Shift colors in specific hue band' },
      { key: 'chromatic_noise', name: 'Chromatic Noise', description: 'Color-separated noise like film grain' },
      { key: 'chromatic_temperature_split', name: 'Temperature Split', description: 'Warm highlights, cool shadows' },
      { key: 'chromatic_fuse', name: 'Chromatic Fuse', description: 'Merge hues into unified mega-hue' },
      { key: 'chromatic_split', name: 'Chromatic Split', description: 'Separate hue into sub-hues' },
      { key: 'chromatic_gravity', name: 'Chromatic Gravity', description: 'Colors as forces' },
      { key: 'color_role_reassignment', name: 'Color Role Swap', description: 'Swap color roles' },
      { key: 'saturation_scalpel', name: 'Saturation Scalpel', description: 'Selective saturation' },
      { key: 'negative_color_injection', name: 'Negative Color', description: 'Inverted color accents' },
      { key: 'ambient_color_suction', name: 'Ambient Suction', description: 'Pull ambient into shadows' },
      { key: 'local_color_mutation', name: 'Local Color', description: 'Zone-specific palette changes' },
      // Lighting/Shadow
      { key: 'ambient_occlusion_variance', name: 'AO Variance', description: 'Alter ambient occlusion' },
      { key: 'specular_flip', name: 'Specular Flip', description: 'Matte/glossy swap' },
      { key: 'bloom_variance', name: 'Bloom Variance', description: 'Adjust bloom effects' },
      { key: 'desync_lighting_channels', name: 'Desync Lighting', description: 'Randomize lighting channels' },
      { key: 'highlight_shift', name: 'Highlight Shift', description: 'Modify highlight behavior' },
      { key: 'shadow_recode', name: 'Shadow Recode', description: 'Rewrite shadow behavior' },
      { key: 'lighting_angle_shift', name: 'Light Angle', description: 'Move light source' },
      { key: 'highlight_bloom_colorize', name: 'Bloom Colorize', description: 'Color highlight bloom' },
      { key: 'micro_shadowing', name: 'Micro-Shadows', description: 'Tiny crisp shadows' },
      { key: 'macro_shadow_pivot', name: 'Shadow Pivot', description: 'Reposition shadow masses' },
      // Tonal
      { key: 'midtone_shift', name: 'Midtone Shift', description: 'Mutate midtones only' },
      { key: 'tonal_compression', name: 'Tonal Compress', description: 'Flatten tonal range' },
      { key: 'tonal_expansion', name: 'Tonal Expand', description: 'Expand tonal range' },
      { key: 'microcontrast_tuning', name: 'Microcontrast', description: 'Small-scale contrast' },
      { key: 'contrast_channel_swap', name: 'Channel Contrast', description: 'Selective channel contrast' },
      { key: 'vignette_modification', name: 'Vignette', description: 'Add/modify vignette' },
    ],
  },
  {
    id: 'texture',
    name: 'Texture & Material',
    description: 'Surface properties, materials, noise, edges, contours, and line quality',
    color: 'bg-orange-500',
    strategies: [
      // Texture
      { key: 'texture_direction_shift', name: 'Texture Direction', description: 'Rotate texture direction' },
      { key: 'noise_injection', name: 'Noise Injection', description: 'Add controlled noise' },
      { key: 'microfracture_pattern', name: 'Microfracture', description: 'Add cracking lines' },
      { key: 'crosshatch_density_shift', name: 'Crosshatch', description: 'Alter crosshatching' },
      // Material/Surface
      { key: 'background_material_swap', name: 'BG Material', description: 'Change backdrop material' },
      { key: 'surface_material_shift', name: 'Surface Material', description: 'Transform surface feel' },
      { key: 'translucency_shift', name: 'Translucency', description: 'Alter transparency' },
      { key: 'subsurface_scatter_tweak', name: 'Subsurface', description: 'Internal glow adjustment' },
      { key: 'anisotropy_shift', name: 'Anisotropy', description: 'Directional reflections' },
      { key: 'reflectivity_shift', name: 'Reflectivity', description: 'Change reflectivity' },
      { key: 'material_transmute', name: 'Material Transmute', description: 'Transform all surfaces' },
      // Contour/Edge
      { key: 'contour_simplify', name: 'Contour Simplify', description: 'Reduce contour lines' },
      { key: 'contour_complexify', name: 'Contour Complex', description: 'Add contour detail' },
      { key: 'line_weight_modulation', name: 'Line Weight', description: 'Change line thickness' },
      { key: 'edge_behavior_swap', name: 'Edge Swap', description: 'Soft/hard/broken edges' },
      { key: 'boundary_echo', name: 'Boundary Echo', description: 'Duplicated outlines' },
      { key: 'halo_generation', name: 'Halo Generation', description: 'Glow around shapes' },
      // Overlay/Pattern
      { key: 'pattern_overlay', name: 'Pattern Overlay', description: 'Repeating pattern overlay' },
      { key: 'gradient_remap', name: 'Gradient Remap', description: 'Reassign gradient behavior' },
      // Technical
      { key: 'algorithmic_wrinkle', name: 'Algorithmic Wrinkle', description: 'Computational artifacts' },
      { key: 'symbolic_reduction', name: 'Symbolic Reduction', description: 'Reduce to symbols' },
    ],
  },
  {
    id: 'shape',
    name: 'Shape & Form',
    description: 'Silhouettes, geometry, proportions, detail density, and form complexity',
    color: 'bg-blue-500',
    strategies: [
      // Silhouette
      { key: 'silhouette_shift', name: 'Silhouette Shift', description: 'Transform shape language' },
      { key: 'silhouette_merge', name: 'Silhouette Merge', description: 'Fuse silhouettes' },
      { key: 'silhouette_subtract', name: 'Silhouette Subtract', description: 'Negative-space shapes' },
      { key: 'silhouette_distortion', name: 'Silhouette Distort', description: 'Stretch/bend/fracture' },
      { key: 'internal_geometry_twist', name: 'Internal Twist', description: 'Twist inside shape' },
      // Detail/Form
      { key: 'detail_density_shift', name: 'Detail Density', description: 'Where detail clusters' },
      { key: 'form_simplification', name: 'Form Simplify', description: 'Reduce to simpler geometry' },
      { key: 'form_complication', name: 'Form Complicate', description: 'Add micro-detail' },
      { key: 'proportion_shift', name: 'Proportion Shift', description: 'Change proportions' },
      // Density
      { key: 'density_shift', name: 'Density Shift', description: 'Adjust visual density' },
      { key: 'dimensional_shift', name: 'Dimensional Shift', description: 'Flatten or deepen space' },
      { key: 'micro_macro_swap', name: 'Micro/Macro Swap', description: 'Flip detail scale' },
      { key: 'essence_strip', name: 'Essence Strip', description: 'VLM-guided reduction' },
      // Motif
      { key: 'motif_splice', name: 'Motif Splice', description: 'Inject recurring patterns' },
      { key: 'motif_mirroring', name: 'Motif Mirror', description: 'Mirror motif' },
      { key: 'motif_scaling', name: 'Motif Scale', description: 'Scale repeated motifs' },
      { key: 'motif_repetition', name: 'Motif Repeat', description: 'Duplicate and scatter' },
    ],
  },
  {
    id: 'space',
    name: 'Space & Composition',
    description: 'Perspective, depth, spatial hierarchy, layout, balance, and visual flow',
    color: 'bg-emerald-500',
    strategies: [
      // Spatial
      { key: 'topology_fold', name: 'Topology Fold', description: 'Warp spatial logic' },
      { key: 'perspective_drift', name: 'Perspective Drift', description: 'Shift viewpoint' },
      { key: 'axis_swap', name: 'Axis Swap', description: 'Rotate orientation' },
      { key: 'local_perspective_bend', name: 'Local Perspective', description: 'Bend localized perspective' },
      // Depth
      { key: 'background_depth_collapse', name: 'Depth Collapse', description: 'Compress background' },
      { key: 'depth_flattening', name: 'Depth Flatten', description: 'Reduce depth cues' },
      { key: 'depth_expansion', name: 'Depth Expand', description: 'Exaggerate perspective' },
      // Composition
      { key: 'scale_warp', name: 'Scale Warp', description: 'Change scale perspective' },
      { key: 'remix', name: 'Remix', description: 'Shuffle style sections' },
      { key: 'constrain', name: 'Constrain', description: 'Apply strict limits' },
      { key: 'decay', name: 'Decay', description: 'Add entropy/aging' },
      { key: 'quadrant_mutation', name: 'Quadrant', description: 'Mutate one quadrant' },
      { key: 'object_alignment_shift', name: 'Alignment Shift', description: 'Misalign objects' },
      { key: 'spatial_hierarchy_flip', name: 'Hierarchy Flip', description: 'Reorder visual priority' },
      { key: 'balance_shift', name: 'Balance Shift', description: 'Shift visual weight' },
      { key: 'interplay_swap', name: 'Interplay Swap', description: 'Swap element dominance' },
      { key: 'frame_reinterpretation', name: 'Frame', description: 'Alter conceptual border' },
      // Blur/Focus
      { key: 'directional_blur', name: 'Directional Blur', description: 'Motion-like blur' },
      { key: 'focal_plane_shift', name: 'Focal Plane', description: 'Move focus point' },
      { key: 'mask_boundary_mutation', name: 'Mask Boundary', description: 'Modify mask borders' },
    ],
  },
  {
    id: 'rhythm',
    name: 'Rhythm & Environment',
    description: 'Visual rhythm, flow, patterns, weather, atmosphere, and physics bending',
    color: 'bg-teal-500',
    strategies: [
      // Pattern & Rhythm
      { key: 'rhythm_overlay', name: 'Rhythm Overlay', description: 'Add visual cadence' },
      { key: 'harmonic_balance', name: 'Harmonic Balance', description: 'Compositional harmony' },
      { key: 'symmetry_break', name: 'Symmetry Break', description: 'Disrupt symmetry' },
      // Flow/Rhythm
      { key: 'path_flow_shift', name: 'Path Flow', description: 'Alter directional flow' },
      { key: 'rhythm_disruption', name: 'Rhythm Disrupt', description: 'Break repetition intervals' },
      { key: 'rhythm_rebalance', name: 'Rhythm Rebalance', description: 'Adjust motif spacing' },
      { key: 'directional_energy_shift', name: 'Energy Shift', description: 'Alter implied flow' },
      // Environment
      { key: 'climate_morph', name: 'Climate Morph', description: 'Apply weather/atmosphere' },
      { key: 'biome_shift', name: 'Biome Shift', description: 'Different ecosystem' },
      { key: 'atmospheric_scatter_shift', name: 'Atmospheric Scatter', description: 'Change light scatter' },
      { key: 'occlusion_pattern', name: 'Occlusion Pattern', description: 'Hidden behind layers' },
      { key: 'opacity_fog', name: 'Opacity Fog', description: 'Translucent fog layer' },
      // Physics
      { key: 'physics_bend', name: 'Physics Bend', description: 'Alter physical laws' },
      { key: 'temporal_exposure', name: 'Temporal Exposure', description: 'Layer time in image' },
    ],
  },
]

// Get all strategies flat
export const ALL_STRATEGIES = STRATEGY_CATEGORIES.flatMap(c => c.strategies)

// Quick presets for common use cases
export const STRATEGY_PRESETS: Record<string, { name: string; strategies: MutationStrategy[] }> = {
  core: { name: 'Core', strategies: ['random_dimension', 'what_if', 'amplify', 'diverge', 'crossover', 'inversion'] },
  chromatic: { name: 'Chromatic', strategies: ['chroma_band_shift', 'chromatic_noise', 'chromatic_temperature_split', 'chromatic_fuse', 'color_role_reassignment'] },
  lighting: { name: 'Lighting', strategies: ['highlight_shift', 'shadow_recode', 'lighting_angle_shift', 'bloom_variance', 'ambient_occlusion_variance'] },
  texture: { name: 'Texture', strategies: ['texture_direction_shift', 'noise_injection', 'surface_material_shift', 'contour_simplify', 'line_weight_modulation'] },
  shape: { name: 'Shape', strategies: ['silhouette_shift', 'form_simplification', 'proportion_shift', 'density_shift', 'motif_splice'] },
  composition: { name: 'Composition', strategies: ['scale_warp', 'perspective_drift', 'balance_shift', 'depth_expansion', 'focal_plane_shift'] },
}

interface StrategySelectionModalProps {
  isOpen: boolean
  onClose: () => void
  selectedStrategies: MutationStrategy[]
  onSelectionChange: (strategies: MutationStrategy[]) => void
  title?: string
  description?: string
}

export default function StrategySelectionModal({
  isOpen,
  onClose,
  selectedStrategies,
  onSelectionChange,
  title = 'Select Mutation Strategies',
  description,
}: StrategySelectionModalProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(STRATEGY_CATEGORIES.map(c => c.id))
  )

  // Filter strategies based on search
  const filteredCategories = useMemo(() => {
    if (!searchQuery.trim()) return STRATEGY_CATEGORIES
    const query = searchQuery.toLowerCase()
    return STRATEGY_CATEGORIES.map(cat => ({
      ...cat,
      strategies: cat.strategies.filter(
        s => s.name.toLowerCase().includes(query) || s.description.toLowerCase().includes(query)
      ),
    })).filter(cat => cat.strategies.length > 0)
  }, [searchQuery])

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev)
      if (next.has(categoryId)) {
        next.delete(categoryId)
      } else {
        next.add(categoryId)
      }
      return next
    })
  }

  const toggleStrategy = (strategy: MutationStrategy) => {
    if (selectedStrategies.includes(strategy)) {
      onSelectionChange(selectedStrategies.filter(s => s !== strategy))
    } else {
      onSelectionChange([...selectedStrategies, strategy])
    }
  }

  const selectAllInCategory = (categoryId: string) => {
    const category = STRATEGY_CATEGORIES.find(c => c.id === categoryId)
    if (!category) return
    const categoryStrategies = category.strategies.map(s => s.key)
    const allSelected = categoryStrategies.every(s => selectedStrategies.includes(s))
    if (allSelected) {
      onSelectionChange(selectedStrategies.filter(s => !categoryStrategies.includes(s)))
    } else {
      onSelectionChange([...new Set([...selectedStrategies, ...categoryStrategies])])
    }
  }

  const selectAll = () => {
    const allStrategies = STRATEGY_CATEGORIES.flatMap(c => c.strategies.map(s => s.key))
    onSelectionChange(allStrategies)
  }

  const clearAll = () => {
    onSelectionChange([])
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-xl shadow-xl w-[90vw] max-w-4xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
            {description && <p className="text-sm text-slate-500">{description}</p>}
            <p className="text-sm text-purple-600 font-medium">{selectedStrategies.length} strategies selected</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Search & Quick Actions */}
        <div className="p-4 border-b space-y-3">
          {/* Search */}
          <div className="relative">
            <input
              type="text"
              placeholder="Search strategies..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
            />
            <svg className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>

          {/* Quick Presets */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">Presets:</span>
            {Object.entries(STRATEGY_PRESETS).map(([key, preset]) => (
              <button
                key={key}
                onClick={() => onSelectionChange(preset.strategies)}
                className="px-2 py-1 text-xs border border-slate-300 rounded hover:bg-slate-100"
              >
                {preset.name}
              </button>
            ))}
            <span className="mx-2 text-slate-300">|</span>
            <button onClick={selectAll} className="px-2 py-1 text-xs text-purple-600 hover:bg-purple-50 rounded">
              All
            </button>
            <button onClick={clearAll} className="px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded">
              Clear
            </button>
          </div>
        </div>

        {/* Categories */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-3">
            {filteredCategories.map(category => {
              const isExpanded = expandedCategories.has(category.id) || searchQuery.trim().length > 0
              const selectedCount = category.strategies.filter(s => selectedStrategies.includes(s.key)).length
              const allSelected = selectedCount === category.strategies.length

              return (
                <div key={category.id} className="border border-slate-200 rounded-lg overflow-hidden">
                  {/* Category Header */}
                  <div
                    className="flex items-center gap-3 p-3 bg-slate-50 cursor-pointer hover:bg-slate-100"
                    onClick={() => toggleCategory(category.id)}
                  >
                    <div className={`w-3 h-3 rounded-full ${category.color}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-slate-800">{category.name}</span>
                        <span className="text-xs text-slate-500">({category.strategies.length})</span>
                        {selectedCount > 0 && (
                          <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">
                            {selectedCount} selected
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 truncate">{category.description}</p>
                    </div>
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        selectAllInCategory(category.id)
                      }}
                      className="px-2 py-1 text-xs text-purple-600 hover:bg-purple-100 rounded whitespace-nowrap"
                    >
                      {allSelected ? 'None' : 'All'}
                    </button>
                    <svg
                      className={`w-5 h-5 text-slate-400 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>

                  {/* Strategies Grid */}
                  {isExpanded && (
                    <div className="p-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                      {category.strategies.map(strategy => {
                        const isSelected = selectedStrategies.includes(strategy.key)
                        return (
                          <label
                            key={strategy.key}
                            className={`group relative flex items-start gap-2 p-2 rounded cursor-pointer transition-colors ${
                              isSelected
                                ? 'bg-purple-50 border border-purple-300'
                                : 'bg-slate-50 border border-transparent hover:border-slate-200'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleStrategy(strategy.key)}
                              className="mt-0.5 flex-shrink-0"
                            />
                            <span className="text-xs text-slate-700 leading-tight">{strategy.name}</span>
                            {/* Tooltip */}
                            <div className="absolute left-0 bottom-full mb-1 hidden group-hover:block z-50 w-48 p-2 bg-slate-800 text-white text-xs rounded shadow-lg pointer-events-none">
                              <div className="font-medium mb-0.5">{strategy.name}</div>
                              <div className="text-slate-300">{strategy.description}</div>
                            </div>
                          </label>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t bg-slate-50">
          <div className="text-sm text-slate-600">
            {selectedStrategies.length} of {ALL_STRATEGIES.length} strategies
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} className="px-4 py-2 text-slate-600 hover:text-slate-800">
              Cancel
            </button>
            <button
              onClick={onClose}
              className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
            >
              Apply
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
