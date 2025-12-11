# Style Explorer Mode - Design Document

## Overview

A new mode that **diverges** rather than converges. Starting from a reference style, each iteration intentionally mutates, exaggerates, and explores variations - treating the style space as a creative landscape to explore rather than a target to match.

## Core Concept

```
TRAINER MODE (current):          EXPLORER MODE (new):

Reference ◄──── Generated        Reference ────► Variation 1 ────► Variation 1.1
    │              │                                  │
    │   minimize   │                                  ├──► Variation 1.2
    │   distance   │                                  │
    ▼              │             Variation 2 ────► Variation 2.1
  Converge         │                  │
                                      └──► Variation 2.2

                                 Variation 3 ────► ...

Goal: Match reference            Goal: Maximize interesting divergence
Metric: Style similarity         Metric: Novelty + Coherence
Output: One refined style        Output: Tree of variations to explore
```

## Key Differences from Trainer

| Aspect | Trainer Mode | Explorer Mode |
|--------|--------------|---------------|
| Direction | Converge to reference | Diverge from reference |
| Evaluation | "How close is this?" | "How interesting is this?" |
| Mutations | Discouraged (regression) | Encouraged (exploration) |
| Output | Single refined profile | Gallery of variations |
| Iterations | Stop when converged | Continue indefinitely |
| Saving | Final result only | Every iteration saved |

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                      STYLE EXPLORER MODE                        │
└─────────────────────────────────────────────────────────────────┘

                    ┌──────────────┐
                    │   Starting   │
                    │    Point     │
                    └──────┬───────┘
                           │
            Can be: • Reference image
                    • Existing style profile
                    • Previous exploration snapshot
                           │
                           ▼
              ┌────────────────────────┐
              │   Extract Base Style   │
              │   (if from image)      │
              └────────────┬───────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────────┐
    │                   EXPLORATION LOOP                        │
    │                                                           │
    │   ┌─────────────────────────────────────────────────┐    │
    │   │  1. SELECT MUTATION STRATEGY                     │    │
    │   │                                                  │    │
    │   │  • Random dimension push (pick dim, go extreme)  │    │
    │   │  • VLM-guided "what if?" (ask for wild idea)     │    │
    │   │  • Crossover (blend with random other style)     │    │
    │   │  • Inversion (flip a key characteristic)         │    │
    │   │  • Amplification (exaggerate existing traits)    │    │
    │   └─────────────────────┬───────────────────────────┘    │
    │                         │                                 │
    │                         ▼                                 │
    │   ┌─────────────────────────────────────────────────┐    │
    │   │  2. MUTATE STYLE PROFILE                        │    │
    │   │                                                  │    │
    │   │  Apply selected mutation to create               │    │
    │   │  divergent_profile = mutate(current_profile)     │    │
    │   └─────────────────────┬───────────────────────────┘    │
    │                         │                                 │
    │                         ▼                                 │
    │   ┌─────────────────────────────────────────────────┐    │
    │   │  3. GENERATE EXPLORATION IMAGE                  │    │
    │   │                                                  │    │
    │   │  Use same subject as reference (or user choice)  │    │
    │   │  to see the mutation effect clearly              │    │
    │   └─────────────────────┬───────────────────────────┘    │
    │                         │                                 │
    │                         ▼                                 │
    │   ┌─────────────────────────────────────────────────┐    │
    │   │  4. EVALUATE EXPLORATION                        │    │
    │   │                                                  │    │
    │   │  Score on:                                       │    │
    │   │  • Novelty: How different from parent?          │    │
    │   │  • Coherence: Is it still a valid style?        │    │
    │   │  • Interest: VLM "is this visually striking?"   │    │
    │   │                                                  │    │
    │   │  exploration_score = novelty × coherence × interest │ │
    │   └─────────────────────┬───────────────────────────┘    │
    │                         │                                 │
    │                         ▼                                 │
    │   ┌─────────────────────────────────────────────────┐    │
    │   │  5. SAVE SNAPSHOT                               │    │
    │   │                                                  │    │
    │   │  Store:                                          │    │
    │   │  • Mutated profile                               │    │
    │   │  • Generated image                               │    │
    │   │  • Mutation description                          │    │
    │   │  • Scores (novelty, coherence, interest)        │    │
    │   │  • Parent reference (for tree structure)        │    │
    │   └─────────────────────┬───────────────────────────┘    │
    │                         │                                 │
    │                         ▼                                 │
    │                  ┌─────────────┐                          │
    │                  │  Continue?  │                          │
    │                  └──────┬──────┘                          │
    │                         │                                 │
    │         ┌───────────────┼───────────────┐                 │
    │         │               │               │                 │
    │         ▼               ▼               ▼                 │
    │   [Continue from   [Branch from    [Stop and             │
    │    this variation]  saved snapshot]  browse gallery]     │
    │         │               │                                 │
    │         └───────────────┘                                 │
    │                │                                          │
    │                ▼                                          │
    │         (loop back)                                       │
    └───────────────────────────────────────────────────────────┘
