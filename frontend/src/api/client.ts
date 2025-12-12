import {
  Session,
  SessionDetail,
  StyleProfile,
  IterationStepResult,
  CritiqueResult,
  TrainedStyleSummary,
  TrainedStyle,
  PromptWriteResponse,
  PromptGenerateResponse,
  GenerationHistoryResponse,
  HypothesisExploreResponse,
  HypothesisSet,
  SessionMode,
  ExplorationSessionSummary,
  ExplorationSession,
  ExplorationSnapshot,
  ExplorationTree,
  AutoExploreResult,
  MutationStrategy,
} from '../types';

const API_BASE = '/api';

// Default timeout for regular requests (30 seconds)
const DEFAULT_TIMEOUT = 30000;
// Extended timeout for long operations like iteration (30 minutes)
// Auto-improve can run many iterations sequentially, each taking 30-60 seconds
const LONG_TIMEOUT = 1800000;

async function fetchJson<T>(
  url: string,
  options?: RequestInit & { timeout?: number }
): Promise<T> {
  const { timeout = DEFAULT_TIMEOUT, ...fetchOptions } = options || {};

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeout / 1000} seconds`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

// Sessions
export async function listSessions(): Promise<Session[]> {
  return fetchJson<Session[]>(`${API_BASE}/sessions/`);
}

export async function createSession(
  name: string,
  imageB64: string,
  mode: SessionMode = 'training',
  styleHints?: string
): Promise<Session> {
  return fetchJson<Session>(`${API_BASE}/sessions/`, {
    method: 'POST',
    body: JSON.stringify({ name, image_b64: imageB64, mode, style_hints: styleHints }),
  });
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  return fetchJson<SessionDetail>(`${API_BASE}/sessions/${sessionId}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetchJson(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' });
}

export async function deleteAllSessions(): Promise<{ count: number; message: string }> {
  return fetchJson(`${API_BASE}/sessions/`, { method: 'DELETE' });
}

// Extraction
export async function extractStyle(sessionId: string): Promise<StyleProfile> {
  return fetchJson<StyleProfile>(`${API_BASE}/extract/`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
    timeout: LONG_TIMEOUT,
  });
}

export async function getStyleProfile(
  sessionId: string,
  version?: number
): Promise<{
  version: number;
  profile: StyleProfile;
  created_at: string;
  available_versions: number[];
}> {
  const params = version !== undefined ? `?version=${version}` : '';
  return fetchJson(`${API_BASE}/extract/${sessionId}/profile${params}`);
}

// Generation
export async function generateImage(
  sessionId: string,
  subject: string
): Promise<{ iteration_id: string; image_b64: string; prompt_used: string }> {
  return fetchJson(`${API_BASE}/generate/`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, subject }),
  });
}

export async function previewPrompt(
  sessionId: string,
  subject: string
): Promise<{ prompt: string }> {
  const params = new URLSearchParams({ session_id: sessionId, subject });
  return fetchJson(`${API_BASE}/generate/prompt-preview?${params}`);
}

// Critique
export async function critiqueIteration(
  sessionId: string,
  iterationId: string,
  creativityLevel: number = 50
): Promise<CritiqueResult> {
  return fetchJson<CritiqueResult>(`${API_BASE}/critique/`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      iteration_id: iterationId,
      creativity_level: creativityLevel,
    }),
  });
}

// Iteration
export async function runIterationStep(
  sessionId: string,
  subject: string,
  creativityLevel: number = 50
): Promise<IterationStepResult> {
  return fetchJson<IterationStepResult>(`${API_BASE}/iterate/step`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      subject,
      creativity_level: creativityLevel,
    }),
    timeout: LONG_TIMEOUT,
  });
}

export async function submitFeedback(
  iterationId: string,
  approved: boolean,
  notes?: string
): Promise<void> {
  await fetchJson(`${API_BASE}/iterate/feedback`, {
    method: 'POST',
    body: JSON.stringify({ iteration_id: iterationId, approved, notes }),
  });
}

export async function applyProfileUpdate(
  sessionId: string,
  updatedProfile: StyleProfile
): Promise<{ version: number; profile: StyleProfile }> {
  return fetchJson(`${API_BASE}/iterate/apply-update?session_id=${sessionId}`, {
    method: 'POST',
    body: JSON.stringify(updatedProfile),
  });
}

