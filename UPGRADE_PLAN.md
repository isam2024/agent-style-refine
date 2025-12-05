# System Upgrade Plan: Vectorized Directional Feedback

## Problem Statement

Current system has three critical weaknesses causing drift accumulation:

### Problem #1: No Feature Classification
System treats everything uniformly instead of distinguishing:
- **Style features** - aesthetic qualities (color saturation, brushstroke quality)
- **Structural motifs** - repeating compositional elements (swirl arcs, geometric patterns)
- **Scene constraints** - spatial/framing requirements (centered subject, circular boundary)
- **Surface coincidence** - accidental artifacts (random leaf shape, watermark ghost)

Result: Coincidences become locked as "motifs" → drift accumulates

### Problem #2: Evaluative vs Diagnostic Critique
Current: "Swirl placement diverged" (judgment)
Needed: "Swirl placement drifted 15° clockwise in upper-left quadrant due to botanical tonal substitution" (root cause + location)

Result: No actionable correction vector → random mutations persist

### Problem #3: Missing Directional Correction Signals
Current: ❌ "Wrong"
Needed:
- ⬅ move direction backward
- ⬆ increase strength
- ↘ reduce density
- ↺ rotate motif
- ⤵ flip symmetry

Result: Each iteration has randomness → no cumulative convergence

---

## Solution Architecture: 3-Phase Upgrade

### Phase 1: Feature Categorization

**Goal**: Classify every extracted feature into explicit buckets

**New Schema: FeatureClassification**
```python
class FeatureType(str, Enum):
    STRUCTURAL_MOTIF = "structural_motif"      # Repeating compositional element
    STYLE_FEATURE = "style_feature"            # Aesthetic quality
    SCENE_CONSTRAINT = "scene_constraint"      # Spatial/framing requirement
    POTENTIAL_COINCIDENCE = "potential_coincidence"  # Artifact (low confidence)

class ClassifiedFeature(BaseModel):
    feature_id: str                    # Unique identifier
    feature_type: FeatureType          # Category
    description: str                   # What it is
    source_dimension: str              # Which style dimension it came from
    confidence: float = 0.5            # 0.0-1.0, updated through iterations
    first_seen: int                    # Iteration number when discovered
    persistence_count: int = 1         # How many iterations it's appeared

class FeatureRegistry(BaseModel):
    """Registry of all classified features discovered during training"""
    features: dict[str, ClassifiedFeature] = {}  # feature_id -> feature
```

**Changes to StyleProfile**:
- Add `feature_registry: FeatureRegistry` field
- Existing sections (palette, motifs, etc.) stay but get linked to feature_ids

**Example Classification**:
```json
{
  "feature_registry": {
    "features": {
      "central_seated_cat": {
        "feature_id": "central_seated_cat",
        "feature_type": "scene_constraint",
        "description": "Cat seated in center of frame",
        "source_dimension": "composition",
        "confidence": 0.95,
        "first_seen": 1,
        "persistence_count": 5
      },
      "circular_containment": {
        "feature_id": "circular_containment",
        "feature_type": "structural_motif",
        "description": "Circular boundary framing the subject",
        "source_dimension": "composition",
        "confidence": 0.92,
        "first_seen": 1,
        "persistence_count": 5
      },
      "watercolor_dispersion": {
        "feature_id": "watercolor_dispersion",
        "feature_type": "style_feature",
        "description": "Radial color gradient with soft edges",
        "source_dimension": "texture",
        "confidence": 0.88,
        "first_seen": 1,
        "persistence_count": 5
      },
      "foliage_extensions": {
        "feature_id": "foliage_extensions",
        "feature_type": "potential_coincidence",
        "description": "Leaf-like shapes in arc tips",
        "source_dimension": "motifs",
        "confidence": 0.34,
        "first_seen": 3,
        "persistence_count": 2
      }
    }
  }
}
```

---

### Phase 2: Directional Corrections

**Goal**: Critic outputs actionable correction vectors, not just scores