```

## Mutation Strategies

### 1. Random Dimension Push
Pick a random style dimension and push it toward an extreme.

```python
DIMENSION_EXTREMES = {
    "palette.saturation": ["completely desaturated/monochrome", "hypersaturated/neon"],
    "palette.contrast": ["flat/no contrast", "extreme high contrast"],
    "palette.temperature": ["freezing cold blues", "burning hot oranges"],
    "line_and_shape.edges": ["razor sharp vector edges", "completely dissolved/blurry"],
    "line_and_shape.complexity": ["minimal single shape", "infinitely complex fractal"],
    "texture.surface": ["glass smooth perfect", "extremely rough/distressed"],
    "texture.noise": ["clinical clean", "heavy grain/static"],
    "lighting.intensity": ["pitch black shadows", "blown out overexposed"],
    "lighting.direction": ["flat frontal", "extreme side lighting"],
    "composition.density": ["single element vast empty space", "horror vacui packed full"],
    "composition.symmetry": ["perfect mathematical symmetry", "chaotic asymmetry"],
}

def random_dimension_push(profile: StyleProfile) -> StyleProfile:
    dimension = random.choice(list(DIMENSION_EXTREMES.keys()))
    extreme = random.choice(DIMENSION_EXTREMES[dimension])
    return apply_mutation(profile, dimension, extreme)
```

### 2. VLM-Guided "What If?"
Ask the VLM to suggest a wild creative mutation.

```python
WHAT_IF_PROMPT = """
Looking at this style profile, suggest ONE wild "what if?" variation.

Current style: {profile_summary}

Think of unexpected combinations like:
- "What if this watercolor style used only neon colors?"
- "What if this minimal design became maximally ornate?"
- "What if the lighting came from inside the objects?"

Suggest a specific, dramatic change that would create something visually striking.
Output format:
{
  "mutation": "description of the change",
  "target_field": "which profile field to modify",
  "new_value": "the new extreme value"
}
"""
```

### 3. Style Crossover
Blend the current style with a randomly selected "donor" style.

```python
DONOR_STYLES = [
    "1970s psychedelic poster",
    "Japanese woodblock print",
    "Soviet constructivist propaganda",
    "Art nouveau organic curves",
    "Brutalist concrete architecture",
    "Vaporwave aesthetic",
    "Medieval illuminated manuscript",
    "Glitch art corruption",
    "Infrared photography",
    "Blueprint technical drawing",
]

async def style_crossover(profile: StyleProfile) -> StyleProfile:
    donor = random.choice(DONOR_STYLES)

    prompt = f"""
    Blend these two styles into a hybrid:

    Style A (current): {profile.summary()}
    Style B (donor): {donor}

    Create a merged style that takes the most distinctive element
    from each. Output the modified style profile.
    """

    return await vlm_mutate(profile, prompt)
