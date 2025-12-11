export interface PaletteSchema {
  dominant_colors: string[];
  accents: string[];
  color_descriptions?: string[];
  saturation: string;
  value_range: string;
}

export interface LineShapeSchema {
  line_quality: string;
  shape_language: string;
  geometry_notes: string;
}

export interface TextureSchema {
  surface: string;
  noise_level: string;
  special_effects: string[];
}

export interface LightingSchema {
  lighting_type: string;
  shadows: string;
  highlights: string;
}

export interface CompositionSchema {
  camera: string;
  framing: string;
  negative_space_behavior: string;
}

export interface MotifsSchema {
  recurring_elements: string[];
  forbidden_elements: string[];
}

export interface StyleProfile {
  style_name: string;
  core_invariants: string[];
  palette: PaletteSchema;
  line_and_shape: LineShapeSchema;
  texture: TextureSchema;
  lighting: LightingSchema;
  composition: CompositionSchema;
  motifs: MotifsSchema;
  original_subject?: string | null;
  suggested_test_prompt?: string | null;
  image_description?: string | null;
}

export interface CritiqueResult {
  match_scores: Record<string, number>;
  preserved_traits: string[];
  lost_traits: string[];
  interesting_mutations: string[];
  updated_style_profile: StyleProfile;
}

export type SessionMode = 'training' | 'auto' | 'hypothesis';
export type SessionStatus = 'created' | 'extracting' | 'ready' | 'generating' | 'critiquing' | 'auto_improving' | 'hypothesis_exploring' | 'hypothesis_ready' | 'completed' | 'error';

export interface Session {
  id: string;
  name: string;
  mode: SessionMode;
  status: SessionStatus;
  created_at: string;
  current_style_version: number | null;
  iteration_count: number;
}

export interface SessionDetail extends Session {
  original_image_b64: string | null;
  style_profile: {
    version: number;
    profile: StyleProfile;
    created_at: string;
  } | null;
  iterations: Iteration[];
}

export interface Iteration {
  id: string;
  session_id: string;
  iteration_num: number;
  image_b64: string | null;
  prompt_used: string | null;
  scores: Record<string, number> | null;
  feedback: string | null;
  approved: boolean | null;
  created_at: string;
  critique_data: {
    preserved_traits: string[];
    lost_traits: string[];
    interesting_mutations: string[];
  } | null;
}

export interface IterationStepResult {
  iteration_id: string;
  iteration_num: number;
  image_b64: string;
  prompt_used: string;
  critique: {
    match_scores: Record<string, number>;
    preserved_traits: string[];
    lost_traits: string[];
    interesting_mutations: string[];
  };
  updated_profile: StyleProfile;
}

export interface WSMessage {
  event: string;
  data?: Record<string, unknown>;
  error?: string;
}

// ============================================================
// Trained Styles & Prompt Writer Types
// ============================================================

export interface StyleRules {
  always_include: string[];
  always_avoid: string[];
  technique_keywords: string[];
  mood_keywords: string[];
  emphasize: string[];
  de_emphasize: string[];
}

export interface TrainedStyleSummary {
  id: string;
  name: string;
  description: string | null;
  thumbnail_b64: string | null;
  iterations_trained: number;
  final_score: number | null;
  tags: string[];
  created_at: string;
}

export interface TrainedStyle extends TrainedStyleSummary {
  style_profile: StyleProfile;
  style_rules: StyleRules;
  source_session_id: string | null;
  updated_at: string;
}

export interface PromptWriteRequest {
  style_id: string;
  subject: string;
  additional_context?: string;
  include_negative?: boolean;
}

export interface PromptWriteResponse {
  positive_prompt: string;
  negative_prompt: string | null;
  style_name: string;
  prompt_breakdown: {
    subject: string;
    additional_context: string | null;
    technique: string[];
    palette: string[];
    lighting: {
      type: string;
      shadows: string;
      highlights: string;
    };
    texture: {
      surface: string;
      noise: string;
      effects: string[];
    };
    composition: {
      camera: string;
      framing: string;
      negative_space: string;
    };
    mood: string[];
    core_invariants: string[];
    always_include: string[];
    always_avoid: string[];
    emphasize: string[];
    de_emphasize: string[];
  } | null;
}

export interface PromptGenerateResponse {
  positive_prompt: string;
  negative_prompt: string | null;
  image_b64: string;
  style_name: string;
}

export interface GenerationHistoryResponse {
  id: string;
  style_id: string;
  style_name: string;
  subject: string;
  additional_context: string | null;
  positive_prompt: string;
  negative_prompt: string | null;
  image_b64: string | null;
  created_at: string;
}