export async function runAutoMode(
  sessionId: string,
  subject: string,
  maxIterations: number = 5,
  targetScore: number = 80,
  creativityLevel: number = 50
): Promise<{
  iterations_run: number;
  results: Array<{ iteration_num: number; overall_score?: number; error?: string }>;
  final_score: number | null;
}> {
  return fetchJson(`${API_BASE}/iterate/auto`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      subject,
      max_iterations: maxIterations,
      target_score: targetScore,
      creativity_level: creativityLevel,
    }),
  });
}

export async function runAutoImprove(
  sessionId: string,
  subject: string,
  targetScore: number = 85,
  maxIterations: number = 10,
  creativityLevel: number = 50
): Promise<{
  iterations_run: number;
  approved_count: number;
  rejected_count: number;
  results: Array<{
    iteration_num: number;
    overall_score?: number;
    weak_dimensions?: string[];
    focused_areas?: string[];
    scores?: Record<string, number>;
    approved?: boolean;
    eval_reason?: string;
    error?: string;
  }>;
  final_score: number | null;
  best_score: number | null;
  target_reached: boolean;
}> {
  return fetchJson(`${API_BASE}/iterate/auto-improve`, {
    method: 'POST',
    timeout: LONG_TIMEOUT, // Can take a long time
    body: JSON.stringify({
      session_id: sessionId,
      subject,
      target_score: targetScore,
      max_iterations: maxIterations,
      creativity_level: creativityLevel,
    }),
  });
}

export async function stopAutoImprove(
  sessionId: string
): Promise<{
  session_id: string;
  message: string;
}> {
  return fetchJson(`${API_BASE}/iterate/stop`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
    }),
  });
}

// Health
export async function checkHealth(): Promise<{
  status: string;
  services: {
    vlm: { status: string; url: string };
    comfyui: { status: string; url: string };
  };
}> {
  return fetchJson('/health');
}

// WebSocket
export function createWebSocket(sessionId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return new WebSocket(`${protocol}//${host}/ws/${sessionId}`);
}

// ============================================================
// Trained Styles
// ============================================================

export async function listStyles(tag?: string): Promise<TrainedStyleSummary[]> {
  const params = tag ? `?tag=${encodeURIComponent(tag)}` : '';
  return fetchJson<TrainedStyleSummary[]>(`${API_BASE}/styles/${params}`);
}

export async function getStyle(styleId: string): Promise<TrainedStyle> {
  return fetchJson<TrainedStyle>(`${API_BASE}/styles/${styleId}`);
}

export async function finalizeStyle(
  sessionId: string,
  name: string,
  description?: string,
  tags?: string[]
): Promise<TrainedStyle> {
  return fetchJson<TrainedStyle>(`${API_BASE}/styles/finalize`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      name,
      description,
      tags: tags || [],
    }),
  });
}

export async function deleteStyle(styleId: string): Promise<void> {
  await fetchJson(`${API_BASE}/styles/${styleId}`, { method: 'DELETE' });
}

export async function deleteAllStyles(): Promise<{ count: number; message: string }> {
  return fetchJson(`${API_BASE}/styles/bulk/all`, { method: 'DELETE' });
}

export async function reextractStyle(sessionId: string): Promise<StyleProfile> {
  return fetchJson<StyleProfile>(`${API_BASE}/extract/reextract`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
    timeout: LONG_TIMEOUT,
  });
}

// ============================================================
// Prompt Writer
// ============================================================

export async function writePrompt(
  styleId: string,
  subject: string,
  additionalContext?: string,
  includeNegative: boolean = true,
  variationLevel: number = 50
): Promise<PromptWriteResponse> {
  return fetchJson<PromptWriteResponse>(`${API_BASE}/styles/write-prompt`, {
    method: 'POST',
    body: JSON.stringify({
      style_id: styleId,
      subject,
      additional_context: additionalContext,
      include_negative: includeNegative,
      variation_level: variationLevel,
    }),
  });
}

export async function writeAndGenerate(
  styleId: string,
  subject: string,
  additionalContext?: string,
  variationLevel: number = 50
): Promise<PromptGenerateResponse> {
  return fetchJson<PromptGenerateResponse>(`${API_BASE}/styles/write-and-generate`, {
    method: 'POST',
    timeout: LONG_TIMEOUT, // Image generation can take a long time
    body: JSON.stringify({
      style_id: styleId,
      subject,
      additional_context: additionalContext,
      variation_level: variationLevel,
    }),
  });
}

export async function batchWritePrompts(
  styleId: string,
  subjects: string[]
): Promise<PromptWriteResponse[]> {
  return fetchJson<PromptWriteResponse[]>(
    `${API_BASE}/styles/batch-write?style_id=${styleId}`,
    {
      method: 'POST',
      body: JSON.stringify(subjects),
    }
  );
}