**New Schema: DirectionalCorrection**
```python
class CorrectionDirection(str, Enum):
    MAINTAIN = "maintain"              # Keep as-is
    REINFORCE = "reinforce"            # Strengthen/amplify
    REDUCE = "reduce"                  # Weaken/diminish
    ROTATE = "rotate"                  # Adjust angle/orientation
    SIMPLIFY = "simplify"              # Remove detail/complexity
    EXAGGERATE = "exaggerate"          # Amplify curve/form
    REDISTRIBUTE = "redistribute"      # Reposition spatially
    ELIMINATE = "eliminate"            # Remove completely

class VectorizedCorrection(BaseModel):
    feature_id: str                    # Links to FeatureRegistry
    current_state: str                 # Description of current state
    target_state: str                  # Description of desired state
    direction: CorrectionDirection     # How to change
    magnitude: float                   # 0.0-1.0 (strength of change)
    spatial_hint: str | None = None    # e.g., "upper-left quadrant"
    diagnostic: str | None = None      # Root cause analysis
    confidence: float                  # 0.0-1.0 (critic's certainty)

class CritiqueResultV2(BaseModel):
    # Existing fields
    match_scores: dict[str, int]
    preserved_traits: list[str]
    lost_traits: list[str]
    interesting_mutations: list[str]
    updated_style_profile: StyleProfile

    # NEW: Vectorized corrections
    corrections: list[VectorizedCorrection] = []
```

**Example Corrections**:
```json
{
  "corrections": [
    {
      "feature_id": "foliage_extensions",
      "current_state": "Leaf shapes appearing in 3 arc tips, density ~40%",
      "target_state": "Minimal to no botanical elements in arcs",
      "direction": "reduce",
      "magnitude": 0.6,
      "spatial_hint": "arc tips at 45°, 90°, 135° positions",
      "diagnostic": "Model hallucinated botanical tonal substitutions due to color proximity",
      "confidence": 0.72
    },
    {
      "feature_id": "circular_containment",
      "current_state": "Circular boundary at 85% strength",
      "target_state": "Crisp circular boundary at 95% strength",
      "direction": "reinforce",
      "magnitude": 0.3,
      "spatial_hint": "entire boundary perimeter",
      "diagnostic": "Edge softness increased during rendering",
      "confidence": 0.91
    },
    {
      "feature_id": "watercolor_dispersion",
      "current_state": "Radial gradient density at 60%",
      "target_state": "Radial gradient density at 70%",
      "direction": "reinforce",
      "magnitude": 0.2,
      "spatial_hint": "background layer, radial from center",
      "diagnostic": "Color dispersion under-rendered compared to reference",
      "confidence": 0.68
    },
    {
      "feature_id": "halo_outline",
      "current_state": "Soft glow outline around subject",
      "target_state": "Maintain current implementation",
      "direction": "maintain",
      "magnitude": 0.0,
      "diagnostic": "Feature correctly preserved from reference",
      "confidence": 0.94
    }
  ]
}
```

---

### Phase 3: Confidence Tracking & Coincidence Detection

**Goal**: Automatically identify artifacts vs true motifs through iteration persistence

**Confidence Update Algorithm**:
```python
def update_feature_confidence(feature: ClassifiedFeature, appeared_in_iteration: bool):
    """
    Update confidence based on persistence across iterations.

    Confidence increases when:
    - Feature appears in both original AND generated
    - Feature persists across multiple iterations

    Confidence decreases when:
    - Feature disappears in generated image
    - Feature only appeared in 1-2 iterations (likely coincidence)
    """
    if appeared_in_iteration:
        # Feature appeared - boost confidence
        feature.persistence_count += 1

        # Confidence grows with persistence (logarithmic curve)
        # 1 iteration = 0.3, 3 iterations = 0.6, 5+ iterations = 0.85+
        persistence_factor = min(1.0, 0.3 + (0.15 * feature.persistence_count))

        # Smooth update (moving average)
        feature.confidence = 0.7 * feature.confidence + 0.3 * persistence_factor
    else:
        # Feature disappeared - penalize confidence
        decay = 0.15  # Confidence drops by 15% per missed iteration
        feature.confidence *= (1.0 - decay)

    # Clamp to valid range
    feature.confidence = max(0.0, min(1.0, feature.confidence))

def classify_by_confidence(confidence: float) -> FeatureType:
    """
    Reclassify features based on confidence thresholds.
    Low confidence features are likely coincidences.
    """
    if confidence >= 0.75:
        return "confirmed"  # True motif/feature
    elif confidence >= 0.50:
        return "probable"   # Likely real
    elif confidence >= 0.30:
        return "uncertain"  # Needs more data
    else:
        return "coincidence"  # Likely artifact
```

