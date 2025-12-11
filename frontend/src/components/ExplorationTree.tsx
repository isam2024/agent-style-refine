import { useMemo } from 'react'
import { ExplorationTreeNode, ExplorationTree as TreeData } from '../types'

interface ExplorationTreeProps {
  tree: TreeData
  onSelectNode: (nodeId: string) => void
  selectedNodeId?: string
  // Map of snapshot ID to base64 image
  snapshotImages?: Record<string, string>
}

// Strategy colors for visual differentiation
const STRATEGY_COLORS: Record<string, string> = {
  // Core mutations
  random_dimension: '#3b82f6', // blue
  what_if: '#8b5cf6',          // purple
  crossover: '#22c55e',        // green
  inversion: '#f97316',        // orange
  amplify: '#ef4444',          // red
  diverge: '#ec4899',          // pink
  refine: '#14b8a6',           // teal
  // Style transformations
  time_shift: '#f59e0b',       // amber
  medium_swap: '#06b6d4',      // cyan
  mood_shift: '#7c3aed',       // violet
  culture_shift: '#f43f5e',    // rose
  // Composition mutations
  scale_warp: '#10b981',       // emerald
  decay: '#78716c',            // stone
  remix: '#d946ef',            // fuchsia
  constrain: '#64748b',        // slate
  chaos: '#dc2626',            // red-600
  // Spatial mutations
  topology_fold: '#6366f1',    // indigo
  silhouette_shift: '#0ea5e9', // sky
  perspective_drift: '#06b6d4',// cyan
  axis_swap: '#3b82f6',        // blue
  // Physics mutations
  physics_bend: '#8b5cf6',     // violet
  chromatic_gravity: '#d946ef',// fuchsia
  material_transmute: '#ec4899',// pink
  temporal_exposure: '#f43f5e',// rose
  // Pattern mutations
  motif_splice: '#f97316',     // orange
  rhythm_overlay: '#f59e0b',   // amber
  harmonic_balance: '#eab308', // yellow
  symmetry_break: '#84cc16',   // lime
  // Density mutations
  density_shift: '#22c55e',    // green
  dimensional_shift: '#10b981',// emerald
  micro_macro_swap: '#14b8a6', // teal
  essence_strip: '#06b6d4',    // cyan
  // Narrative mutations
  narrative_resonance: '#3b82f6',// blue
  archetype_mask: '#6366f1',   // indigo
  anomaly_inject: '#8b5cf6',   // purple
  spectral_echo: '#7c3aed',    // violet
  // Environment mutations
  climate_morph: '#0ea5e9',    // sky
  biome_shift: '#22c55e',      // green
  // Technical mutations
  algorithmic_wrinkle: '#64748b',// slate
  symbolic_reduction: '#78716c', // stone
}

interface TreeNode extends ExplorationTreeNode {
  children: TreeNode[]
  x: number
  y: number
}