```

### 4. Characteristic Inversion
Flip a key characteristic to its opposite.

```python
INVERSIONS = {
    "warm colors": "cold colors",
    "organic shapes": "geometric shapes",
    "soft lighting": "harsh lighting",
    "busy composition": "minimal composition",
    "realistic rendering": "abstract rendering",
    "smooth textures": "rough textures",
    "high saturation": "desaturated",
    "dark mood": "bright mood",
}

def invert_characteristic(profile: StyleProfile) -> StyleProfile:
    # Find a characteristic present in the profile
    for original, inverted in INVERSIONS.items():
        if original in profile.summary().lower():
            return apply_inversion(profile, original, inverted)

    # Random inversion if no match found
    original, inverted = random.choice(list(INVERSIONS.items()))
    return apply_inversion(profile, original, inverted)
```

### 5. Trait Amplification
Take an existing trait and push it to absurd extremes.

```python
async def amplify_trait(profile: StyleProfile) -> StyleProfile:
    prompt = f"""
    This style has these characteristics:
    {profile.summary()}

    Pick the MOST DISTINCTIVE trait and amplify it to an extreme.

    Examples:
    - If slightly desaturated → completely monochrome
    - If somewhat geometric → pure mathematical shapes only
    - If soft shadows → shadows that glow and pulse

    Push it past realistic into stylized/surreal territory.
    """

    return await vlm_mutate(profile, prompt)
```

## Exploration Scoring

Instead of "how close to reference?" we score "how interesting?"

```python
@dataclass
class ExplorationScore:
    novelty: float      # 0-100: How different from parent?
    coherence: float    # 0-100: Is it still a valid, consistent style?
    interest: float     # 0-100: Is it visually striking/compelling?

    @property
    def combined(self) -> float:
        # Novelty and interest matter most, coherence is a sanity check
        return (self.novelty * 0.4 + self.interest * 0.4 + self.coherence * 0.2)


async def score_exploration(
    parent_image: str,
    child_image: str,
    mutation_description: str
) -> ExplorationScore:

    # Novelty: How different is this from the parent?
    novelty_prompt = """
    Compare these two images. Score from 0-100 how DIFFERENT the second
    image's style is from the first.

    0 = Identical style
    50 = Noticeably different
    100 = Completely transformed

    Output just the number.
    """
    novelty = await vlm_score(novelty_prompt, [parent_image, child_image])

    # Coherence: Is it still a valid style (not random noise)?
    coherence_prompt = """
    Look at this image. Score from 0-100 how COHERENT the visual style is.

    0 = Random noise, no consistent style
    50 = Some style elements but inconsistent
    100 = Clear, consistent, intentional style

    Output just the number.
    """
    coherence = await vlm_score(coherence_prompt, [child_image])

    # Interest: Is it visually compelling?
    interest_prompt = """
    Score this image from 0-100 on visual INTEREST.

    0 = Boring, generic, forgettable
    50 = Moderately interesting
    100 = Striking, memorable, would stop scrolling to look

    Output just the number.
    """
    interest = await vlm_score(interest_prompt, [child_image])

    return ExplorationScore(novelty=novelty, coherence=coherence, interest=interest)
```

## Data Model

### ExplorationSnapshot

```python
@dataclass
class ExplorationSnapshot:
    id: str                          # Unique ID
    session_id: str                  # Parent exploration session
    parent_id: str | None            # Previous snapshot (None if root)

    # Content
    style_profile: StyleProfile      # The mutated profile
    generated_image_path: str        # Path to generated image
    prompt_used: str                 # Generation prompt

    # Mutation info
    mutation_strategy: str           # "dimension_push", "what_if", etc.
    mutation_description: str        # Human-readable description

    # Scores
    novelty_score: float
    coherence_score: float
    interest_score: float
    combined_score: float

    # Metadata
    created_at: datetime
    is_favorite: bool                # User can star snapshots
    user_notes: str | None           # Optional user annotations

    # Tree structure
    depth: int                       # Distance from root
    branch_name: str | None          # Optional branch label