export async function getGenerationHistory(
  styleId: string,
  limit: number = 50
): Promise<GenerationHistoryResponse[]> {
  return fetchJson<GenerationHistoryResponse[]>(
    `${API_BASE}/styles/${styleId}/history?limit=${limit}`,
    {
      method: 'GET',
    }
  );
}

export async function regenerateThumbnail(styleId: string): Promise<{ status: string; message: string }> {
  return fetchJson<{ status: string; message: string }>(
    `${API_BASE}/styles/${styleId}/regenerate-thumbnail`,
    {
      method: 'POST',
    }
  );
}

// ============================================================
// Hypothesis Mode API
// ============================================================

export async function getHypothesisSet(
  sessionId: string
): Promise<HypothesisSet> {
  return fetchJson<HypothesisSet>(
    `${API_BASE}/hypothesis/${sessionId}`
  );
}

export async function exploreHypotheses(
  sessionId: string,
  numHypotheses: number = 3,
  testSubjects: string[] = ['abstract pattern', 'landscape', 'portrait'],
  autoSelect: boolean = false,
  autoSelectThreshold: number = 0.7
): Promise<HypothesisExploreResponse> {
  return fetchJson<HypothesisExploreResponse>(
    `${API_BASE}/hypothesis/explore`,
    {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        num_hypotheses: numHypotheses,
        test_subjects: testSubjects,
        auto_select: autoSelect,
        auto_select_threshold: autoSelectThreshold,
      }),
      timeout: LONG_TIMEOUT, // Hypothesis exploration can take a long time
    }
  );
}

export async function selectHypothesis(
  sessionId: string,
  hypothesisId: string
): Promise<StyleProfile> {
  return fetchJson<StyleProfile>(
    `${API_BASE}/hypothesis/select`,
    {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        hypothesis_id: hypothesisId,
      }),
    }
  );
}

export async function stopHypothesisExploration(
  sessionId: string
): Promise<{ session_id: string; message: string }> {
  return fetchJson<{ session_id: string; message: string }>(
    `${API_BASE}/hypothesis/stop`,
    {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
      }),
    }
  );
}

export async function clearComfyUIQueue(): Promise<{ status: string; message: string }> {
  return fetchJson<{ status: string; message: string }>(
    '/health/comfyui/clear-queue',
    {
      method: 'POST',
    }
  );
}

// ============================================================
// Style Explorer API
// ============================================================

export async function listExplorations(): Promise<ExplorationSessionSummary[]> {
  return fetchJson<ExplorationSessionSummary[]>(`${API_BASE}/explorer/sessions`);
}

export async function createExploration(
  name: string,
  imageB64: string,
  preferredStrategies: MutationStrategy[] = ['random_dimension', 'what_if', 'amplify']
): Promise<ExplorationSession> {
  return fetchJson<ExplorationSession>(`${API_BASE}/explorer/sessions`, {
    method: 'POST',
    body: JSON.stringify({
      name,
      image_b64: imageB64,
      preferred_strategies: preferredStrategies,
    }),
    timeout: LONG_TIMEOUT,
  });
}

export async function getExploration(sessionId: string): Promise<ExplorationSession> {
  return fetchJson<ExplorationSession>(`${API_BASE}/explorer/sessions/${sessionId}`);
}

export async function deleteExploration(sessionId: string): Promise<void> {
  await fetchJson(`${API_BASE}/explorer/sessions/${sessionId}`, { method: 'DELETE' });
}

export async function exploreStep(
  sessionId: string,
  strategy?: MutationStrategy,
  parentSnapshotId?: string
): Promise<{ snapshot: ExplorationSnapshot; image_b64: string }> {
  return fetchJson(`${API_BASE}/explorer/sessions/${sessionId}/explore`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      strategy,
      parent_snapshot_id: parentSnapshotId,
    }),
    timeout: LONG_TIMEOUT,
  });
}

export async function autoExplore(
  sessionId: string,
  numSteps: number = 5,
  branchThreshold: number = 101,  // Default to 101 so it always runs all steps
  parentSnapshotId?: string,
  strategy?: string
): Promise<AutoExploreResult> {
  const params = new URLSearchParams();
  params.append('num_steps', numSteps.toString());
  params.append('branch_threshold', branchThreshold.toString());
  if (parentSnapshotId) {
    params.append('parent_snapshot_id', parentSnapshotId);
  }
  if (strategy) {
    params.append('strategy', strategy);
  }
  return fetchJson<AutoExploreResult>(
    `${API_BASE}/explorer/sessions/${sessionId}/auto-explore?${params.toString()}`,
    {
      method: 'POST',
      timeout: LONG_TIMEOUT * numSteps,  // Scale timeout with steps
    }
  );
}

