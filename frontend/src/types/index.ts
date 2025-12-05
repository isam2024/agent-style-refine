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

export type SessionMode = 'training' | 'auto';
export type SessionStatus = 'created' | 'extracting' | 'ready' | 'generating' | 'critiquing' | 'completed' | 'error';

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