class ExplorationSession:
    id: str
    name: str

    # Starting point
    reference_image_path: str
    base_style_profile: StyleProfile

    # Settings
    auto_mode: bool                  # Auto-continue or manual step
    mutations_per_step: int          # Generate N variations per step
    preferred_strategies: list[str]  # Which mutation types to use

    # State
    current_snapshot_id: str | None
    total_snapshots: int

    # Tree
    snapshots: list[ExplorationSnapshot]
```

### Database Schema

```sql
CREATE TABLE exploration_sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    reference_image_path TEXT NOT NULL,
    base_style_profile JSON NOT NULL,
    auto_mode BOOLEAN DEFAULT FALSE,
    mutations_per_step INTEGER DEFAULT 1,
    preferred_strategies JSON DEFAULT '["random_dimension", "what_if", "amplify"]',
    current_snapshot_id TEXT,
    total_snapshots INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE exploration_snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES exploration_sessions(id),
    parent_id TEXT REFERENCES exploration_snapshots(id),

    style_profile JSON NOT NULL,
    generated_image_path TEXT NOT NULL,
    prompt_used TEXT,

    mutation_strategy TEXT NOT NULL,
    mutation_description TEXT NOT NULL,

    novelty_score REAL,
    coherence_score REAL,
    interest_score REAL,
    combined_score REAL,

    depth INTEGER DEFAULT 0,
    branch_name TEXT,
    is_favorite BOOLEAN DEFAULT FALSE,
    user_notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_snapshots_session ON exploration_snapshots(session_id);
CREATE INDEX idx_snapshots_parent ON exploration_snapshots(parent_id);
CREATE INDEX idx_snapshots_favorite ON exploration_snapshots(is_favorite);
CREATE INDEX idx_snapshots_score ON exploration_snapshots(combined_score DESC);
```

## API Endpoints

```python
# Session management
POST   /api/explorer/sessions                    # Create new exploration
GET    /api/explorer/sessions                    # List all explorations
GET    /api/explorer/sessions/{id}               # Get exploration details
DELETE /api/explorer/sessions/{id}               # Delete exploration

# Exploration control
POST   /api/explorer/{session_id}/explore        # Run one exploration step
POST   /api/explorer/{session_id}/auto-explore   # Auto-run N steps
POST   /api/explorer/{session_id}/stop           # Stop auto-exploration
POST   /api/explorer/{session_id}/branch         # Branch from a snapshot

# Snapshot management
GET    /api/explorer/{session_id}/snapshots      # List all snapshots
GET    /api/explorer/{session_id}/snapshots/{id} # Get snapshot details
GET    /api/explorer/{session_id}/tree           # Get tree structure
POST   /api/explorer/snapshots/{id}/favorite     # Toggle favorite
POST   /api/explorer/snapshots/{id}/notes        # Add notes
POST   /api/explorer/snapshots/{id}/continue     # Continue from this snapshot

# Export
POST   /api/explorer/snapshots/{id}/to-style     # Convert snapshot to trained style
GET    /api/explorer/{session_id}/gallery        # Get gallery view data
```

## Frontend Components

### ExplorerPage
Main exploration interface with:
- Reference image display
- Current variation display
- Mutation strategy selector
- "Explore" / "Auto-Explore" buttons
- Score display (novelty, coherence, interest)

### ExplorationTree
Visual tree showing exploration history:
- Nodes = snapshots (thumbnails)
- Edges = parent-child relationships
- Color coding by score
- Click to branch from any node

### ExplorationGallery
Grid view of all snapshots:
- Sort by: score, date, novelty, depth
- Filter by: favorites, strategy type, score threshold
- Bulk actions: favorite, delete, export

### SnapshotDetail
Detailed view of single snapshot:
- Full-size image
- Style profile diff from parent
- Mutation description
- Scores breakdown
- "Continue from here" button
- "Save as trained style" button

## Example Session

```
User uploads: Moody watercolor landscape