**Coincidence Pruning**:
- Features with confidence < 0.30 after 3 iterations → flagged as `potential_coincidence`
- Features with confidence < 0.20 after 5 iterations → moved to `forbidden_elements`

---

## Implementation Plan

### Step 1: Schema Updates

**Files to modify**:
- `backend/models/schemas.py`
  - Add `FeatureType`, `ClassifiedFeature`, `FeatureRegistry`
  - Add `CorrectionDirection`, `VectorizedCorrection`
  - Update `StyleProfile` to include `feature_registry: FeatureRegistry`
  - Update `CritiqueResult` to include `corrections: list[VectorizedCorrection]`

**Backward compatibility**:
- Use `model_config = {"extra": "allow"}` for old profiles
- Populate `feature_registry` from existing fields on first load

---

### Step 2: Extractor Prompt Updates

**File**: `backend/prompts/extractor.md`

**Add new section**:
```markdown
## FEATURE CLASSIFICATION

After extracting style elements, classify each significant feature:

For each feature, determine:
1. **Type**: structural_motif / style_feature / scene_constraint / potential_coincidence
2. **Confidence**: 0.5 (default for first extraction, will adjust through training)

Classification Guide:
- **structural_motif**: Repeating visual element that defines composition (swirls, geometric patterns, recurring shapes)
- **style_feature**: Aesthetic quality (brushstroke type, color treatment, texture rendering)
- **scene_constraint**: Spatial/framing requirement (centered subject, specific camera angle, boundary shapes)
- **potential_coincidence**: Single-instance detail that may be artifact (random leaf, watermark ghost, compression artifact)

Output in new `feature_registry` section with:
- Unique feature_id (snake_case)
- Feature type
- Clear description
- Source dimension (palette/lighting/texture/composition/motifs/core_invariants)

Example:
```json
"feature_registry": {
  "features": {
    "radial_color_gradient": {
      "feature_id": "radial_color_gradient",
      "feature_type": "style_feature",
      "description": "Colors disperse radially from center with soft edges",
      "source_dimension": "palette",
      "confidence": 0.5,
      "first_seen": 1,
      "persistence_count": 1
    }
  }
}
```
```

---

### Step 3: Critic Prompt Updates

**File**: `backend/prompts/critic.md`

**Add new section**:
```markdown
## VECTORIZED CORRECTION OUTPUT

For each feature in the feature_registry, output a correction directive:

```json
"corrections": [
  {
    "feature_id": "feature_from_registry",
    "current_state": "Describe what you see in the GENERATED image",
    "target_state": "Describe what it should look like (from ORIGINAL)",
    "direction": "maintain|reinforce|reduce|rotate|simplify|exaggerate|redistribute|eliminate",
    "magnitude": 0.0-1.0,
    "spatial_hint": "Where in the image (quadrant, layer, etc)",
    "diagnostic": "WHY the divergence occurred (root cause analysis)",
    "confidence": 0.0-1.0
  }
]
```

**Direction Guidelines**:
- `maintain`: Feature is correct, preserve it exactly
- `reinforce`: Feature is weak, needs strengthening (increase opacity/size/prominence)
- `reduce`: Feature is too strong, needs weakening (decrease opacity/size/prominence)
- `rotate`: Feature has wrong angle/orientation
- `simplify`: Feature has excess detail, remove complexity
- `exaggerate`: Feature needs more dramatic curve/form
- `redistribute`: Feature is in wrong spatial position
- `eliminate`: Feature is unwanted artifact, remove completely

**Magnitude Scale**:
- 0.0-0.2: Tiny adjustment
- 0.2-0.4: Small adjustment
- 0.4-0.6: Moderate adjustment
- 0.6-0.8: Large adjustment
- 0.8-1.0: Dramatic adjustment

**Diagnostic Requirements**:
- Don't just say "it drifted"
- Explain WHY: color proximity? model hallucination? rendering artifact?
- Be specific: "upper-left quadrant" not "somewhere in the image"
```

