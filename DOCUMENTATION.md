# Style Refine Agent - Complete Documentation

**Version:** 2.0
**Last Updated:** 2025-12-05
**Status:** Production (main branch) + Experimental (feature/vectorized-feedback branch)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Core Concepts](#core-concepts)
4. [API Reference](#api-reference)
5. [Data Models](#data-models)
6. [Services](#services)
7. [Prompts System](#prompts-system)
8. [Evaluation System](#evaluation-system)
9. [Branches and Versions](#branches-and-versions)
10. [Configuration](#configuration)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)

---

## Project Overview

### Purpose

Style Refine Agent is a self-improving visual style replication system that:
- Extracts visual style profiles from reference images using Vision Language Models (VLM)
- Generates new images in that style using ComfyUI + Flux models
- Iteratively refines the style profile through VLM critique
- Converges to accurate style replication through multi-dimensional weighted evaluation

### Key Features

**Main Branch (Production):**
- ✅ Visual style extraction with structural identity locking
- ✅ Multi-dimensional style evaluation (6 dimensions: palette, line_and_shape, texture, lighting, composition, motifs)
- ✅ Weighted regression detection prevents oscillation
- ✅ Catastrophic failure recovery system
- ✅ Training vs Auto modes
- ✅ Real-time WebSocket progress updates
- ✅ Style library for trained styles
- ✅ Prompt writer for applying styles to new subjects

**Feature Branch (Experimental):**
- 🔬 Feature classification system (structural_motif, style_feature, scene_constraint, potential_coincidence)
- 🔬 Vectorized corrections with 8 direction types
- 🔬 Confidence tracking with logarithmic growth
- 🔬 Diagnostic root-cause analysis
- ⚠️ Requires more capable VLM (llama3.2-vision:11b recommended)

### Technology Stack

**Backend:**
- Python 3.13
- FastAPI (async web framework)
- SQLAlchemy (ORM with SQLite)
- Pydantic (data validation)
- WebSockets (real-time updates)

**Frontend:**
- React 18 + TypeScript
- Vite (build tool)
- TailwindCSS (styling)
- React Query (API state management)

**AI/ML:**
- Ollama (VLM serving)
  - Production: llava:7b (7 billion parameters)
  - Experimental: llama3.2-vision:11b (11 billion parameters)
- ComfyUI (image generation)
- Flux models (Stable Diffusion successor)

**Storage:**
- SQLite (sessions, iterations, profiles, styles)
- File system (images as PNG, base64 transport)

---

## Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          FRONTEND                                │
│  React + TypeScript + TailwindCSS                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Session    │  │    Style     │  │    Prompt    │         │
│  │   Manager    │  │   Library    │  │    Writer    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                  │                 │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          │  HTTP/WS         │  HTTP            │  HTTP
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼─────────────────┐
│                       BACKEND (FastAPI)                          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Sessions   │  │   Styles     │  │  Iterations  │         │
│  │   Router     │  │   Router     │  │    Router    │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                 │
│  ┌──────▼──────────────────▼──────────────────▼───────┐        │
│  │             SERVICE LAYER                           │        │
│  │                                                      │        │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │        │
│  │  │Extractor │  │  Critic  │  │  Agent   │         │        │
│  │  │ Service  │  │ Service  │  │ Service  │         │        │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘         │        │
│  │       │             │             │                │        │
│  │       │    ┌────────▼─────────────▼───────┐       │        │
│  │       │    │   Auto Improver Service       │       │        │
│  │       │    └────────────────────────────────┘      │        │
│  └───────┼──────────────────────────────────────────┘         │
│          │                                                      │
│  ┌───────▼────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  VLM Service   │  │   ComfyUI    │  │   Storage    │      │
│  │   (Ollama)     │  │   Service    │  │   Service    │      │
│  └────────────────┘  └──────────────┘  └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
    ┌──────────┐      ┌──────────┐      ┌──────────┐
    │  Ollama  │      │ ComfyUI  │      │  SQLite  │
    │  Server  │      │  Server  │      │ Database │
    └──────────┘      └──────────┘      └──────────┘
```

### Data Flow

#### 1. Style Extraction Flow

```
Original Image (base64)
    │
    ▼
Extractor Service
    │
    ├─> VLM Analysis (Ollama)
    │   └─> Structural prompt (10KB)
    │
    ├─> Color Extraction (PIL)
    │   └─> Dominant colors, accents, saturation
    │
    ▼
StyleProfile v1
    │
    ├─> Core Invariants (FROZEN identity)
    ├─> Palette (colors, saturation, value range)
    ├─> Lighting (type, shadows, highlights)
    ├─> Texture (surface, noise, effects)
    ├─> Composition (camera, framing, depth)
    ├─> Line & Shape (quality, language)
    └─> Motifs (recurring, forbidden)
```

#### 2. Iteration Loop Flow

```
StyleProfile (current version)
    │
    ▼
Agent Service
    │
    ├─> Build System Prompt
    │   ├─> Core invariants
    │   ├─> Full profile JSON
    │   ├─> Feedback history
    │   ├─> Lost traits (emphasize)
    │   └─> Preserved traits (maintain)
    │
    ├─> Generate Image Prompt
    │   └─> VLM generates prompt for ComfyUI
    │
    ▼
ComfyUI Service
    │
    ├─> Queue workflow
    ├─> Poll for completion
    │
    ▼
Generated Image (base64)
    │
    ▼
Critic Service
    │
    ├─> Compare original vs generated
    │   └─> VLM analyzes both images
    │
    ├─> Multi-dimensional scoring
    │   ├─> palette (0-100)
    │   ├─> line_and_shape (0-100)
    │   ├─> texture (0-100)
    │   ├─> lighting (0-100)
    │   ├─> composition (0-100)
    │   └─> motifs (0-100)
    │
    ├─> Trait analysis
    │   ├─> Preserved traits
    │   ├─> Lost traits
    │   └─> Interesting mutations
    │
    ▼
CritiqueResult
    │
    ▼
Auto Improver (Evaluation)
    │
    ├─> Weighted Regression Detection
    │   ├─> Dimension weights (composition=2x, lighting=1.5x, etc)
    │   └─> Net progress calculation
    │
    ├─> Approval Logic (Three Tiers)
    │   ├─> Tier 1: Meets quality targets (overall≥70, dims≥55)
    │   ├─> Tier 2: Strong weighted progress (≥+3.0)
    │   └─> Tier 3: Weak positive progress (≥+1.0)
    │
    ├─> APPROVED: Update profile to v(n+1)
    └─> REJECTED: Revert to last approved, add recovery guidance
```

#### 3. Style Application Flow (Prompt Writer)

```
TrainedStyle (finalized profile)
    │
    ├─> style_name
    ├─> style_profile (converged)
    ├─> final_scores
    └─> iteration_count
    │
    ▼
User provides new subject
    │
    ▼
Agent Service
    │
    ├─> Build prompt for new subject
    │   ├─> Apply style profile
    │   ├─> Insert subject
    │   └─> Maintain stylistic qualities
    │
    ▼
Styled Prompt (ready for ComfyUI)
```

---

## Core Concepts

### 1. Identity vs Style

**Critical Distinction:**

- **Identity (FROZEN):** WHAT is shown, WHERE it's positioned, HOW it's structured
  - Example: "Black cat facing left, centered in frame, whiskers extending horizontally"
  - Stored in: `core_invariants`, `original_subject`, `composition.structural_notes`, `suggested_test_prompt`
  - **Never changes during training**

- **Style (REFINABLE):** Colors, textures, lighting quality, rendering technique
  - Example: "Watercolor texture with radial color dispersion, soft ambient lighting"
  - Stored in: `palette`, `lighting`, `texture`, `line_and_shape`
  - **Can evolve through iterations**

### 2. Core Invariants

Core invariants are **hard locks** on structural identity:

```json
{
  "core_invariants": [
    "Black cat facing left, centered in frame",
    "Circular boundary containing the subject",
    "Background filled with swirling patterns",
    "Impressionistic style with bold brushstrokes"
  ]
}
```

**Rules:**
1. Set during initial extraction
2. **NEVER modified** by critic (frozen in prompt instructions)
3. Must be present in every generated image
4. Define the replication target

### 3. Multi-Dimensional Evaluation

Six dimensions scored independently (0-100):

| Dimension | Weight | Catastrophic Threshold | Description |
|-----------|--------|------------------------|-------------|
| **palette** | 1.0x | N/A | Color accuracy, saturation, value range |
| **line_and_shape** | 2.0x | N/A | Edge treatment, shape language, geometry |
| **texture** | 1.5x | N/A | Surface quality, noise level, effects |
| **lighting** | 1.5x | ≤20 | Lighting type, shadows, highlights |
| **composition** | 2.0x | ≤30 | Camera angle, framing, depth, layout |
| **motifs** | 0.8x | ≤20 | Recurring elements, style consistency |

**Weighted Progress Calculation:**

```python
weighted_delta = 0
for dim in dimensions:
    delta = current_score[dim] - baseline_score[dim]
    weight = dimension_weights[dim]
    weighted_delta += delta * weight

# Decision:
if weighted_delta >= 3.0:  # Strong progress
    APPROVE
elif weighted_delta >= 1.0:  # Weak progress
    APPROVE
elif weighted_delta < 0:  # Regression
    REJECT
```

### 4. Approval System (Three Tiers)

**Tier 1 - Quality Targets:**
- Overall score ≥ 70
- All dimensions ≥ 55
- **Result:** APPROVE (meets quality bar)

**Tier 2 - Strong Weighted Progress:**
- Weighted Δ ≥ +3.0 points
- Net improvement across dimensions
- **Result:** APPROVE (significant progress)

**Tier 3 - Weak Positive Progress:**
- Weighted Δ ≥ +1.0 points
- Small but positive improvement
- **Result:** APPROVE (incremental gain)

**Rejection:**
- Weighted Δ < 0 (regression)
- Catastrophic dimension failures
- **Result:** REJECT, revert to last approved version

### 5. Catastrophic Failure Recovery

**Catastrophic thresholds:**
- Lighting ≤ 20 (lost lighting entirely)
- Composition ≤ 30 (lost spatial structure)
- Motifs ≤ 20 (introduced forbidden elements)

**Recovery process:**
1. Detect catastrophic dimension(s)
2. Generate recovery guidance:
   ```
   CATASTROPHIC: lighting=15
   → Must restore soft ambient lighting from last approved iteration

   LOST TRAITS: Dynamic lighting effect, Warm golden shadows
   → These must be restored in next iteration

   AVOID: Harsh directional shadows, Cool blue tones
   → These introduced incompatible elements
   ```
3. Insert recovery guidance into next iteration's feedback
4. Revert style profile to last approved version
5. Next iteration focuses on recovery

### 6. Feedback History System

**Structure:**
```python
feedback_history = [
    {
        "iteration": 1,
        "approved": True,
        "notes": "PASS (Baseline): First iteration with overall 70",
        "scores": {"overall": 70, "palette": 75, ...},
        "preserved_traits": ["watercolor texture", "centered composition"],
        "lost_traits": []
    },
    {
        "iteration": 2,
        "approved": False,
        "notes": "FAIL: Weighted Δ=-85.0 | Regressed: lighting(-20), composition(-15)",
        "scores": {"overall": 52, "palette": 60, ...},
        "preserved_traits": ["color palette"],
        "lost_traits": ["soft ambient lighting", "circular boundary"],
        "recovery_guidance": "CATASTROPHIC: lighting=30. Must restore..."
    }
]
```

**Agent uses feedback to:**
- Emphasize frequently lost traits (counted across iterations)
- Preserve consistently maintained traits
- Avoid rejected approaches
- Focus on recovery after failures

### 7. Training vs Auto Modes

**Training Mode (Human-in-Loop):**
- Generate → Critique → Wait for approval
- User can approve, reject, or add notes
- Allows manual course correction
- Best for initial style development

**Auto Mode (Automated):**
- Runs N iterations without user input
- Automatic approval based on evaluation tiers
- Stops when: target score reached OR max iterations
- Best for refinement and convergence

---

## API Reference

### Base URL

```
http://localhost:1443/api
```

### WebSocket

```
ws://localhost:1443/ws/{session_id}
```

---

### Sessions Endpoints

#### `POST /api/sessions`

Create a new training session with original image.

**Request:**
```json
{
  "name": "Cat Watercolor Style",
  "mode": "training",  // or "auto"
  "original_image": "data:image/png;base64,iVBOR..."
}
```

**Response:**
```json
{
  "id": "uuid-string",
  "name": "Cat Watercolor Style",
  "mode": "training",
  "status": "created",
  "created_at": "2025-12-05T10:00:00Z"
}
```

#### `GET /api/sessions`

List all training sessions.

**Response:**
```json
[
  {
    "id": "uuid-1",
    "name": "Cat Watercolor Style",
    "mode": "training",
    "status": "active",
    "iteration_count": 5,
    "created_at": "2025-12-05T10:00:00Z"
  }
]
```

#### `GET /api/sessions/{session_id}`

Get session details with all iterations.

**Response:**
```json
{
  "id": "uuid-1",
  "name": "Cat Watercolor Style",
  "mode": "training",
  "status": "active",
  "style_profile": {
    "style_name": "Cat Watercolor",
    "core_invariants": [...],
    "palette": {...},
    "lighting": {...}
  },
  "iterations": [
    {
      "id": "iter-uuid-1",
      "iteration_num": 1,
      "image_url": "/outputs/uuid-1/iteration_001.png",
      "scores": {"overall": 70, ...},
      "approved": true
    }
  ]
}
```

#### `DELETE /api/sessions/{session_id}`

Delete session and all associated files.

---

### Extraction Endpoints

#### `POST /api/extract`

Extract style profile from session's original image.

**Request:**
```json
{
  "session_id": "uuid-string"
}
```

**Response:**
```json
{
  "style_profile": {
    "style_name": "Cat Watercolor",
    "core_invariants": [
      "Black cat facing left, centered in frame",
      "Circular boundary containing subject"
    ],
    "palette": {
      "dominant_colors": ["#1b2a4a", "#41959b", "#ece0bb"],
      "accents": ["#c0392b", "#f39c12"],
      "color_descriptions": ["deep navy blue", "teal", "pale cream"],
      "saturation": "medium",
      "value_range": "dark mids with bright highlights"
    },
    "lighting": {
      "lighting_type": "soft ambient",
      "shadows": "subtle, warm-toned",
      "highlights": "gentle, diffused"
    },
    "texture": {
      "surface": "painterly brushstrokes",
      "noise_level": "low",
      "special_effects": ["color bleeding", "soft edges"]
    },
    "composition": {
      "camera": "eye level",
      "framing": "centered",
      "depth": "subject in foreground, abstract background",
      "negative_space_behavior": "radial gradients",
      "structural_notes": "Circular framing with subject at center point"
    },
    "line_and_shape": {
      "line_quality": "soft, organic edges",
      "shape_language": "rounded, flowing forms",
      "geometry_notes": "Circular and arc motifs"
    },
    "motifs": {
      "recurring_elements": [],
      "forbidden_elements": []
    },
    "original_subject": "Black and white cat in playful pose",
    "suggested_test_prompt": "Black cat facing left, centered in circular frame, abstract swirling background"
  }
}
```

---

### Iteration Endpoints

#### `POST /api/iterate/step`

Run one full iteration (generate + critique).

**Request:**
```json
{
  "session_id": "uuid-string",
  "subject": "centered",  // What to generate (usually matches original)
  "creativity_level": 50  // 0-100, controls mutation allowance
}
```

**Response:**
```json
{
  "iteration_id": "iter-uuid-2",
  "iteration_num": 2,
  "image_b64": "base64-encoded-png",
  "image_url": "/outputs/uuid-1/iteration_002.png",
  "prompt_used": "Create an image featuring a stylized black cat...",
  "critique": {
    "match_scores": {
      "palette": 85,
      "line_and_shape": 90,
      "texture": 75,
      "lighting": 80,
      "composition": 85,
      "motifs": 70,
      "overall": 82
    },
    "preserved_traits": [
      "Soft ambient lighting",
      "Circular boundary composition"
    ],
    "lost_traits": [
      "Bold brushstroke energy"
    ],
    "interesting_mutations": [
      "Enhanced color dispersion in background"
    ],
    "updated_style_profile": {...}
  }
}
```

#### `POST /api/iterate/feedback`

Submit user feedback for an iteration (training mode).

**Request:**
```json
{
  "iteration_id": "iter-uuid-2",
  "approved": true,
  "notes": "Great improvement on composition!"
}
```

**Response:**
```json
{
  "success": true,
  "profile_updated": true,
  "new_profile_version": 3
}
```

#### `POST /api/iterate/auto`

Run automated training loop.

**Request:**
```json
{
  "session_id": "uuid-string",
  "subject": "centered",
  "max_iterations": 10,
  "target_score": 85,
  "creativity_level": 50
}
```

**Response:**
```json
{
  "completed_iterations": 8,
  "final_score": 87,
  "final_profile_version": 9,
  "convergence_reason": "target_score_reached",
  "iterations": [
    {
      "iteration_num": 1,
      "scores": {...},
      "approved": true,
      "decision": "PASS (Baseline)"
    },
    ...
  ]
}
```

**WebSocket Events:**
```json
{
  "type": "iteration_start",
  "iteration": 2
}
{
  "type": "log",
  "stage": "generate",
  "level": "info",
  "message": "Building style agent prompt..."
}
{
  "type": "iteration_complete",
  "iteration": 2,
  "approved": true,
  "scores": {...}
}
```

---

### Styles Endpoints (Trained Styles Library)

#### `POST /api/styles/finalize`

Finalize a session's style profile for reuse.

**Request:**
```json
{
  "session_id": "uuid-string",
  "style_name": "Watercolor Cat Style",
  "description": "Soft impressionistic watercolor with vibrant colors"
}
```

**Response:**
```json
{
  "id": "style-uuid-1",
  "style_name": "Watercolor Cat Style",
  "description": "Soft impressionistic watercolor with vibrant colors",
  "style_profile": {...},
  "iteration_count": 8,
  "final_scores": {
    "overall": 87,
    "palette": 90,
    ...
  },
  "created_at": "2025-12-05T11:00:00Z"
}
```

#### `GET /api/styles`

List all trained styles.

**Query Parameters:**
- `search` (optional): Filter by name/description
- `min_score` (optional): Minimum overall score

**Response:**
```json
[
  {
    "id": "style-uuid-1",
    "style_name": "Watercolor Cat Style",
    "description": "Soft impressionistic watercolor",
    "final_scores": {"overall": 87},
    "created_at": "2025-12-05T11:00:00Z",
    "sample_image_url": "/outputs/uuid-1/iteration_008.png"
  }
]
```

#### `GET /api/styles/{style_id}`

Get detailed style information.

#### `POST /api/styles/{style_id}/write-prompt`

Generate a styled prompt for a new subject.

**Request:**
```json
{
  "subject": "a fox sleeping under a tree",
  "emphasis": ["color palette", "soft lighting"]  // optional
}
```

**Response:**
```json
{
  "styled_prompt": "A fox sleeping under a tree, rendered in soft watercolor style with deep navy and teal tones, warm amber accents, painterly brushstrokes creating organic flowing forms, soft ambient lighting with gentle shadows, impressionistic technique with color bleeding at edges, centered composition with circular framing, eye-level perspective"
}
```

#### `POST /api/styles/batch-prompts`

Generate multiple styled prompts.

**Request:**
```json
{
  "style_id": "style-uuid-1",
  "subjects": [
    "a fox sleeping under a tree",
    "a mountain landscape at sunset",
    "a coffee cup on a wooden table"
  ]
}
```

**Response:**
```json
{
  "prompts": [
    {
      "subject": "a fox sleeping under a tree",
      "styled_prompt": "..."
    },
    ...
  ]
}
```

---

## Data Models

### StyleProfile

Complete representation of visual style.

```python
class StyleProfile(BaseModel):
    style_name: str
    core_invariants: list[str]  # FROZEN identity constraints
    palette: PaletteSchema
    line_and_shape: LineShapeSchema
    texture: TextureSchema
    lighting: LightingSchema
    composition: CompositionSchema
    motifs: MotifsSchema
    original_subject: str  # FROZEN literal identity
    suggested_test_prompt: str  # FROZEN replication baseline
    image_description: str | None = None

    # Feature branch only:
    feature_registry: FeatureRegistry | None = None
```

### PaletteSchema

```python
class PaletteSchema(BaseModel):
    dominant_colors: list[str]  # ["#1b2a4a", "#41959b", ...]
    accents: list[str]  # ["#c0392b", "#f39c12"]
    color_descriptions: list[str]  # ["deep navy blue", "teal", ...]
    saturation: str  # "low" | "medium" | "high" | "medium-high" | "medium-low"
    value_range: str  # "dark mids with bright highlights"
```

### LightingSchema

```python
class LightingSchema(BaseModel):
    lighting_type: str  # "soft ambient" | "directional" | "backlit" | ...
    shadows: str  # Description of shadow quality and color
    highlights: str  # Description of highlight treatment
```

### TextureSchema

```python
class TextureSchema(BaseModel):
    surface: str  # "painterly brushstrokes" | "smooth" | "rough" | ...
    noise_level: str  # "low" | "medium" | "high"
    special_effects: list[str]  # ["color bleeding", "soft edges", ...]
```

### CompositionSchema

```python
class CompositionSchema(BaseModel):
    camera: str  # "eye level" | "low angle" | "high angle" | ...
    framing: str  # "centered" | "rule of thirds" | "asymmetric" | ...
    depth: str  # Description of spatial layers
    negative_space_behavior: str | None = None
    structural_notes: str | None = None  # FROZEN spatial identity
```

### LineShapeSchema

```python
class LineShapeSchema(BaseModel):
    line_quality: str  # "soft edges" | "hard edges" | "mixed" | ...
    shape_language: str  # "organic" | "geometric" | "angular" | ...
    geometry_notes: str | None = None
```

### MotifsSchema

```python
class MotifsSchema(BaseModel):
    recurring_elements: list[str]  # Discovered through iterations
    forbidden_elements: list[str]  # Incompatible elements to avoid
```

### CritiqueResult

```python
class CritiqueResult(BaseModel):
    match_scores: dict[str, int]  # {"palette": 85, "overall": 82, ...}
    preserved_traits: list[str]
    lost_traits: list[str]
    interesting_mutations: list[str]
    updated_style_profile: dict  # Updated StyleProfile as dict

    # Feature branch only:
    corrections: list[VectorizedCorrection] | None = None
```

### Session (Database Model)

```python
class Session(Base):
    id: str  # UUID
    name: str
    mode: str  # "training" | "auto"
    status: str  # "created" | "extracting" | "active" | "completed"
    original_image_path: str
    created_at: datetime

    # Relationships:
    style_profiles: list[StyleProfile]  # Versioned profiles
    iterations: list[Iteration]
```

### Iteration (Database Model)

```python
class Iteration(Base):
    id: str  # UUID
    session_id: str  # Foreign key
    iteration_num: int
    image_path: str
    prompt_used: str
    scores_json: str  # JSON serialized scores
    preserved_traits: str  # JSON list
    lost_traits: str  # JSON list
    approved: bool | None  # None = pending, True = approved, False = rejected
    feedback_notes: str | None
    created_at: datetime
```

### TrainedStyle (Database Model)

```python
class TrainedStyle(Base):
    id: str  # UUID
    session_id: str  # Source session
    style_name: str
    description: str | None
    style_profile_json: str  # Final converged StyleProfile
    iteration_count: int
    final_scores_json: str  # Final dimension scores
    sample_image_path: str  # Best iteration image
    created_at: datetime
```

---

## Services

### VLM Service (`backend/services/vlm.py`)

Wrapper for Ollama Vision Language Model API.

**Methods:**

```python
class VLMService:
    async def analyze(
        self,
        prompt: str,
        images: list[str],  # Base64 encoded images
    ) -> str:
        """
        Analyze images with VLM.

        Args:
            prompt: System/user prompt
            images: List of base64 image strings

        Returns:
            VLM text response
        """

    async def generate_text(
        self,
        prompt: str,
        system: str | None = None,
    ) -> str:
        """
        Generate text without images.

        Args:
            prompt: User prompt
            system: Optional system prompt

        Returns:
            VLM text response
        """
```

**Configuration:**
- `OLLAMA_URL`: http://localhost:11434
- `VLM_MODEL`: llava:7b (main) or llama3.2-vision:11b (feature)

### Extractor Service (`backend/services/extractor.py`)

Extracts style profile from reference image.

**Methods:**

```python
class StyleExtractor:
    async def extract_style(
        self,
        image_b64: str,
        session_id: str | None = None,
    ) -> StyleProfile:
        """
        Extract style profile from image.

        Process:
        1. Load extraction prompt (extractor.md)
        2. Send image + prompt to VLM
        3. Parse JSON response
        4. Extract colors with PIL
        5. Build mechanical replication baseline
        6. Validate schema

        Returns:
            StyleProfile with frozen identity + refinable style
        """
```

**Key Features:**
- **Structural identity locking** via core_invariants
- **Mechanical baseline construction** (no VLM hallucination)
- **Pixel-accurate color extraction** with PIL quantization
- **Feature classification** (feature branch only)

### Critic Service (`backend/services/critic.py`)

Critiques generated images against reference style.

**Methods:**

```python
class StyleCritic:
    async def critique(
        self,
        original_image_b64: str,
        generated_image_b64: str,
        style_profile: StyleProfile,
        creativity_level: int = 50,
        session_id: str | None = None,
    ) -> CritiqueResult:
        """
        Critique generated image vs original reference.

        Process:
        1. Extract colors from both images (PIL)
        2. Compare color palettes
        3. Load critic prompt (critic.md)
        4. Send both images + profile to VLM
        5. Parse multi-dimensional scores
        6. Extract trait analysis
        7. Update feature confidence (feature branch)
        8. Return critique with updated profile

        Returns:
            CritiqueResult with scores, traits, updated profile
        """
```

**Key Features:**
- **Two-image comparison** (original + generated)
- **Pixel-level color analysis** for palette scoring
- **Profile preservation rules** (frozen fields copied exactly)
- **Type coercion** for VLM response errors

### Agent Service (`backend/services/agent.py`)

Builds prompts for the style agent (image prompt generator).

**Methods:**

```python
class StyleAgent:
    def build_system_prompt(
        self,
        style_profile: StyleProfile,
        feedback_history: list[dict] | None = None,
        latest_corrections: list[dict] | None = None,
    ) -> str:
        """
        Build system prompt for style agent.

        Includes:
        - Core invariants (MUST preserve)
        - Full style profile JSON
        - Feedback history with approval status
        - Frequently lost traits (emphasis list)
        - Preserved traits (what works)
        - Vectorized corrections (feature branch)

        Returns:
            Complete system prompt for generator
        """

    async def generate_image_prompt(
        self,
        style_profile: StyleProfile,
        subject: str,
        feedback_history: list[dict] | None = None,
        latest_corrections: list[dict] | None = None,
        session_id: str | None = None,
    ) -> str:
        """
        Generate image generation prompt.

        Process:
        1. Build system prompt with profile + feedback
        2. Send subject + system to VLM
        3. Clean response (remove markdown)
        4. Return styled prompt ready for ComfyUI

        Returns:
            Styled prompt string
        """
```

**Key Features:**
- **Feedback aggregation** (lost trait counting, preservation tracking)
- **Recovery guidance** injection after rejections
- **Corrections formatting** (feature branch)

### Auto Improver Service (`backend/services/auto_improver.py`)

Orchestrates automated training loops with evaluation logic.

**Methods:**

```python
class AutoImprover:
    async def run_focused_iteration(
        self,
        session_id: str,
        subject: str,
        style_profile: StyleProfile,
        original_image_b64: str,
        feedback_history: list[dict],
        previous_scores: dict[str, int] | None = None,
        previous_corrections: list[dict] | None = None,
        creativity_level: int = 50,
        training_insights: dict | None = None,
        log_fn: Callable | None = None,
    ) -> dict:
        """
        Run one iteration with evaluation.

        Process:
        1. Generate image prompt (Agent)
        2. Generate image (ComfyUI)
        3. Critique image (Critic)
        4. Evaluate with weighted regression detection
        5. Decide approval (three-tier system)
        6. Generate recovery guidance if rejected

        Returns:
            Iteration result with decision
        """

    async def run_auto_loop(
        self,
        session_id: str,
        subject: str,
        max_iterations: int = 10,
        target_score: int = 85,
        creativity_level: int = 50,
    ) -> dict:
        """
        Run automated training loop.

        Stops when:
        - Target score reached
        - Max iterations completed
        - User cancellation (future)

        Returns:
            Complete training report
        """
```

**Evaluation Logic:**

```python
# Weighted regression detection
DIMENSION_WEIGHTS = {
    "composition": 2.0,      # Structure most important
    "line_and_shape": 2.0,   # Form definition critical
    "texture": 1.5,          # Surface quality
    "lighting": 1.5,         # Mood and depth
    "palette": 1.0,          # Colors (already well-tracked)
    "motifs": 0.8,           # Style consistency
}

# Calculate weighted delta
weighted_delta = sum(
    (current[dim] - baseline[dim]) * DIMENSION_WEIGHTS[dim]
    for dim in dimensions
)

# Three-tier approval
if meets_quality_targets(overall >= 70, all_dims >= 55):
    return APPROVE_TIER_1
elif weighted_delta >= 3.0:
    return APPROVE_TIER_2_STRONG
elif weighted_delta >= 1.0:
    return APPROVE_TIER_3_WEAK
else:
    return REJECT
```

**Catastrophic Detection:**

```python
CATASTROPHIC_THRESHOLDS = {
    "lighting": 20,      # Lost lighting entirely
    "composition": 30,   # Lost spatial structure
    "motifs": 20,        # Introduced forbidden elements
}

if any(score <= threshold):
    generate_recovery_guidance()
    revert_to_last_approved_profile()
```

### ComfyUI Service (`backend/services/comfyui.py`)

Interface to ComfyUI image generation server.

**Methods:**

```python
class ComfyUIService:
    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        workflow: dict | None = None,
    ) -> str:
        """
        Generate image with ComfyUI.

        Process:
        1. Build workflow JSON (or use provided)
        2. Queue workflow via API
        3. Poll for completion
        4. Download result image
        5. Convert to base64

        Returns:
            Base64 encoded PNG
        """
```

### Storage Service (`backend/services/storage.py`)

File I/O for images and sessions.

**Methods:**

```python
class StorageService:
    def save_image(
        self,
        session_id: str,
        image_b64: str,
        filename: str,
    ) -> Path:
        """Save base64 image to session directory."""

    def load_image(self, path: Path) -> str:
        """Load image and return as base64."""

    def ensure_session_dir(self, session_id: str) -> Path:
        """Create session output directory."""

    def delete_session(self, session_id: str) -> None:
        """Delete session directory and all files."""
```

---

## Prompts System

### Prompt Architecture

Prompts are stored as Markdown files in `backend/prompts/`:

```
backend/prompts/
├── extractor.md      # Style extraction (identity locking)
├── critic.md         # Style critique (comparison + scoring)
└── generator.md      # Image prompt generation (style agent)
```

Each prompt uses **template substitution**:

```python
template = prompt_path.read_text()
filled = template.replace("{{VARIABLE}}", value)
```

### Extractor Prompt (`extractor.md`)

**Purpose:** Extract structural identity + refinable style from reference image.

**Key Sections:**

1. **Schema Definition** (JSON output format)
2. **Color Extraction Guide** (hex value guidance)
3. **Identity Lock Protocol**
   - Identity vs Style distinction
   - Core invariants = structural locks
   - Motifs start empty (discovered through iteration)
4. **Feature Classification** (feature branch only)
   - structural_motif, style_feature, scene_constraint, potential_coincidence

**Template Variables:** None (static prompt)

**Main Branch Length:** ~6,500 characters
**Feature Branch Length:** ~10,400 characters

**Critical Instructions:**

```markdown
## IDENTITY vs STYLE - Know the Difference:

- IDENTITY (frozen, never changes): WHAT subject, WHERE positioned, HOW structured
- STYLE (refinable, can evolve): colors, textures, lighting quality, rendering technique

## Core Invariants = STRUCTURAL IDENTITY LOCKS:

Example GOOD: "Black cat facing left, centered in frame, whiskers extending horizontally"
Example BAD: "Vivid colors with flowing organic shapes" ← This is style, not identity

## Mechanical Baseline Construction:

The suggested_test_prompt field will be mechanically reconstructed from structural fields
to prevent VLM hallucination of style adjectives.
```

### Critic Prompt (`critic.md`)

**Purpose:** Compare generated image to reference, score dimensions, update profile.

**Key Sections:**

1. **Two-Image Instructions** (IMAGE 1 = original, IMAGE 2 = generated)
2. **Scoring Guidelines** (0-100 per dimension)
3. **Profile Update Rules**
   - FROZEN fields (core_invariants, structural_notes, original_subject)
   - REFINABLE fields (palette, lighting, texture)
   - Conservative edits only
4. **Motifs Discovery Protocol** (only add if seen in BOTH images)
5. **Vectorized Corrections** (feature branch only)

**Template Variables:**

- `{{CREATIVITY_LEVEL}}`: 0-100, controls mutation allowance
- `{{STYLE_PROFILE}}`: Full StyleProfile JSON
- `{{COLOR_ANALYSIS}}`: Pixel-level color comparison text
- `{{IMAGE_DESCRIPTION}}`: Natural language description of original

**Main Branch Length:** ~8,200 characters
**Feature Branch Length:** ~10,300 characters

**Critical Instructions:**

```markdown
## PROFILE UPDATE RULES (CRITICAL - FOLLOW EXACTLY):

1. **CORE INVARIANTS ARE FROZEN - DO NOT MODIFY:**
   - You MUST copy core_invariants EXACTLY from current to updated profile
   - Do NOT refine, reword, or delete any
   - These are identity constraints, not suggestions

2. **WHAT YOU CAN UPDATE (Refinable Style):**
   - Palette: color descriptions, saturation levels
   - Lighting: lighting_type, shadow/highlight descriptions
   - Texture: surface quality, noise level, effects

3. **WHAT YOU CANNOT UPDATE (Frozen Identity):**
   - core_invariants (copy exactly)
   - composition.structural_notes (spatial identity)
   - original_subject (literal identity)
   - suggested_test_prompt (replication baseline)
```

### Generator Prompt (`generator.md`)

**Purpose:** Build system prompt for style agent that generates image prompts.

**Key Sections:**

1. **Core Invariants** (MUST preserve in every prompt)
2. **Full Style Profile** (JSON reference)
3. **Feedback History** (learning from iterations)
4. **Recovery Guidance** (after rejections)
5. **Directional Corrections** (feature branch only)

**Template Variables:**

- `{{STYLE_NAME}}`: Name of the style
- `{{CORE_INVARIANTS}}`: Bulleted list of invariants
- `{{STYLE_PROFILE}}`: Full StyleProfile JSON
- `{{FEEDBACK_HISTORY}}`: Formatted feedback with approval status
- `{{EMPHASIZE_TRAITS}}`: Frequently lost traits (need emphasis)
- `{{PRESERVE_TRAITS}}`: Consistently preserved traits (what works)
- `{{CORRECTIONS}}`: Vectorized corrections (feature branch)

**Main Branch Length:** ~4,800 characters
**Feature Branch Length:** ~5,700 characters

**Critical Instructions:**

```markdown
## FEEDBACK FROM PREVIOUS ITERATIONS:

**How to Use Feedback:**
- ✅ **Approved iterations**: Build on what worked
- ❌ **Rejected iterations (RECOVERY NEEDED)**: Critical recovery instructions
  - **LOST TRAITS**: Must be restored in your next prompt
  - **CATASTROPHIC failures**: Specific dimensions that broke - restore from approved
  - **Action**: Revert to last approved characteristics, then fix specific failures

**Recovery Priority**: If feedback includes "RECOVERY NEEDED", prioritize fixing
those specific issues over everything else.

## GOAL - ACCURACY OVER CREATIVITY:

Your goal is to recreate the original image as accurately as possible, not to be
creative or add variations. Match the structure, content, and style exactly.
```

---

## Evaluation System

### Weighted Multi-Dimensional Scoring

**Purpose:** Prevent oscillation by detecting net progress across dimensions instead of just overall score changes.

**Problem Solved:**

Old system (single overall score):
```
Iteration 1: Overall 70 → APPROVE
Iteration 2: Overall 68 → REJECT (regression)
Iteration 3: Overall 69 → REJECT (still below baseline)
Result: Stuck, can't recover
```

New system (weighted dimensions):
```
Iteration 1: Overall 70 → APPROVE
Iteration 2: Overall 68, but composition +10, palette +8, lighting -20
  → Weighted Δ = (+10×2.0) + (+8×1.0) + (-20×1.5) = 20 + 8 - 30 = -2.0
  → REJECT (negative progress)
Iteration 3: Overall 72, composition +5, lighting +15 (recovering)
  → Weighted Δ = (+5×2.0) + (+15×1.5) = 10 + 22.5 = +32.5
  → APPROVE (strong progress despite lower overall)
Result: Converges by building on partial improvements
```

### Dimension Weights

Weights prioritize critical dimensions:

```python
DIMENSION_WEIGHTS = {
    "composition": 2.0,      # Spatial structure is critical
    "line_and_shape": 2.0,   # Form definition is critical
    "texture": 1.5,          # Surface quality is important
    "lighting": 1.5,         # Mood and depth are important
    "palette": 1.0,          # Already well-tracked via color extraction
    "motifs": 0.8,           # Style consistency, less critical than structure
}
```

**Rationale:**
- Composition and line_and_shape define **structural identity** → highest weight
- Texture and lighting affect **perception and mood** → medium-high weight
- Palette is **accurately measured** via color extraction → standard weight
- Motifs are **emergent and soft** → lower weight

### Approval Decision Tree

```
                    ┌─────────────────────────┐
                    │ Evaluate Iteration      │
                    └──────────┬──────────────┘
                               │
                  ┌────────────▼────────────┐
                  │ Meets Quality Targets?  │
                  │ (overall≥70, dims≥55)   │
                  └────┬──────────────┬──────┘
                       │ YES          │ NO
                       │              │
             ┌─────────▼─────┐       │
             │ TIER 1         │       │
             │ APPROVE        │       │
             │ (Quality Bar)  │       │
             └────────────────┘       │
                                      │
                         ┌────────────▼───────────────┐
                         │ Weighted Δ ≥ +3.0?        │
                         │ (Strong Progress)          │
                         └────┬───────────────┬───────┘
                              │ YES           │ NO
                              │               │
                    ┌─────────▼─────┐        │
                    │ TIER 2         │        │
                    │ APPROVE        │        │
                    │ (Strong Prog)  │        │
                    └────────────────┘        │
                                              │
                                 ┌────────────▼───────────────┐
                                 │ Weighted Δ ≥ +1.0?        │
                                 │ (Weak Progress)            │
                                 └────┬───────────────┬───────┘
                                      │ YES           │ NO
                                      │               │
                            ┌─────────▼─────┐        │
                            │ TIER 3         │        │
                            │ APPROVE        │        │
                            │ (Weak Prog)    │        │
                            └────────────────┘        │
                                                      │
                                         ┌────────────▼───────────────┐
                                         │ Weighted Δ < 0             │
                                         │ (Regression)               │
                                         └────┬───────────────────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │ Check Catastrophic  │
                                    │ Failures            │
                                    └─────────┬───────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │ REJECT              │
                                    │ - Revert profile    │
                                    │ - Add recovery      │
                                    │   guidance          │
                                    └─────────────────────┘
```

### Catastrophic Failure Handling

**Definition:** A dimension score drops below a critical threshold, indicating total loss of that aspect.

**Thresholds:**

| Dimension | Threshold | Meaning |
|-----------|-----------|---------|
| lighting | ≤ 20 | Lost lighting entirely (e.g., harsh shadows replaced soft ambient) |
| composition | ≤ 30 | Lost spatial structure (e.g., centered → off-frame) |
| motifs | ≤ 20 | Introduced forbidden elements (e.g., photorealistic in ink drawing) |

**Recovery Process:**

1. **Detection:**
   ```python
   catastrophic_dims = [
       dim for dim, score in scores.items()
       if dim in CATASTROPHIC_THRESHOLDS
       and score <= CATASTROPHIC_THRESHOLDS[dim]
   ]
   ```

2. **Generate Recovery Guidance:**
   ```python
   recovery_guidance = f"""
   CATASTROPHIC: {dim}={score}
   → Must restore from last approved iteration

   LOST TRAITS: {', '.join(lost_traits)}
   → These must be restored in next iteration

   AVOID: {', '.join(interesting_mutations)}
   → These introduced incompatible elements
   """
   ```

3. **Inject into Feedback History:**
   ```python
   feedback_history.append({
       "iteration": n,
       "approved": False,
       "notes": f"FAIL: {decision_reason}",
       "recovery_guidance": recovery_guidance
   })
   ```

4. **Revert Profile:**
   ```python
   # Don't save updated_style_profile
   # Keep using last approved version
   current_profile = last_approved_profile
   ```

5. **Next Iteration Sees Recovery Instructions:**
   ```markdown
   ## FEEDBACK FROM PREVIOUS ITERATIONS:

   Iteration 5: ❌ REJECTED - RECOVERY NEEDED

   CATASTROPHIC: lighting=15
   → Must restore soft ambient lighting from last approved iteration

   LOST TRAITS: Dynamic lighting effect, Warm golden shadows
   → These must be restored in next iteration
   ```

---

## Branches and Versions

### Main Branch (Production)

**Status:** ✅ Stable, proven convergence

**Key Features:**
- Structural identity locking (core invariants frozen)
- Multi-dimensional weighted evaluation
- Catastrophic failure recovery
- Three-tier approval system
- Mechanical baseline construction
- Training and auto modes
- Style library and prompt writer

**Prompt Complexity:**
- Extractor: ~6,500 chars
- Critic: ~8,200 chars
- Generator: ~4,800 chars

**VLM Compatibility:** ✅ llava:7b (works well)

**Performance:**
- Typical convergence: 5-8 iterations to score ≥85
- Success rate: ~80% reach target within 10 iterations
- Oscillation: Rare (weighted evaluation prevents)

**Best Use Cases:**
- Production training with llava:7b
- Users who need reliable convergence
- Systems with limited VLM capability

### Feature Branch: `feature/vectorized-feedback`

**Status:** 🔬 Experimental, needs stronger VLM

**Additional Features:**
- Feature classification (4 types: structural_motif, style_feature, scene_constraint, potential_coincidence)
- Confidence tracking with logarithmic growth
- Vectorized corrections (8 direction types)
- Diagnostic root-cause analysis
- Spatial hints for corrections
- High-priority correction filtering

**Prompt Complexity:**
- Extractor: ~10,400 chars (+60% complexity)
- Critic: ~10,300 chars (+26% complexity)
- Generator: ~5,700 chars (+19% complexity)

**VLM Compatibility:**
- ❌ llava:7b (overwhelmed by complex instructions)
- ✅ llama3.2-vision:11b (recommended)
- ✅ Claude 3.5 Sonnet (via API, untested)

**Performance with llava:7b:**
- Feature registry empty (failed to classify)
- No corrections generated
- Consistent regression (weighted Δ negative)
- Never converged in 10 iterations

**Performance with llama3.2-vision:11b:**
- 🔬 Untested (needs evaluation)

**Best Use Cases:**
- Future upgrade when using stronger VLM
- Research into diagnostic feedback systems
- Advanced users who need fine-grained control

### Data Model Differences

**Main Branch:**
```python
class StyleProfile(BaseModel):
    style_name: str
    core_invariants: list[str]
    palette: PaletteSchema
    # ... other fields
```

**Feature Branch:**
```python
class FeatureType(str, Enum):
    STRUCTURAL_MOTIF = "structural_motif"
    STYLE_FEATURE = "style_feature"
    SCENE_CONSTRAINT = "scene_constraint"
    POTENTIAL_COINCIDENCE = "potential_coincidence"

class ClassifiedFeature(BaseModel):
    feature_id: str
    feature_type: FeatureType
    description: str
    source_dimension: str
    confidence: float  # 0.0-1.0
    persistence_count: int

class FeatureRegistry(BaseModel):
    features: dict[str, ClassifiedFeature]

class StyleProfile(BaseModel):
    # ... main branch fields
    feature_registry: FeatureRegistry | None = None  # NEW

class CorrectionDirection(str, Enum):
    MAINTAIN = "maintain"
    REINFORCE = "reinforce"
    REDUCE = "reduce"
    ELIMINATE = "eliminate"
    # ... 4 more types

class VectorizedCorrection(BaseModel):
    feature_id: str
    current_state: str
    target_state: str
    direction: CorrectionDirection
    magnitude: float  # 0.0-1.0
    spatial_hint: str | None
    diagnostic: str | None  # Root cause
    confidence: float

class CritiqueResult(BaseModel):
    # ... main branch fields
    corrections: list[VectorizedCorrection] | None = None  # NEW
```

### Migration Path

**To upgrade from main → feature branch:**

1. Switch to stronger VLM:
   ```bash
   # Update .env
   VLM_MODEL=llama3.2-vision:11b
   ```

2. Checkout feature branch:
   ```bash
   git checkout feature/vectorized-feedback
   ```

3. Restart backend:
   ```bash
   kill <backend-pid>
   cd backend && python main.py
   ```

4. Test with new session (existing sessions incompatible)

**To downgrade from feature → main:**

1. Checkout main:
   ```bash
   git checkout main
   ```

2. Update VLM (optional):
   ```bash
   # .env
   VLM_MODEL=llava:7b
   ```

3. Restart backend

4. Existing sessions will work (feature fields ignored)

---

## Configuration

### Environment Variables

Create `.env` file in project root:

```bash
# Ollama Configuration
OLLAMA_URL=http://localhost:11434
VLM_MODEL=llava:7b  # or llama3.2-vision:11b for feature branch

# ComfyUI Configuration
COMFYUI_URL=http://192.168.1.100:8188  # Your ComfyUI server

# Storage
OUTPUTS_DIR=./outputs
DATABASE_URL=sqlite:///./refine_agent.db

# Server
HOST=0.0.0.0
PORT=1443
CORS_ORIGINS=["http://localhost:5173"]  # Frontend dev server

# Logging
LOG_LEVEL=INFO
```

### Backend Configuration (`backend/config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Ollama
    ollama_url: str = "http://localhost:11434"
    vlm_model: str = "llava:7b"

    # ComfyUI
    comfyui_url: str

    # Storage
    outputs_dir: Path = Path("./outputs")
    database_url: str = "sqlite:///./refine_agent.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 1443
    cors_origins: list[str] = ["http://localhost:5173"]

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
```

### Frontend Configuration (`frontend/.env`)

```bash
VITE_API_URL=http://localhost:1443
VITE_WS_URL=ws://localhost:1443
```

---

## Deployment

### Development Setup

**Prerequisites:**
- Python 3.13+
- Node.js 18+
- Ollama installed with llava:7b model
- ComfyUI running with Flux models

**Backend:**

```bash
cd backend

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your settings

# Run migrations (creates database)
python -c "from database import Base, engine; Base.metadata.create_all(engine)"

# Start server
python main.py
```

**Frontend:**

```bash
cd frontend

# Install dependencies
npm install

# Create .env file
cp .env.example .env

# Start dev server
npm run dev
```

Access at: http://localhost:5173

### Production Deployment

**Backend (systemd service):**

```ini
# /etc/systemd/system/refine-agent.service
[Unit]
Description=Style Refine Agent Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/refine_agent/backend
Environment="PATH=/opt/refine_agent/backend/venv/bin"
ExecStart=/opt/refine_agent/backend/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**Frontend (nginx):**

```nginx
# /etc/nginx/sites-available/refine-agent
server {
    listen 80;
    server_name refine.example.com;

    root /opt/refine_agent/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:1443;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://localhost:1443;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
}
```

### Docker Deployment

**Dockerfile (backend):**

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 1443
CMD ["python", "main.py"]
```

**docker-compose.yml:**

```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "1443:1443"
    environment:
      - OLLAMA_URL=http://ollama:11434
      - COMFYUI_URL=http://comfyui:8188
      - DATABASE_URL=sqlite:////data/refine_agent.db
    volumes:
      - ./outputs:/app/outputs
      - ./data:/data
    depends_on:
      - ollama

  frontend:
    image: node:18
    working_dir: /app
    command: sh -c "npm install && npm run build && npx serve -s dist"
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama

volumes:
  ollama-data:
```

---

## Troubleshooting

### Common Issues

#### 1. VLM Not Responding

**Symptoms:**
- Extraction/critique hangs indefinitely
- Error: "Connection refused to Ollama"

**Solutions:**

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check model is pulled
ollama list

# Pull model if missing
ollama pull llava:7b

# Restart Ollama
ollama serve
```

#### 2. Empty Feature Registry (Feature Branch)

**Symptoms:**
- `feature_registry.features: {}`
- No corrections generated
- Consistent regression

**Root Cause:** llava:7b overwhelmed by complex prompts

**Solutions:**

1. **Switch to llama3.2-vision:11b:**
   ```bash
   ollama pull llama3.2-vision:11b
   # Update .env: VLM_MODEL=llama3.2-vision:11b
   ```

2. **Or revert to main branch:**
   ```bash
   git checkout main
   # Restart backend
   ```

#### 3. Pydantic Validation Errors

**Symptoms:**
```
ValidationError: updated_style_profile.feature_registry.features
Input should be a valid dictionary [type=dict_type, input_value=[], input_type=list]
```

**Root Cause:** VLM returns `[]` instead of `{}`

**Solution:** Already fixed in feature branch (e348b64):
```python
# critic.py line 418-425
if "features" in registry and isinstance(registry["features"], list):
    logger.warning(f"VLM returned features as list, converting to dict")
    registry["features"] = {}
```

#### 4. Training Stuck in Oscillation

**Symptoms:**
- Scores fluctuate: 70 → 65 → 68 → 63
- Never reaches target
- Weighted Δ alternates positive/negative

**Solutions:**

1. **Check dimension weights** (should be enabled on main branch)
2. **Review lost traits:** May be conflicting goals
3. **Increase creativity_level:** Allows more mutation
4. **Manual intervention:** Approve partial improvements in training mode

#### 5. ComfyUI Generation Fails

**Symptoms:**
- Error: "Image generation failed"
- Timeout waiting for ComfyUI

**Solutions:**

```bash
# Check ComfyUI is running
curl http://192.168.1.100:8188/system_stats

# Check workflow is valid
# Test workflow in ComfyUI UI first

# Increase timeout in comfyui.py
TIMEOUT = 600  # 10 minutes
```

#### 6. Style Drift Despite Approvals

**Symptoms:**
- Early iterations look good
- Later iterations drift away
- Core invariants not preserved

**Solutions:**

1. **Check core_invariants in profile:**
   ```bash
   # Should have 3-5 structural locks
   # Example: "Black cat facing left, centered"
   ```

2. **Review critic prompt:**
   ```bash
   # Ensure FROZEN FIELDS section present
   # Critic must copy core_invariants exactly
   ```

3. **Check generator feedback:**
   ```bash
   # Lost traits should be counted and emphasized
   # Generator should see "EMPHASIZE: X (lost 3x)"
   ```

#### 7. Frontend WebSocket Disconnects

**Symptoms:**
- Progress stops updating
- Console error: "WebSocket closed"

**Solutions:**

```javascript
// Check WebSocket URL matches backend
const wsUrl = `ws://localhost:1443/ws/${sessionId}`;

// Add reconnection logic
socket.onclose = () => {
  setTimeout(() => connectWebSocket(), 1000);
};
```

#### 8. Database Locked Errors

**Symptoms:**
- Error: "database is locked"
- Occurs during concurrent iterations

**Solutions:**

```bash
# Increase SQLite timeout
# database.py
engine = create_engine(
    DATABASE_URL,
    connect_args={"timeout": 30}  # 30 seconds
)

# Or switch to PostgreSQL for production
```

### Debug Logs

**Enable verbose logging:**

```python
# .env
LOG_LEVEL=DEBUG

# Or in code
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check auto_improve_debug.txt:**

```bash
# Each session has detailed log
cat outputs/{session_id}/auto_improve_debug.txt

# Look for:
# - Weighted deltas
# - Decision analysis
# - Recovery guidance
# - Score progression
```

### Performance Optimization

**Slow VLM responses:**

```bash
# Check Ollama GPU usage
nvidia-smi

# Increase context size
ollama run llava:7b --context 8192

# Use quantized model
ollama pull llava:7b-q4  # 4-bit quantization
```

**Slow image generation:**

```bash
# Check ComfyUI queue
curl http://192.168.1.100:8188/queue

# Clear stuck jobs
curl -X POST http://192.168.1.100:8188/interrupt

# Use faster Flux model
# flux-schnell instead of flux-dev
```

---

## Appendix

### Glossary

- **Core Invariants:** Frozen structural constraints defining image identity
- **Style Profile:** Complete representation of visual style (colors, lighting, texture, composition)
- **Critique:** VLM analysis comparing generated image to reference
- **Weighted Delta:** Sum of dimension score changes multiplied by importance weights
- **Catastrophic Failure:** Dimension score below critical threshold (indicates total loss)
- **Feature Classification:** Categorizing visual elements (feature branch)
- **Vectorized Correction:** Actionable directive with direction + magnitude (feature branch)
- **Mechanical Baseline:** Programmatically constructed prompt (no VLM hallucination)

### References

**Related Technologies:**
- Ollama: https://ollama.ai/
- ComfyUI: https://github.com/comfyanonymous/ComfyUI
- Flux Models: https://blackforestlabs.ai/
- FastAPI: https://fastapi.tiangolo.com/
- Pydantic: https://docs.pydantic.dev/

**Research Papers:**
- "DreamBooth: Fine Tuning Text-to-Image Diffusion Models" (Ruiz et al., 2022)
- "Prompt-to-Prompt Image Editing with Cross Attention Control" (Hertz et al., 2022)

### Changelog

**v2.0 - 2025-12-05**
- ✅ Feature branch: Vectorized feedback system
- ✅ Feature branch: Feature classification with confidence tracking
- ✅ Feature branch: Diagnostic root-cause analysis
- ⚠️ Feature branch requires llama3.2-vision:11b (not llava:7b)

**v1.5 - 2025-12-04**
- ✅ Weighted multi-dimensional evaluation
- ✅ Catastrophic failure recovery system
- ✅ Three-tier approval logic
- ✅ Recovery guidance generation

**v1.0 - 2025-12-03**
- ✅ Initial release
- ✅ Style extraction with identity locking
- ✅ Iterative refinement loop
- ✅ Training and auto modes
- ✅ Style library and prompt writer

---

## Contact & Support

**Repository:** https://github.com/isam2024/agent-style-refine

**Issues:** https://github.com/isam2024/agent-style-refine/issues

**Branches:**
- `main`: Production stable
- `feature/vectorized-feedback`: Experimental advanced features

---

*Documentation last updated: 2025-12-05*
*Main branch version: 1.5*
*Feature branch version: 2.0-experimental*