Step 1: Extract base style
  → palette: muted blues/greens, low saturation
  → texture: visible paper grain, wet edges
  → lighting: overcast, soft shadows
  → mood: melancholic, quiet

Step 2: Explore (Random Dimension Push → saturation extreme)
  → MUTATION: Push saturation to "hypersaturated neon"
  → RESULT: Same composition but electric colors
  → SCORES: novelty=78, coherence=65, interest=82
  → SAVED as snapshot_001

Step 3: Explore (VLM What-If from snapshot_001)
  → MUTATION: "What if the neon colors were only in the shadows?"
  → RESULT: Dark areas glow with color, highlights stay neutral
  → SCORES: novelty=85, coherence=72, interest=91
  → SAVED as snapshot_002 ⭐ (user favorites this)

Step 4: Branch from base (Inversion → "dark mood" → "bright mood")
  → MUTATION: Invert melancholic to cheerful
  → RESULT: Same style but warm, sunny, inviting
  → SCORES: novelty=71, coherence=80, interest=68
  → SAVED as snapshot_003

Step 5: Continue from snapshot_002 (Amplification)
  → MUTATION: Push glowing shadows even further
  → RESULT: Shadows become primary light source, surreal
  → SCORES: novelty=92, coherence=58, interest=95
  → SAVED as snapshot_004 ⭐

User exports snapshot_002 and snapshot_004 as trained styles
```

## Implementation Phases

### Phase 1: Core Infrastructure ✅ COMPLETE
- [x] Database models for sessions/snapshots
- [x] Basic API endpoints (create, explore, list)
- [x] Single mutation strategy (random dimension push)
- [x] Basic scoring (novelty only)
- [x] Snapshot saving

### Phase 2: Mutation Variety ✅ COMPLETE
- [x] All 5 mutation strategies (random_dimension, what_if, crossover, inversion, amplify)
- [x] Full scoring (novelty + coherence + interest with weighted combination)
- [x] Strategy selection/weighting
- [x] Auto-explore mode

### Phase 3: Tree Navigation ✅ COMPLETE
- [x] Branch from any snapshot (via parent_snapshot_id)
- [x] Tree visualization data structure (GET /sessions/{id}/tree)
- [x] Continue from snapshot (set-current endpoint)
- [x] Depth tracking

### Phase 4: Frontend
- [ ] ExplorerPage with basic controls
- [ ] Gallery view
- [ ] Tree visualization
- [ ] Snapshot detail view

### Phase 5: Polish
- [x] Favorites and notes (implemented)
- [x] Export to trained style (implemented)
- [ ] Batch operations
- [ ] Exploration presets/templates

## Configuration Options

```python
class ExplorerConfig:
    # Mutation settings
    default_strategy_weights: dict = {
        "random_dimension": 0.25,
        "what_if": 0.25,
        "crossover": 0.15,
        "inversion": 0.15,
        "amplify": 0.20,
    }

    # Scoring thresholds
    min_coherence: float = 40.0      # Reject if below (too chaotic)
    min_novelty: float = 30.0        # Reject if below (too similar)

    # Auto-explore settings
    auto_explore_steps: int = 10
    auto_branch_threshold: float = 85.0  # Auto-branch if score above this

    # Limits
    max_depth: int = 20              # Max tree depth
    max_snapshots_per_session: int = 100
```

## Future Ideas

- **Guided exploration**: User provides direction ("make it more aggressive")
- **Multi-parent crossover**: Blend 2+ snapshots together
- **Exploration sharing**: Export/import exploration trees
- **AI curator**: Auto-select most interesting branches to continue
- **Style interpolation**: Animate between snapshots
- **Batch generation**: Generate N images per snapshot for variety