---

### Step 4: Generator Updates

**File**: `backend/prompts/generator.md`

**Add new section**:
```markdown
## DIRECTIONAL CORRECTION CONSUMPTION

You have access to VECTORIZED CORRECTIONS from the previous critique:

{{CORRECTIONS}}

For each correction with direction != "maintain":

1. **reinforce**: Explicitly strengthen this element in your prompt
   - Example: "circular boundary MUST be crisp and well-defined, 95% opacity"

2. **reduce**: Explicitly weaken or minimize this element
   - Example: "minimal botanical elements, avoid leaf shapes in arc tips"

3. **eliminate**: Explicitly forbid this element
   - Example: "NO foliage extensions, NO leaf-like shapes"

4. **rotate/redistribute**: Adjust spatial positioning
   - Example: "swirl arcs at 30°, 60°, 90° angles (not 45°)"

5. **simplify**: Reduce complexity
   - Example: "simple smooth curves, no texture variation within arcs"

6. **exaggerate**: Amplify the feature
   - Example: "dramatic color dispersion with STRONG radial gradient"

Magnitude tells you HOW MUCH to adjust (0.1 = subtle, 0.9 = extreme).

**CRITICAL**: Focus corrections on features with confidence >= 0.5.
Ignore or explicitly avoid features with confidence < 0.3 (likely coincidences).
```

---

### Step 5: Service Layer Updates

**File**: `backend/services/extractor.py`

**Changes**:
- Parse `feature_registry` from VLM response
- Initialize all features with confidence=0.5, first_seen=1, persistence_count=1

**File**: `backend/services/critic.py`

**Changes**:
- Parse `corrections` from VLM response
- Update feature confidence based on presence/absence in generated image
- Classify features by confidence (confirmed/probable/uncertain/coincidence)

**File**: `backend/services/agent.py`

**Changes**:
- Include corrections in generator prompt template
- Format corrections as human-readable directives
- Filter by confidence threshold (only include features with confidence >= 0.4)

**File**: `backend/services/auto_improver.py`

**Changes**:
- Track feature confidence over iterations
- Prune coincidences (confidence < 0.20 after 5 iterations)
- Add coincidence metrics to training insights

---

## Expected Results

### Before Upgrade:
❌ Artifacts accumulate as "motifs"
❌ Critic says "wrong" but not "how to fix"
❌ Random mutations persist across iterations
❌ No clear convergence path

### After Upgrade:
✅ Features classified: structural/style/scene/coincidence
✅ Directional corrections: "reduce foliage by 60% in upper-left"
✅ Confidence tracking: artifacts auto-detected and pruned
✅ Vectorized feedback: cumulative convergence, not random walk
✅ Stable style WITHOUT freezing creativity

---

## Migration Strategy

1. **Add schemas** (backward compatible with `extra: allow`)
2. **Update prompts** (extractor, critic, generator)
3. **Test extraction** on existing image (verify feature_registry populated)
4. **Test critique** on iteration pair (verify corrections generated)
5. **Test iteration** with directional feedback (verify generator consumes corrections)
6. **Run auto-improve** (verify confidence tracking and coincidence pruning)

---

## Future Enhancements

### Phase 4: Human-Editable Feature Vectors
- UI to view/edit feature_registry
- Manually adjust confidence scores
- Override directional corrections
- Lock/unlock specific features

### Phase 5: Feature Visualization
- Overlay feature_ids on images
- Color-code by confidence (green=confirmed, yellow=uncertain, red=coincidence)
- Show correction vectors as arrows/annotations

### Phase 6: Cross-Session Feature Library
- Extract common features across multiple training sessions
- Build reusable feature templates
- "Portrait lighting template", "Watercolor dispersion template", etc.
