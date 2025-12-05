import {
  Session,
  SessionDetail,
  StyleProfile,
  IterationStepResult,
  CritiqueResult,
} from '../types';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
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