function buildTree(nodes: ExplorationTreeNode[]): TreeNode[] {
  // Create a map for quick lookup
  const nodeMap = new Map<string, TreeNode>()
  nodes.forEach(node => {
    nodeMap.set(node.id, { ...node, children: [], x: 0, y: 0 })
  })

  // Build tree structure
  const roots: TreeNode[] = []
  nodeMap.forEach(node => {
    if (node.parent_id && nodeMap.has(node.parent_id)) {
      nodeMap.get(node.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  })

  return roots
}

function layoutTree(roots: TreeNode[], nodeWidth: number, nodeHeight: number, horizontalGap: number, verticalGap: number): { nodes: TreeNode[], width: number, height: number } {
  let currentX = 0
  const allNodes: TreeNode[] = []

  function layoutSubtree(node: TreeNode, depth: number): number {
    node.y = depth * (nodeHeight + verticalGap)
    allNodes.push(node)

    if (node.children.length === 0) {
      node.x = currentX
      currentX += nodeWidth + horizontalGap
      return node.x
    }

    // Layout children first
    const childXs: number[] = []
    node.children.forEach(child => {
      childXs.push(layoutSubtree(child, depth + 1))
    })

    // Center parent above children
    node.x = (childXs[0] + childXs[childXs.length - 1]) / 2
    return node.x
  }

  roots.forEach(root => {
    layoutSubtree(root, 0)
  })

  const maxX = allNodes.length > 0 ? Math.max(...allNodes.map(n => n.x)) + nodeWidth : nodeWidth
  const maxY = allNodes.length > 0 ? Math.max(...allNodes.map(n => n.y)) + nodeHeight : nodeHeight

  return { nodes: allNodes, width: maxX, height: maxY }
}

function ExplorationTreeView({ tree, onSelectNode, selectedNodeId, snapshotImages = {} }: ExplorationTreeProps) {
  const NODE_WIDTH = 100
  const NODE_HEIGHT = 120
  const H_GAP = 16
  const V_GAP = 32

  const { layoutNodes, svgWidth, svgHeight, edges } = useMemo(() => {
    const roots = buildTree(tree.all_nodes)
    const { nodes, width, height } = layoutTree(roots, NODE_WIDTH, NODE_HEIGHT, H_GAP, V_GAP)

    // Build edges
    const edgeList: { from: TreeNode, to: TreeNode }[] = []
    nodes.forEach(node => {
      node.children.forEach(child => {
        edgeList.push({ from: node, to: child })
      })
    })

    return {
      layoutNodes: nodes,
      svgWidth: Math.max(width + 40, 400),
      svgHeight: Math.max(height + 40, 200),
      edges: edgeList,
    }
  }, [tree.all_nodes])

  if (tree.all_nodes.length === 0) {
    return (
      <div className="bg-slate-100 rounded-lg p-8 text-center text-slate-500">
        No exploration tree yet. Start exploring to build the tree!
      </div>
    )
  }

  return (
    <div className="bg-slate-50 rounded-lg border border-slate-200 overflow-auto">
      <svg
        width={svgWidth}
        height={svgHeight}
        className="min-w-full"
        style={{ minHeight: '200px' }}
      >
        <defs>
          {/* Clip paths for rounded image corners */}
          {layoutNodes.map(node => (
            <clipPath key={`clip-${node.id}`} id={`clip-${node.id}`}>
              <rect x={4} y={10} width={NODE_WIDTH - 8} height={NODE_WIDTH - 8} rx={6} />
            </clipPath>
          ))}
        </defs>

        <g transform="translate(20, 20)">
          {/* Draw edges */}
          {edges.map((edge, i) => (
            <path
              key={i}
              d={`M ${edge.from.x + NODE_WIDTH / 2} ${edge.from.y + NODE_HEIGHT}
                  C ${edge.from.x + NODE_WIDTH / 2} ${edge.from.y + NODE_HEIGHT + V_GAP / 2},
                    ${edge.to.x + NODE_WIDTH / 2} ${edge.to.y - V_GAP / 2},
                    ${edge.to.x + NODE_WIDTH / 2} ${edge.to.y}`}
              fill="none"
              stroke="#94a3b8"
              strokeWidth={2}
            />
          ))}

          {/* Draw nodes */}
          {layoutNodes.map(node => {
            const isSelected = node.id === selectedNodeId
            const isCurrent = node.id === tree.current_snapshot_id
            const strategyColor = STRATEGY_COLORS[node.mutation_strategy] || '#64748b'
            const imageB64 = snapshotImages[node.id]

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={() => onSelectNode(node.id)}
                className="cursor-pointer"
                style={{ filter: isSelected ? 'drop-shadow(0 4px 6px rgba(59, 130, 246, 0.3))' : undefined }}
              >
                {/* Node background */}
                <rect
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx={8}
                  fill="white"
                  stroke={isSelected ? '#3b82f6' : isCurrent ? '#22c55e' : '#e2e8f0'}
                  strokeWidth={isSelected || isCurrent ? 3 : 1}
                />

                {/* Strategy color bar at top */}
                <rect
                  x={0}
                  y={0}
                  width={NODE_WIDTH}
                  height={6}
                  fill={strategyColor}
                  rx={8}
                  ry={8}
                />
                <rect
                  x={0}
                  y={3}
                  width={NODE_WIDTH}
                  height={3}
                  fill={strategyColor}
                />

                {/* Image thumbnail */}
                {imageB64 ? (
                  <image
                    href={`data:image/png;base64,${imageB64}`}
                    x={4}
                    y={10}
                    width={NODE_WIDTH - 8}
                    height={NODE_WIDTH - 8}
                    preserveAspectRatio="xMidYMid slice"
                    clipPath={`url(#clip-${node.id})`}
                  />
                ) : (
                  <rect
                    x={4}
                    y={10}
                    width={NODE_WIDTH - 8}
                    height={NODE_WIDTH - 8}
                    rx={6}
                    fill="#f1f5f9"
                  />
                )}

                {/* Score badge */}
                {node.combined_score !== null && (
                  <g transform={`translate(${NODE_WIDTH - 28}, ${NODE_HEIGHT - 24})`}>
                    <rect
                      x={0}
                      y={0}
                      width={24}
                      height={18}
                      rx={4}
                      fill={node.combined_score >= 80 ? '#22c55e' : node.combined_score >= 60 ? '#eab308' : '#94a3b8'}
                    />
                    <text
                      x={12}
                      y={13}
                      textAnchor="middle"
                      fontSize={10}
                      fontWeight="bold"
                      fill="white"
                    >
                      {Math.round(node.combined_score)}
                    </text>
                  </g>
                )}

                {/* Favorite star */}
                {node.is_favorite && (
                  <g transform={`translate(4, ${NODE_HEIGHT - 24})`}>
                    <circle cx={9} cy={9} r={10} fill="white" />
                    <text
                      x={9}
                      y={14}
                      textAnchor="middle"
                      fontSize={14}
                      fill="#eab308"
                    >
                      ★
                    </text>
                  </g>
                )}

                {/* Current indicator (green dot) */}
                {isCurrent && (
                  <g transform={`translate(${NODE_WIDTH / 2 - 8}, ${NODE_HEIGHT - 6})`}>
                    <circle cx={8} cy={0} r={5} fill="#22c55e" stroke="white" strokeWidth={2} />
                  </g>
                )}
              </g>
            )
          })}
        </g>
      </svg>

      {/* Legend */}
      <div className="border-t border-slate-200 p-3 flex flex-wrap gap-3 text-xs">
        {Object.entries(STRATEGY_COLORS).map(([strategy, color]) => (
          <div key={strategy} className="flex items-center gap-1">
            <div
              className="w-3 h-3 rounded"
              style={{ backgroundColor: color }}
            />
            <span className="text-slate-600 capitalize">
              {strategy.replace('_', ' ')}
            </span>
          </div>
        ))}
        <div className="flex items-center gap-1 ml-4">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span className="text-slate-600">Current</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-yellow-500">★</span>
          <span className="text-slate-600">Favorite</span>
        </div>
      </div>
    </div>
  )
}

export default ExplorationTreeView
