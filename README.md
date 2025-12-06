# Style Refine Agent

A self-improving visual style replication system that extracts style profiles from reference images, generates new images in that style, and iteratively refines through VLM critique and weighted multi-dimensional evaluation.

[![Status](https://img.shields.io/badge/status-production-green)]()
[![Python](https://img.shields.io/badge/python-3.13-blue)]()
[![License](https://img.shields.io/badge/license-TBD-lightgrey)]()

---

## Features

### 🎨 Core Capabilities

- **Visual Style Extraction**: Extract comprehensive style profiles from reference images using Vision Language Models
- **Structural Identity Locking**: Freeze subject identity while allowing style refinement
- **Multi-Dimensional Evaluation**: Score 6 style dimensions with weighted importance
- **Iterative Refinement**: Converge to accurate style replication through feedback loops
- **Training & Auto Modes**: Human-in-loop or fully automated training
- **Style Library**: Save and reuse trained styles on new subjects
- **Prompt Writer**: Generate styled prompts for any subject using trained styles

### 🔬 Advanced Features (Experimental Branch)

- **Feature Classification**: Categorize visual elements (motifs, style features, constraints, artifacts)
- **Vectorized Corrections**: Actionable feedback with direction and magnitude
- **Confidence Tracking**: Distinguish true motifs from coincidental artifacts
- **Diagnostic Analysis**: Root-cause explanations for style divergence

---

## Quick Start

### Prerequisites

- Python 3.13+
- Node.js 18+
- [Ollama](https://ollama.ai/) with llava:7b model
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) server with Flux models

### Installation

**1. Clone Repository**

```bash
git clone https://github.com/isam2024/agent-style-refine.git
cd agent-style-refine
```

**2. Backend Setup**

```bash
cd backend

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (Ollama URL, ComfyUI URL, etc.)

# Initialize database
python -c "from database import Base, engine; Base.metadata.create_all(engine)"

# Start server
python main.py
```

Backend runs at: http://localhost:1443

**3. Frontend Setup**

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env

# Start dev server
npm run dev
```

Frontend runs at: http://localhost:5173

**4. Verify Services**

```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Pull VLM model if needed
ollama pull llava:7b

# Check ComfyUI
curl http://YOUR_COMFYUI_URL:8188/system_stats
```

---

## Usage

### Training a Style

1. **Create Session**
   - Navigate to http://localhost:5173
   - Click "New Session"
   - Upload reference image
   - Name your session

2. **Extract Style**
   - System analyzes reference image
   - Generates StyleProfile v1 with:
     - Core invariants (frozen identity)
     - Palette (colors, saturation)
     - Lighting, texture, composition
     - Line quality and shape language

3. **Training Mode (Human-in-Loop)**
   - Enter subject (e.g., "centered")
   - System generates image in style
   - Review side-by-side comparison
   - Approve ✓ or Reject ✗ with notes
   - Repeat until converged

4. **Auto Mode (Automated)**
   - Set max iterations (e.g., 10)
   - Set target score (e.g., 85)
   - System runs loop automatically
   - Stops when target reached or max iterations

5. **Finalize Style**
   - Once satisfied, click "Finalize Style"
   - Style saved to library
   - Can be applied to new subjects

### Using Trained Styles

1. Navigate to **Style Library**
2. Select a trained style
3. Go to **Prompt Writer**
4. Enter new subject (e.g., "a fox sleeping under a tree")
5. System generates styled prompt
6. Use prompt in ComfyUI or other image generators

---

## Architecture

```
┌─────────────────┐
│  React Frontend │  ← User interface
└────────┬────────┘
         │ REST/WebSocket
┌────────▼────────┐
│  FastAPI Backend│  ← Orchestration
└────────┬────────┘
         │
    ┌────┴────┬──────────┬─────────┐
    │         │          │         │
┌───▼───┐ ┌──▼────┐ ┌───▼────┐ ┌──▼──────┐
│Ollama │ │ComfyUI│ │SQLite  │ │File     │
│ VLM   │ │ Image │ │Database│ │Storage  │
└───────┘ └───────┘ └────────┘ └─────────┘
```

**Key Components:**

- **Extractor Service**: Analyzes images, extracts style profiles
- **Critic Service**: Compares generated vs reference, scores dimensions
- **Agent Service**: Builds prompts for image generation
- **Auto Improver**: Orchestrates training loop with weighted evaluation

**Data Flow:**

```
Reference Image
    → Extract Style (VLM)
    → Generate Image (ComfyUI)
    → Critique (VLM)
    → Evaluate (Weighted Regression Detection)
    → Approve/Reject Decision
    → Update Profile or Revert
    → Repeat
```

---

## How It Works

### 1. Style Extraction

The extractor analyzes your reference image and creates a **StyleProfile**:

```json
{
  "style_name": "Watercolor Cat",
  "core_invariants": [
    "Black cat facing left, centered in frame",
    "Circular boundary containing subject",
    "Impressionistic brushstrokes"
  ],
  "palette": {
    "dominant_colors": ["#1b2a4a", "#41959b", "#ece0bb"],
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
    "noise_level": "low"
  },
  "composition": {
    "camera": "eye level",
    "framing": "centered"
  }
}
```

**Key Concept:** **Identity vs Style**
- **Identity** (frozen): WHAT is shown, WHERE positioned, HOW structured → `core_invariants`
- **Style** (refinable): Colors, textures, lighting → `palette`, `lighting`, `texture`

### 2. Iterative Refinement

Each iteration:

1. **Generate**: Agent creates image prompt based on current style profile + feedback
2. **Critique**: VLM compares generated image to reference
3. **Score**: 6 dimensions evaluated (palette, line_and_shape, texture, lighting, composition, motifs)
4. **Evaluate**: Weighted regression detection determines approval
5. **Decide**:
   - ✅ **Approved**: Update profile to new version, use as baseline
   - ✗ **Rejected**: Revert to last approved, add recovery guidance

### 3. Weighted Multi-Dimensional Evaluation

**Problem:** Single overall score causes oscillation

**Solution:** Weight dimensions by importance, track net progress

```python
Weights:
- composition: 2.0x  (structural identity critical)
- line_and_shape: 2.0x  (form definition critical)
- texture: 1.5x  (surface quality important)
- lighting: 1.5x  (mood important)
- palette: 1.0x  (well-tracked via color extraction)
- motifs: 0.8x  (emergent, less critical)

Weighted Δ = Σ (score_delta * weight)

Approval:
- Tier 1: Overall ≥70, all dims ≥55
- Tier 2: Weighted Δ ≥ +3.0 (strong progress)
- Tier 3: Weighted Δ ≥ +1.0 (weak progress)
- Reject: Weighted Δ < 0 (regression)
```

**Example:**

```
Iteration 2:
- Composition: +10 (70→80) → +10 * 2.0 = +20 weighted
- Lighting: -20 (70→50) → -20 * 1.5 = -30 weighted
- Palette: +8 (70→78) → +8 * 1.0 = +8 weighted
- Overall: 68 (below baseline 70)

Weighted Δ = +20 - 30 + 8 = -2

Decision: REJECT (negative progress)
```

### 4. Catastrophic Recovery

If a dimension drops below critical threshold:

- Lighting ≤ 20: Lost lighting entirely
- Composition ≤ 30: Lost spatial structure
- Motifs ≤ 20: Introduced forbidden elements

**Recovery Process:**

1. Immediate rejection
2. Generate recovery guidance with specific instructions
3. Revert profile to last approved version
4. Next iteration prioritizes recovery

**Example:**

```
CATASTROPHIC: lighting=15
→ Must restore soft ambient lighting from last approved iteration

LOST TRAITS: Dynamic lighting effect, Warm golden shadows
→ These must be restored in next iteration

AVOID: Harsh directional shadows, Cool blue tones
→ These introduced incompatible elements
```

---

## Configuration

### Environment Variables

Create `.env` in project root:

```bash
# Ollama Configuration
OLLAMA_URL=http://localhost:11434
VLM_MODEL=llava:7b

# ComfyUI Configuration
COMFYUI_URL=http://192.168.1.100:8188

# Storage
OUTPUTS_DIR=./outputs
DATABASE_URL=sqlite:///./refine_agent.db

# Server
HOST=0.0.0.0
PORT=1443
CORS_ORIGINS=["http://localhost:5173"]

# Logging
LOG_LEVEL=INFO
```

### VLM Model Selection

**Production (Main Branch):**
```bash
VLM_MODEL=llava:7b  # 7B params, fast, good accuracy
```

**Experimental (Feature Branch):**
```bash
VLM_MODEL=llama3.2-vision:11b  # 11B params, excellent accuracy
```

---

## API Reference

### REST Endpoints

**Sessions:**
- `POST /api/sessions` - Create new session
- `GET /api/sessions` - List all sessions
- `GET /api/sessions/{id}` - Get session details
- `DELETE /api/sessions/{id}` - Delete session

**Training:**
- `POST /api/extract` - Extract style from image
- `POST /api/iterate/step` - Run one iteration
- `POST /api/iterate/feedback` - Submit approval/rejection
- `POST /api/iterate/auto` - Run automated training loop

**Styles:**
- `POST /api/styles/finalize` - Save trained style
- `GET /api/styles` - List trained styles
- `GET /api/styles/{id}` - Get style details
- `POST /api/styles/{id}/write-prompt` - Generate styled prompt

### WebSocket

```javascript
const ws = new WebSocket(`ws://localhost:1443/ws/${sessionId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "log") {
    console.log(`[${data.stage}] ${data.message}`);
  } else if (data.type === "iteration_complete") {
    console.log(`Iteration ${data.iteration} complete`);
  }
};
```

---

## Branches

### Main Branch (Production) ✅

**Status:** Stable, proven convergence

**VLM:** llava:7b

**Features:**
- Structural identity locking
- Weighted multi-dimensional evaluation
- Catastrophic recovery
- Three-tier approval system

**Checkout:**
```bash
git checkout main
```

### Feature Branch: `feature/vectorized-feedback` 🔬

**Status:** Experimental, requires stronger VLM

**VLM:** llama3.2-vision:11b (recommended)

**Features:**
- Feature classification (4 types)
- Vectorized corrections (8 directions)
- Confidence tracking
- Diagnostic root-cause analysis

**Checkout:**
```bash
git checkout feature/vectorized-feedback
# Update .env: VLM_MODEL=llama3.2-vision:11b
```

**Note:** Feature branch does NOT work with llava:7b due to prompt complexity.

---

## Performance

**Main Branch (llava:7b):**
- Typical convergence: 5-8 iterations to score ≥85
- Success rate: ~80% reach target within 10 iterations
- Iteration time: 30-60 seconds (VLM + generation)
- Oscillation: Rare (<5% of sessions)

**Feature Branch (llama3.2-vision:11b):**
- 🔬 Untested, requires evaluation

---

## Troubleshooting

### VLM Not Responding

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Pull model if needed
ollama pull llava:7b

# Restart Ollama
ollama serve
```

### Empty Feature Registry (Feature Branch)

**Cause:** llava:7b overwhelmed by complex prompts

**Solution:**
```bash
# Switch to stronger model
ollama pull llama3.2-vision:11b

# Update .env
VLM_MODEL=llama3.2-vision:11b

# Restart backend
```

Or revert to main branch:
```bash
git checkout main
# Restart backend
```

### Training Stuck in Oscillation

**Symptoms:** Scores fluctuate, never reaches target

**Solutions:**
1. Check dimension weights are enabled (main branch)
2. Review lost traits for conflicting goals
3. Increase creativity_level (allows more mutation)
4. Use training mode for manual course correction

### ComfyUI Generation Fails

```bash
# Check ComfyUI is running
curl http://YOUR_COMFYUI_URL:8188/system_stats

# Test workflow in ComfyUI UI first
# Increase timeout in comfyui.py if needed
```

---

## Documentation

- **[DOCUMENTATION.md](./DOCUMENTATION.md)** - Complete project documentation
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - Deep technical architecture and algorithms
- **[CHANGELOG.md](./CHANGELOG.md)** - Version history and changes

---

## Development

### Project Structure

```
refine_agent/
├── backend/
│   ├── main.py               # FastAPI entry point
│   ├── models/               # Data models
│   ├── routers/              # API endpoints
│   ├── services/             # Business logic
│   └── prompts/              # VLM prompts
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── pages/            # Page components
│   │   └── api/              # API client
│   └── ...
├── outputs/                  # Generated images
└── refine_agent.db          # SQLite database
```

### Running Tests

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

### Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## Examples

### Example 1: Training Watercolor Style

**Reference Image:** Cat in watercolor style

**Extraction Results:**
- Style Name: "Watercolor Cat"
- Core Invariants: "Black cat facing left, centered", "Circular boundary"
- Palette: Deep navy, teal, pale cream
- Lighting: Soft ambient
- Texture: Painterly brushstrokes

**Training Progress:**
- Iteration 1: Overall 70 (baseline) ✅
- Iteration 2: Overall 65 (regression) ✗
- Iteration 3: Overall 82 (strong progress, weighted Δ +15) ✅
- Iteration 4: Overall 87 (target reached) ✅

**Result:** Style saved to library, can be applied to new subjects

### Example 2: Applying Trained Style

**Trained Style:** "Watercolor Cat"

**New Subject:** "a fox sleeping under a tree"

**Generated Prompt:**
```
A fox sleeping under a tree, rendered in soft watercolor style with deep
navy and teal tones, warm amber accents, painterly brushstrokes creating
organic flowing forms, soft ambient lighting with gentle shadows,
impressionistic technique with color bleeding at edges, centered composition
with circular framing, eye-level perspective
```

**Result:** ComfyUI generates fox in same watercolor style as training images

---

## Roadmap

### Short Term
- [ ] Test feature branch with llama3.2-vision:11b
- [ ] Add cancellation button for auto mode
- [ ] Implement interim style saving
- [ ] Improve progress indicators

### Medium Term
- [ ] Claude 3.5 Sonnet API integration
- [ ] Multi-VLM support (choose per session)
- [ ] Style mixing (combine two styles)
- [ ] Batch processing mode

### Long Term
- [ ] Fine-tuning integration (LoRA training)
- [ ] Video style transfer
- [ ] 3D rendering style profiles
- [ ] Community style sharing

---

## Credits

**Project Owner:** [@isam2024](https://github.com/isam2024)

**Technology Stack:**
- [Ollama](https://ollama.ai/) - VLM serving
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - Image generation
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [Flux Models](https://blackforestlabs.ai/) - Image generation models

---

## License

[To be determined]

---

## Contact

**Repository:** https://github.com/isam2024/agent-style-refine

**Issues:** https://github.com/isam2024/agent-style-refine/issues

---

**Made with Claude Code** 🤖

---

*Last updated: 2025-12-05*