// ============================================================
// Hypothesis Mode Types
// ============================================================

export interface HypothesisTest {
  test_subject: string;
  generated_image_path: string;
  scores: {
    visual_consistency: number;
    subject_independence: number;
  };
  timestamp: string;
}

export interface StyleHypothesis {
  id: string;
  interpretation: string;
  confidence_tier: string;
  profile: StyleProfile;
  confidence: number;
  supporting_evidence: string[];
  uncertain_aspects: string[];
  test_results: HypothesisTest[];
}

export interface HypothesisSet {
  session_id: string;
  hypotheses: StyleHypothesis[];
  selected_hypothesis_id: string | null;
  created_at: string;
}

export interface HypothesisExploreRequest {
  session_id: string;
  num_hypotheses?: number;
  test_subjects?: string[];
  auto_select?: boolean;
  auto_select_threshold?: number;
}

export interface HypothesisExploreResponse {
  session_id: string;
  hypotheses: StyleHypothesis[];
  selected_hypothesis: StyleHypothesis | null;
  auto_selected: boolean;
  test_images_generated: number;
}

export interface HypothesisSelectRequest {
  session_id: string;
  hypothesis_id: string;
}

// ============================================================
// Style Explorer Types
// ============================================================

export type MutationStrategy =
  // Core mutations
  | 'random_dimension'
  | 'what_if'
  | 'crossover'
  | 'inversion'
  | 'amplify'
  | 'diverge'
  | 'refine'
  // Style transformations
  | 'time_shift'
  | 'medium_swap'
  | 'mood_shift'
  | 'culture_shift'
  // Composition mutations
  | 'scale_warp'
  | 'remix'
  | 'constrain'
  | 'chaos'
  | 'decay'
  // Spatial mutations
  | 'topology_fold'
  | 'silhouette_shift'
  | 'perspective_drift'
  | 'axis_swap'
  // Physics mutations
  | 'physics_bend'
  | 'chromatic_gravity'
  | 'material_transmute'
  | 'temporal_exposure'
  // Pattern mutations
  | 'motif_splice'
  | 'rhythm_overlay'
  | 'harmonic_balance'
  | 'symmetry_break'
  // Density mutations
  | 'density_shift'
  | 'dimensional_shift'
  | 'micro_macro_swap'
  | 'essence_strip'
  // Narrative mutations
  | 'narrative_resonance'
  | 'archetype_mask'
  | 'anomaly_inject'
  | 'spectral_echo'
  // Environment mutations
  | 'climate_morph'
  | 'biome_shift'
  // Technical mutations
  | 'algorithmic_wrinkle'
  | 'symbolic_reduction';
export type ExplorationStatus = 'created' | 'exploring' | 'paused' | 'completed';

export interface ExplorationScores {
  novelty: number;
  coherence: number;
  interest: number;
  combined: number;
}

export interface ExplorationSnapshot {
  id: string;
  session_id: string;
  parent_id: string | null;
  style_profile: StyleProfile;
  generated_image_path: string;
  image_b64?: string;
  prompt_used: string | null;
  mutation_strategy: string;
  mutation_description: string;
  scores: ExplorationScores | null;
  depth: number;
  branch_name: string | null;
  is_favorite: boolean;
  user_notes: string | null;
  created_at: string;
}

export interface ExplorationSessionSummary {
  id: string;
  name: string;
  status: ExplorationStatus;
  total_snapshots: number;
  created_at: string;
}

export interface ExplorationSession extends ExplorationSessionSummary {
  reference_image_b64: string | null;
  base_style_profile: StyleProfile;
  preferred_strategies: string[];
  current_snapshot_id: string | null;
  snapshots: ExplorationSnapshot[];
  updated_at: string;
}

export interface ExplorationTreeNode {
  id: string;
  parent_id: string | null;
  depth: number;
  mutation_strategy: string;
  mutation_description: string;
  combined_score: number | null;
  is_favorite: boolean;
  children_count: number;
  image_path: string;
}

export interface ExplorationTree {
  session_id: string;
  root_nodes: ExplorationTreeNode[];
  all_nodes: ExplorationTreeNode[];
  total_nodes: number;
  max_depth: number;
  current_snapshot_id: string | null;
}

export interface AutoExploreResult {
  session_id: string;
  snapshots_created: number;
  snapshots: Array<{
    id: string;
    combined_score: number;
    mutation: string;
  }>;
  best_snapshot_id: string | null;
  best_score: number;
  stopped_reason: string;
}
