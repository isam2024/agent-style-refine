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
  mode: 'training' | 'auto' = 'training'
): Promise<Session> {
  return fetchJson<Session>(`${API_BASE}/sessions/`, {
    method: 'POST',
    body: JSON.stringify({ name, image_b64: imageB64, mode }),
  });
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  return fetchJson<SessionDetail>(`${API_BASE}/sessions/${sessionId}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetchJson(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' });
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
  includeNegative: boolean = true
): Promise<PromptWriteResponse> {
  return fetchJson<PromptWriteResponse>(`${API_BASE}/styles/write-prompt`, {
    method: 'POST',
    body: JSON.stringify({
      style_id: styleId,
      subject,
      additional_context: additionalContext,
      include_negative: includeNegative,
    }),
  });
}

export async function writeAndGenerate(
  styleId: string,
  subject: string,
  additionalContext?: string
): Promise<PromptGenerateResponse> {
  return fetchJson<PromptGenerateResponse>(`${API_BASE}/styles/write-and-generate`, {
    method: 'POST',
    timeout: LONG_TIMEOUT, // Image generation can take a long time
    body: JSON.stringify({
      style_id: styleId,
      subject,
      additional_context: additionalContext,
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