export async function getExplorationTree(sessionId: string): Promise<ExplorationTree> {
  return fetchJson<ExplorationTree>(`${API_BASE}/explorer/sessions/${sessionId}/tree`);
}

export interface ChainExploreResult {
  session_id: string;
  snapshots_created: number;
  snapshots: Array<{ id: string; depth: number; combined_score: number; mutation: string }>;
  best_snapshot_id: string | null;
  best_score: number;
  final_depth: number;
}

export async function chainExplore(
  sessionId: string,
  numSteps: number = 5,
  parentSnapshotId?: string,
  strategy?: string
): Promise<ChainExploreResult> {
  const params = new URLSearchParams();
  params.append('num_steps', numSteps.toString());
  if (parentSnapshotId) {
    params.append('parent_snapshot_id', parentSnapshotId);
  }
  if (strategy) {
    params.append('strategy', strategy);
  }
  return fetchJson<ChainExploreResult>(
    `${API_BASE}/explorer/sessions/${sessionId}/chain-explore?${params.toString()}`,
    {
      method: 'POST',
      timeout: LONG_TIMEOUT * numSteps,
    }
  );
}

export interface BatchExploreResult {
  session_id: string;
  parent_snapshot_id: string | null;
  results: Array<{
    id?: string;
    strategy: string;
    mutation_description?: string;
    combined_score?: number;
    image_b64?: string;
    error?: string;
  }>;
  successful: number;
  failed: number;
}

export async function batchExplore(
  sessionId: string,
  strategies: MutationStrategy[],
  iterations: number = 1,
  parentSnapshotId?: string
): Promise<BatchExploreResult> {
  const params = new URLSearchParams();
  strategies.forEach(s => params.append('strategies', s));
  params.append('iterations', iterations.toString());
  if (parentSnapshotId) {
    params.append('parent_snapshot_id', parentSnapshotId);
  }
  return fetchJson<BatchExploreResult>(
    `${API_BASE}/explorer/sessions/${sessionId}/batch-explore?${params.toString()}`,
    {
      method: 'POST',
      timeout: LONG_TIMEOUT * iterations * strategies.length, // Scale timeout with work
    }
  );
}

export async function setCurrentSnapshot(sessionId: string, snapshotId: string): Promise<void> {
  await fetchJson(`${API_BASE}/explorer/sessions/${sessionId}/set-current?snapshot_id=${snapshotId}`, {
    method: 'POST',
  });
}

export async function resetExplorationStatus(sessionId: string): Promise<void> {
  await fetchJson(`${API_BASE}/explorer/sessions/${sessionId}/reset-status`, {
    method: 'POST',
  });
}

export async function updateExplorationStrategies(
  sessionId: string,
  strategies: MutationStrategy[]
): Promise<void> {
  await fetchJson(`${API_BASE}/explorer/sessions/${sessionId}/strategies`, {
    method: 'PATCH',
    body: JSON.stringify(strategies),
  });
}

export async function getFavoriteSnapshots(sessionId: string): Promise<ExplorationSnapshot[]> {
  return fetchJson<ExplorationSnapshot[]>(`${API_BASE}/explorer/sessions/${sessionId}/favorites`);
}

export async function getSnapshot(snapshotId: string): Promise<ExplorationSnapshot> {
  return fetchJson<ExplorationSnapshot>(`${API_BASE}/explorer/snapshots/${snapshotId}`);
}

export async function toggleSnapshotFavorite(snapshotId: string): Promise<{ id: string; is_favorite: boolean }> {
  return fetchJson(`${API_BASE}/explorer/snapshots/${snapshotId}/favorite`, {
    method: 'POST',
  });
}

export async function updateSnapshot(
  snapshotId: string,
  updates: { is_favorite?: boolean; user_notes?: string; branch_name?: string }
): Promise<void> {
  await fetchJson(`${API_BASE}/explorer/snapshots/${snapshotId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function snapshotToStyle(
  snapshotId: string,
  name: string,
  description?: string,
  tags: string[] = []
): Promise<{ id: string; name: string; created: boolean }> {
  return fetchJson(`${API_BASE}/explorer/snapshots/${snapshotId}/to-style`, {
    method: 'POST',
    body: JSON.stringify({ snapshot_id: snapshotId, name, description, tags }),
  });
}
