# Technical Architecture - Style Refine Agent

**Version:** 2.0
**Last Updated:** 2025-12-05

This document provides deep technical details about the system architecture, algorithms, and implementation decisions.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Data Flow Pipelines](#data-flow-pipelines)
3. [Algorithms](#algorithms)
4. [Evaluation System](#evaluation-system)
5. [Prompt Engineering](#prompt-engineering)
6. [VLM Integration](#vlm-integration)
7. [State Management](#state-management)
8. [Error Handling](#error-handling)
9. [Performance Optimization](#performance-optimization)
10. [Design Decisions](#design-decisions)

---

## System Architecture

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     PRESENTATION LAYER                       │
│  React Components + TypeScript + TailwindCSS                │
│  - Session Manager                                           │
│  - Side-by-Side Viewer                                       │
│  - Style Profile Editor                                      │
│  - Feedback Controls                                         │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP/WebSocket
┌──────────────────▼──────────────────────────────────────────┐
│                     APPLICATION LAYER                        │
│  FastAPI Routers (REST endpoints)                           │
│  - SessionsRouter: CRUD operations                          │
│  - IterationRouter: Training loop orchestration             │
│  - StylesRouter: Trained styles management                  │
│  - WebSocketManager: Real-time updates                      │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                     BUSINESS LOGIC LAYER                     │
│  Service Classes (domain logic)                             │
│  - StyleExtractor: VLM-based extraction                     │
│  - StyleCritic: Multi-dimensional evaluation                │
│  - StyleAgent: Prompt generation                            │
│  - AutoImprover: Training loop + decision logic             │
│  - PromptWriter: Style application                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                     INTEGRATION LAYER                        │
│  External System Clients                                    │
│  - VLMService: Ollama API client                           │
│  - ComfyUIService: Image generation API                     │
│  - StorageService: File I/O operations                      │
│  - ColorExtractor: PIL-based color analysis                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                     DATA ACCESS LAYER                        │
│  Database Models + ORM                                       │
│  - Session, Iteration, TrainedStyle (SQLAlchemy models)     │
│  - StyleProfile, CritiqueResult (Pydantic schemas)          │
│  - Database connection pooling                              │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                     PERSISTENCE LAYER                        │
│  Storage Systems                                            │
│  - SQLite database (metadata, sessions, profiles)           │
│  - File system (PNG images, debug logs)                     │
└─────────────────────────────────────────────────────────────┘
```

### Component Interactions

```
┌──────────────┐
│   Frontend   │
└──────┬───────┘
       │ REST
       │
┌──────▼───────┐
│   Routers    │
└──────┬───────┘
       │
       ├──────────────────────────────────────┐
       │                                       │
┌──────▼──────────┐                   ┌───────▼────────┐
│  AutoImprover   │                   │ SessionManager │
└──────┬──────────┘                   └────────────────┘
       │
       ├────────┬────────┬────────┐
       │        │        │        │
┌──────▼──┐ ┌──▼───┐ ┌──▼────┐ ┌─▼─────┐
│Extractor│ │Agent │ │Critic │ │ComfyUI│
└──────┬──┘ └──┬───┘ └──┬────┘ └───────┘
       │       │       │
       └───────┴───────┘
               │
        ┌──────▼──────┐
        │ VLM Service │
        └─────────────┘
```

---

## Data Flow Pipelines

### 1. Style Extraction Pipeline

```python
# Entry: POST /api/extract
# Input: session_id
# Output: StyleProfile v1

def extract_style_pipeline(session_id: str) -> StyleProfile:
    # 1. Load original image
    session = db.query(Session).filter_by(id=session_id).first()
    image_b64 = storage.load_image(session.original_image_path)

    # 2. Extract colors with PIL (pixel-accurate)
    color_data = extract_colors_from_b64(image_b64)
    # Returns:
    # {
    #   "dominant_colors": ["#1b2a4a", "#41959b", "#ece0bb"],
    #   "accents": ["#c0392b", "#f39c12"],
    #   "color_descriptions": ["deep navy blue", "teal", "pale cream"],
    #   "saturation": "medium",
    #   "value_range": "dark mids with bright highlights"
    # }

    # 3. Load extraction prompt template
    prompt_template = extractor._load_prompt()  # extractor.md

    # 4. Send to VLM
    vlm_response = await vlm_service.analyze(
        prompt=prompt_template,
        images=[image_b64]
    )

    # 5. Parse JSON response
    profile_dict = json.loads(vlm_response)

    # 6. Validate schema
    style_profile = StyleProfile(**profile_dict)

    # 7. Override palette with PIL-extracted colors
    style_profile.palette.dominant_colors = color_data["dominant_colors"]
    style_profile.palette.accents = color_data["accents"]

    # 8. Build mechanical baseline (no VLM hallucination)
    mechanical_baseline = build_mechanical_baseline(
        original_subject=style_profile.original_subject,
        framing=style_profile.composition.framing,
        structural_notes=style_profile.composition.structural_notes
    )
    style_profile.suggested_test_prompt = mechanical_baseline

    # 9. Save to database as version 1
    db_profile = DBStyleProfile(
        session_id=session_id,
        version=1,
        profile_json=style_profile.model_dump_json()
    )
    db.add(db_profile)
    db.commit()

    return style_profile
```

**Key Design Decisions:**

1. **PIL color extraction overrides VLM:** VLM can hallucinate colors, PIL is pixel-accurate
2. **Mechanical baseline:** Prevents VLM from injecting style adjectives into identity
3. **Schema validation:** Pydantic catches malformed VLM responses early
4. **Version 1:** First profile is always extraction output (baseline for comparison)

### 2. Iteration Pipeline

```python
# Entry: POST /api/iterate/step
# Input: session_id, subject, creativity_level
# Output: Iteration with critique

async def iteration_pipeline(
    session_id: str,
    subject: str,
    creativity_level: int = 50
) -> dict:
    # 1. Load session and current style profile
    session = db.query(Session).filter_by(id=session_id).first()
    current_profile = get_latest_style_profile(session_id)
    original_image = storage.load_image(session.original_image_path)

    # 2. Build feedback history
    feedback_history = build_feedback_history(session_id)
    # Returns list of:
    # {
    #   "iteration": 1,
    #   "approved": True,
    #   "scores": {...},
    #   "preserved_traits": [...],
    #   "lost_traits": [...],
    #   "recovery_guidance": "..." (if rejected)
    # }

    # 3. Generate image prompt via Style Agent
    system_prompt = agent.build_system_prompt(
        style_profile=current_profile,
        feedback_history=feedback_history,
        latest_corrections=previous_corrections  # feature branch
    )
    # System prompt includes:
    # - Core invariants (MUST preserve)
    # - Full profile JSON
    # - Feedback with approval status
    # - Lost trait counts (emphasize frequently lost)
    # - Preserved trait list (maintain what works)
    # - Recovery guidance (if last iteration rejected)
    # - Vectorized corrections (feature branch)

    image_prompt = await agent.generate_image_prompt(
        system=system_prompt,
        subject=subject
    )
    # VLM generates styled prompt like:
    # "Black cat facing left, centered in circular frame, soft watercolor
    #  texture with radial color dispersion in deep navy and teal tones,
    #  painterly brushstrokes, soft ambient lighting with warm shadows, ..."

    # 4. Generate image with ComfyUI
    generated_image_b64 = await comfyui.generate(
        prompt=image_prompt,
        workflow=default_flux_workflow
    )

    # 5. Save generated image
    iteration_num = session.iteration_count + 1
    image_path = storage.save_image(
        session_id=session_id,
        image_b64=generated_image_b64,
        filename=f"iteration_{iteration_num:03d}.png"
    )

    # 6. Critique generated image
    critique = await critic.critique(
        original_image_b64=original_image,
        generated_image_b64=generated_image_b64,
        style_profile=current_profile,
        creativity_level=creativity_level
    )
    # Returns CritiqueResult:
    # {
    #   "match_scores": {
    #     "palette": 85, "line_and_shape": 90, "texture": 75,
    #     "lighting": 80, "composition": 85, "motifs": 70,
    #     "overall": 82
    #   },
    #   "preserved_traits": ["soft ambient lighting", "circular boundary"],
    #   "lost_traits": ["bold brushstroke energy"],
    #   "interesting_mutations": ["enhanced color dispersion"],
    #   "updated_style_profile": {...},
    #   "corrections": [...]  # feature branch
    # }

    # 7. Save iteration to database
    iteration = Iteration(
        session_id=session_id,
        iteration_num=iteration_num,
        image_path=str(image_path),
        prompt_used=image_prompt,
        scores_json=json.dumps(critique.match_scores),
        preserved_traits=json.dumps(critique.preserved_traits),
        lost_traits=json.dumps(critique.lost_traits),
        approved=None  # Pending user feedback in training mode
    )
    db.add(iteration)
    db.commit()

    return {
        "iteration_id": iteration.id,
        "iteration_num": iteration_num,
        "image_b64": generated_image_b64,
        "image_url": f"/outputs/{session_id}/iteration_{iteration_num:03d}.png",
        "prompt_used": image_prompt,
        "critique": critique
    }
```

**Key Design Decisions:**

1. **Feedback history aggregation:** Agent learns from all past iterations
2. **System prompt composition:** Everything needed for style replication in one prompt
3. **Separate critique step:** Allows inspection before approval decision
4. **Database persistence:** All iterations saved for history/analysis

### 3. Auto-Evaluation Pipeline

```python
# Entry: POST /api/iterate/auto
# Input: session_id, subject, max_iterations, target_score, creativity_level
# Output: Complete training report

async def auto_evaluation_pipeline(
    session_id: str,
    subject: str,
    max_iterations: int = 10,
    target_score: int = 85,
    creativity_level: int = 50
) -> dict:
    session = db.query(Session).filter_by(id=session_id).first()
    current_profile = get_latest_style_profile(session_id)
    original_image = storage.load_image(session.original_image_path)

    # Initialize evaluation state
    feedback_history = []
    baseline_scores = None  # Last approved scores
    best_approved_score = 0
    training_insights = {
        "frequently_lost_traits": Counter(),
        "frequently_preserved_traits": Counter()
    }

    for iteration_num in range(1, max_iterations + 1):
        await log(f"Starting iteration {iteration_num}/{max_iterations}")

        # 1. Run iteration (generate + critique)
        iteration_result = await run_focused_iteration(
            session_id=session_id,
            subject=subject,
            style_profile=current_profile,
            original_image_b64=original_image,
            feedback_history=feedback_history,
            previous_scores=baseline_scores,
            previous_corrections=previous_corrections,  # feature branch
            creativity_level=creativity_level,
            training_insights=training_insights
        )

        critique = iteration_result["critique"]
        scores = critique.match_scores

        # 2. Weighted regression detection
        weighted_delta = 0.0
        if baseline_scores:
            for dim in ["palette", "line_and_shape", "texture", "lighting", "composition", "motifs"]:
                delta = scores[dim] - baseline_scores[dim]
                weight = DIMENSION_WEIGHTS[dim]
                weighted_delta += delta * weight

        # 3. Decision logic (Three-Tier Approval)
        decision, approved = evaluate_iteration(
            scores=scores,
            baseline_scores=baseline_scores,
            weighted_delta=weighted_delta,
            is_first_iteration=(iteration_num == 1)
        )

        # 4. Handle decision
        if approved:
            await log(f"✓ APPROVED: {decision}")

            # Update profile to new version
            current_profile = StyleProfile(**critique.updated_style_profile)
            save_style_profile(session_id, current_profile, version=iteration_num + 1)

            # Update baseline scores
            baseline_scores = scores
            best_approved_score = max(best_approved_score, scores["overall"])

            # Update training insights
            training_insights["frequently_preserved_traits"].update(
                critique.preserved_traits
            )

            # Check if target reached
            if scores["overall"] >= target_score:
                await log(f"Target score {target_score} reached!")
                break

        else:
            await log(f"✗ REJECTED: {decision}")

            # Revert to last approved profile (don't save updated profile)
            current_profile = get_latest_approved_style_profile(session_id)

            # Generate recovery guidance
            recovery_guidance = generate_recovery_guidance(
                scores=scores,
                baseline_scores=baseline_scores,
                lost_traits=critique.lost_traits,
                interesting_mutations=critique.interesting_mutations
            )

            # Update training insights
            training_insights["frequently_lost_traits"].update(
                critique.lost_traits
            )

        # 5. Add to feedback history
        feedback_history.append({
            "iteration": iteration_num,
            "approved": approved,
            "notes": decision,
            "scores": scores,
            "preserved_traits": critique.preserved_traits,
            "lost_traits": critique.lost_traits,
            "recovery_guidance": recovery_guidance if not approved else None
        })

        # 6. Extract corrections for next iteration (feature branch)
        if hasattr(critique, 'corrections') and critique.corrections:
            previous_corrections = [
                corr.model_dump() for corr in critique.corrections
            ]

    # Return complete training report
    return {
        "completed_iterations": iteration_num,
        "final_score": scores["overall"],
        "best_approved_score": best_approved_score,
        "final_profile_version": get_latest_profile_version(session_id),
        "convergence_reason": "target_reached" if scores["overall"] >= target_score else "max_iterations",
        "iterations": feedback_history
    }
```

**Key Design Decisions:**

1. **Stateful loop:** Maintains baseline, profile, feedback across iterations
2. **Reversion on rejection:** Prevents drift by keeping last good state
3. **Training insights:** Aggregates patterns across iterations for emphasis
4. **Early stopping:** Exits when target reached (efficiency)

---

## Algorithms

### 1. Weighted Regression Detection

**Problem:** Single overall score can oscillate:
- Iteration 1: 70 overall → APPROVE
- Iteration 2: 68 overall → REJECT (regression)
- Iteration 3: 69 overall → REJECT (still below 70)
- Stuck forever, can't recover

**Solution:** Weight dimensions by importance, detect net progress

```python
DIMENSION_WEIGHTS = {
    "composition": 2.0,      # Spatial structure most critical
    "line_and_shape": 2.0,   # Form definition most critical
    "texture": 1.5,          # Surface quality important
    "lighting": 1.5,         # Mood and depth important
    "palette": 1.0,          # Well-tracked via color extraction
    "motifs": 0.8,           # Style consistency, less critical
}

def calculate_weighted_delta(current_scores, baseline_scores):
    """Calculate weighted progress across dimensions."""
    if not baseline_scores:
        return 0.0  # First iteration (no baseline)

    weighted_delta = 0.0
    dimension_deltas = {}

    for dim in DIMENSION_WEIGHTS.keys():
        delta = current_scores[dim] - baseline_scores[dim]
        weight = DIMENSION_WEIGHTS[dim]
        weighted_contribution = delta * weight

        weighted_delta += weighted_contribution
        dimension_deltas[dim] = {
            "delta": delta,
            "weight": weight,
            "weighted": weighted_contribution
        }

    return weighted_delta, dimension_deltas
```

**Example:**

```python
# Iteration 2 scores:
current = {
    "composition": 80,   # +10 from baseline 70
    "palette": 78,       # +8 from baseline 70
    "lighting": 50,      # -20 from baseline 70
    "line_and_shape": 65, # -5 from baseline 70
    "texture": 68,       # -2 from baseline 70
    "motifs": 60,        # -10 from baseline 70
    "overall": 68        # -2 overall (would be REJECTED in old system)
}

baseline = {dim: 70 for dim in current.keys()}

# Weighted calculation:
weighted_delta = (
    (+10 * 2.0) +  # composition: +20
    (+8 * 1.0) +   # palette: +8
    (-20 * 1.5) +  # lighting: -30
    (-5 * 2.0) +   # line_and_shape: -10
    (-2 * 1.5) +   # texture: -3
    (-10 * 0.8)    # motifs: -8
) = 20 + 8 - 30 - 10 - 3 - 8 = -23

# Result: Weighted Δ = -23 (negative)
# Decision: REJECT (net regression despite composition improvement)
```

**Benefits:**
- Recognizes partial improvements (composition +10 is valuable)
- Penalizes critical dimension losses (lighting -20 is severe)
- Allows building on strengths while recovering weaknesses
- Prevents oscillation (cumulative progress tracked)

### 2. Three-Tier Approval Logic

```python
def evaluate_iteration(
    scores: dict[str, int],
    baseline_scores: dict[str, int] | None,
    weighted_delta: float,
    is_first_iteration: bool
) -> tuple[str, bool]:
    """
    Evaluate iteration with three-tier approval system.

    Returns:
        (decision_reason, approved)
    """
    # Quality thresholds
    OVERALL_TARGET = 70
    DIMENSION_THRESHOLD = 55

    # Weighted progress thresholds
    STRONG_PROGRESS = 3.0
    WEAK_PROGRESS = 1.0

    # Catastrophic thresholds
    CATASTROPHIC_THRESHOLDS = {
        "lighting": 20,
        "composition": 30,
        "motifs": 20
    }

    # --- TIER 1: Quality Targets ---
    meets_overall = scores["overall"] >= OVERALL_TARGET
    meets_dimensions = all(
        scores[dim] >= DIMENSION_THRESHOLD
        for dim in ["palette", "line_and_shape", "texture", "lighting", "composition", "motifs"]
    )

    if meets_overall and meets_dimensions:
        return (
            f"PASS (Tier 1 - Quality Targets): Overall {scores['overall']}/{OVERALL_TARGET}, "
            f"all dimensions ≥ {DIMENSION_THRESHOLD}",
            True
        )

    # First iteration special case (no baseline for comparison)
    if is_first_iteration:
        return (
            f"PASS (Baseline): First iteration with overall {scores['overall']}",
            True
        )

    # --- TIER 2: Strong Weighted Progress ---
    if weighted_delta >= STRONG_PROGRESS:
        improved_dims = [
            dim for dim in scores.keys()
            if scores[dim] > baseline_scores[dim]
        ]
        return (
            f"PASS (Tier 2 - Strong Progress): Weighted Δ={weighted_delta:.1f} | "
            f"Improved: {', '.join(improved_dims)}",
            True
        )

    # --- TIER 3: Weak Positive Progress ---
    if weighted_delta >= WEAK_PROGRESS:
        return (
            f"PASS (Tier 3 - Weak Progress): Weighted Δ={weighted_delta:.1f} | "
            f"Incremental improvement",
            True
        )

    # --- REJECTION: Negative Progress ---
    regressed_dims = [
        f"{dim}({scores[dim] - baseline_scores[dim]:+d})"
        for dim in scores.keys()
        if scores[dim] < baseline_scores[dim]
    ]

    # Check for catastrophic failures
    catastrophic = [
        f"{dim}={scores[dim]}"
        for dim, threshold in CATASTROPHIC_THRESHOLDS.items()
        if scores[dim] <= threshold
    ]

    decision = f"FAIL: Weighted Δ={weighted_delta:.1f} (negative) | "
    decision += f"Regressed: {', '.join(regressed_dims)}"

    if catastrophic:
        decision += f" | CATASTROPHIC: {', '.join(catastrophic)}"

    return (decision, False)
```

**Decision Tree:**

```
Is first iteration?
├─ YES → APPROVE (Baseline)
└─ NO → Continue

Meets quality targets? (overall≥70, dims≥55)
├─ YES → APPROVE (Tier 1)
└─ NO → Continue

Weighted Δ ≥ +3.0?
├─ YES → APPROVE (Tier 2 - Strong)
└─ NO → Continue

Weighted Δ ≥ +1.0?
├─ YES → APPROVE (Tier 3 - Weak)
└─ NO → Continue

Weighted Δ < 0?
└─ YES → REJECT (Regression)
```

### 3. Recovery Guidance Generation

```python
def generate_recovery_guidance(
    scores: dict[str, int],
    baseline_scores: dict[str, int],
    lost_traits: list[str],
    interesting_mutations: list[str]
) -> str:
    """Generate recovery instructions after rejection."""

    guidance_lines = []
    guidance_lines.append("Action: Revert to last approved state and correct the specific failures listed above")
    guidance_lines.append("")

    # Identify issues
    issues = []

    # 1. Catastrophic failures
    CATASTROPHIC_THRESHOLDS = {
        "lighting": 20,
        "composition": 30,
        "motifs": 20
    }

    catastrophic_dims = [
        (dim, scores[dim])
        for dim, threshold in CATASTROPHIC_THRESHOLDS.items()
        if scores[dim] <= threshold
    ]

    if catastrophic_dims:
        issues.append("CATASTROPHIC: " + ", ".join(
            f"{dim}={score}" for dim, score in catastrophic_dims
        ))
        for dim, score in catastrophic_dims:
            issues.append(f"  → {dim}: Must restore from last approved iteration")

    # 2. Lost traits (must restore)
    if lost_traits:
        issues.append("LOST TRAITS: " + ", ".join(lost_traits))
        issues.append("  → These must be restored in next iteration")

    # 3. Interesting mutations (avoid)
    if interesting_mutations:
        issues.append("AVOID: " + ", ".join(interesting_mutations))
        issues.append("  → These introduced incompatible elements")

    # Format
    if issues:
        guidance_lines.append("Failure Analysis ({} issues):".format(len(issues)))
        guidance_lines.extend(f"  {issue}" for issue in issues)
        guidance_lines.append("")

    guidance = "\n".join(guidance_lines)

    return guidance
```

**Example Output:**

```
Action: Revert to last approved state and correct the specific failures listed above

Failure Analysis (3 issues):
  CATASTROPHIC: lighting=15
    → lighting: Must restore from last approved iteration
  LOST TRAITS: Dynamic lighting effect, Warm golden shadows, Circular boundary definition
    → These must be restored in next iteration
  AVOID: Harsh directional shadows, Cool blue color shift
    → These introduced incompatible elements
```

**How It's Used:**

1. **Injection into feedback history:**
   ```python
   feedback_history.append({
       "iteration": n,
       "approved": False,
       "notes": decision_reason,
       "recovery_guidance": guidance
   })
   ```

2. **Agent reads in next iteration:**
   ```markdown
   ## FEEDBACK FROM PREVIOUS ITERATIONS:

   Iteration 5: ❌ REJECTED - RECOVERY NEEDED

   Action: Revert to last approved state and correct the specific failures

   CATASTROPHIC: lighting=15
   → Must restore soft ambient lighting from last approved iteration

   LOST TRAITS: Dynamic lighting effect, Warm golden shadows
   → These must be restored in next iteration
   ```

3. **Agent prioritizes recovery:**
   - Restoration takes priority over creativity
   - Specific dimensions targeted (lighting)
   - Explicit elements to include (warm golden shadows)

### 4. Feature Confidence Tracking (Feature Branch)

**Algorithm:** Logarithmic growth with persistence

```python
def update_feature_confidence(
    feature: ClassifiedFeature,
    appeared_in_iteration: bool
) -> float:
    """
    Update confidence score based on persistence.

    Confidence grows when:
    - Feature appears in both original AND generated (appeared=True)
    - Feature persists across multiple iterations

    Confidence decays when:
    - Feature disappears in generated image (appeared=False)
    - Feature only appeared 1-2 times (likely coincidence)

    Growth curve (logarithmic):
    - 1 iteration: confidence = 0.3
    - 2 iterations: confidence = 0.45
    - 3 iterations: confidence = 0.6
    - 5 iterations: confidence = 0.85+
    """
    current_confidence = feature.confidence
    persistence_count = feature.persistence_count

    if appeared_in_iteration:
        # Feature appeared - boost confidence
        feature.persistence_count += 1

        # Logarithmic growth: confidence = 0.3 + (0.15 * persistence)
        # Capped at 1.0
        persistence_factor = min(1.0, 0.3 + (0.15 * feature.persistence_count))

        # Smooth update (moving average: 70% old, 30% new)
        new_confidence = 0.7 * current_confidence + 0.3 * persistence_factor

    else:
        # Feature disappeared - decay confidence
        decay_rate = 0.15  # 15% drop per missed iteration
        new_confidence = current_confidence * (1.0 - decay_rate)

    # Clamp to valid range [0.0, 1.0]
    new_confidence = max(0.0, min(1.0, new_confidence))

    # Update in-place
    feature.confidence = new_confidence

    return new_confidence
```

**Growth Curve Visualization:**

```
Confidence
1.0 │                              ████████████
    │                         █████
    │                    █████
0.8 │               █████
    │          █████
    │      ████
0.6 │   ███
    │ ██
0.4 │█
    │
0.2 │
    │
0.0 └─────────────────────────────────────────
    0    1    2    3    4    5    6    7    8
                   Iterations

Legend:
- Appears in every iteration: logarithmic growth to 1.0
- Appears, then misses one: confidence dips, recovers if reappears
- Only appears once: stays low, decays to ~0.1
```

**Usage:**

```python
# After critique, update all features
features = style_profile.feature_registry.features
corrected_feature_ids = {corr.feature_id for corr in corrections}

for feature_id, feature in features.items():
    appeared = feature_id in corrected_feature_ids
    new_confidence = update_feature_confidence(feature, appeared)

    if new_confidence < 0.3:
        # Low confidence - likely artifact, consider removing
        logger.info(f"Feature {feature_id} has low confidence {new_confidence:.2f}")
    elif new_confidence > 0.7:
        # High confidence - likely true motif, prioritize
        logger.info(f"Feature {feature_id} is established motif {new_confidence:.2f}")
```

**Auto-Pruning (Future):**

```python
# After N iterations, prune low-confidence features
if iteration_num >= 5:
    features_to_remove = [
        fid for fid, feature in features.items()
        if feature.confidence < 0.3 and feature.feature_type == "potential_coincidence"
    ]
    for fid in features_to_remove:
        del features[fid]
        logger.info(f"Auto-pruned low-confidence feature: {fid}")
```

---

## Evaluation System

### Multi-Dimensional Scoring

**Dimensions:**

1. **Palette (Weight: 1.0x)**
   - Color accuracy (hex values via PIL extraction)
   - Saturation level match
   - Value range distribution
   - Color relationships (warm/cool balance)

2. **Line & Shape (Weight: 2.0x)**
   - Edge treatment (soft/hard/mixed)
   - Shape language (organic/geometric)
   - Form definition quality
   - Silhouette accuracy

3. **Texture (Weight: 1.5x)**
   - Surface quality (smooth/rough/painterly)
   - Noise level (low/medium/high)
   - Special effects (bloom, grain, etc.)
   - Material representation

4. **Lighting (Weight: 1.5x)**
   - Lighting type (ambient/directional/backlit)
   - Shadow quality and color
   - Highlight treatment
   - Mood consistency

5. **Composition (Weight: 2.0x)**
   - Camera angle preservation
   - Framing accuracy (centered/rule-of-thirds)
   - Depth layer relationships
   - Negative space treatment
   - **Structural notes** (frozen identity)

6. **Motifs (Weight: 0.8x)**
   - Recurring element presence
   - Forbidden element absence
   - Style consistency
   - Visual vocabulary coherence

**Scoring Rubric (0-100):**

```
90-100: Near perfect match
        - All aspects captured with high fidelity
        - Could mistake for same artist/source
        - Minor variations only

70-89:  Good match
        - Core style present and recognizable
        - Some aspects excellent, others good
        - Minor drift in 1-2 dimensions

50-69:  Moderate match
        - Style recognizable but differences notable
        - Some dimensions strong, others weak
        - Acceptable but needs improvement

30-49:  Weak match
        - Style elements present but overwhelmed by drift
        - More differences than similarities
        - Requires significant correction

0-29:   Poor match
        - Style largely lost or misinterpreted
        - May be entirely different aesthetic
        - Catastrophic failure
```

### Dimension Weight Rationale

**High Weight (2.0x): Composition, Line & Shape**
- Define **structural identity**
- Hard to recover if lost
- Most visible to human perception
- Critical for "same style" recognition

**Medium Weight (1.5x): Texture, Lighting**
- Affect **perception and mood**
- Important but more refinable
- Can be adjusted without identity loss
- Contribute to quality feel

**Standard Weight (1.0x): Palette**
- Already **accurately measured** via PIL color extraction
- VLM scoring redundant with pixel data
- Important but well-controlled

**Low Weight (0.8x): Motifs**
- **Emergent and soft** constraints
- Evolves through training
- Less critical than core structure
- Style consistency vs identity

### Catastrophic Failure Detection

**Thresholds:**

```python
CATASTROPHIC_THRESHOLDS = {
    "lighting": 20,      # Total loss of lighting
    "composition": 30,   # Total loss of structure
    "motifs": 20,        # Forbidden elements introduced
}
```

**Detection Logic:**

```python
def detect_catastrophic_failures(scores: dict[str, int]) -> list[tuple[str, int]]:
    """Detect dimensions with catastrophic scores."""
    failures = []

    for dim, threshold in CATASTROPHIC_THRESHOLDS.items():
        if scores[dim] <= threshold:
            failures.append((dim, scores[dim]))

    return failures
```

**Why These Thresholds?**

- **Lighting ≤ 20:** Means lighting completely wrong (e.g., harsh directional vs soft ambient)
- **Composition ≤ 30:** Means spatial structure broken (e.g., subject off-frame vs centered)
- **Motifs ≤ 20:** Means forbidden elements present (e.g., photorealistic in ink drawing style)

**Recovery Protocol:**

1. Immediate rejection (even if overall score decent)
2. Generate specific recovery guidance
3. Revert profile to last approved version
4. Inject recovery priority into next feedback
5. Next iteration focuses exclusively on recovery

**Example:**

```python
# Iteration 5 scores:
scores = {
    "overall": 62,        # Decent overall
    "palette": 75,        # Good
    "line_and_shape": 70, # Good
    "texture": 65,        # OK
    "lighting": 15,       # ← CATASTROPHIC
    "composition": 80,    # Great
    "motifs": 55          # OK
}

# Detect: lighting=15 ≤ 20
# Decision: REJECT (catastrophic despite overall 62)
# Action: Revert profile, add recovery for lighting
# Next iteration: Focus on restoring lighting from approved state
```

---

## Prompt Engineering

### Prompt Architecture

**Three-Prompt System:**

1. **Extractor Prompt** (extractor.md)
   - **Purpose:** Extract structural identity + refinable style
   - **Input:** Single reference image
   - **Output:** StyleProfile JSON (v1)
   - **Length:** 6.5KB (main), 10.4KB (feature)

2. **Critic Prompt** (critic.md)
   - **Purpose:** Compare generated to reference, score, update profile
   - **Input:** Two images (original + generated) + current profile
   - **Output:** CritiqueResult JSON
   - **Length:** 8.2KB (main), 10.3KB (feature)

3. **Generator Prompt** (generator.md)
   - **Purpose:** Build style agent system prompt for image generation
   - **Input:** Profile + feedback history + corrections
   - **Output:** System prompt for VLM
   - **Length:** 4.8KB (main), 5.7KB (feature)

### Template Substitution Pattern

**Example (Generator Prompt):**

```markdown
You are the REPLICATION AGENT for "{{STYLE_NAME}}".

## CORE INVARIANTS (MUST PRESERVE):
{{CORE_INVARIANTS}}

## FULL STYLE PROFILE:
```json
{{STYLE_PROFILE}}
```

## FEEDBACK HISTORY:
{{FEEDBACK_HISTORY}}

## TRAITS TO EMPHASIZE:
{{EMPHASIZE_TRAITS}}

## TRAITS THAT WORK WELL:
{{PRESERVE_TRAITS}}
```

**Substitution Code:**

```python
def build_system_prompt(
    style_profile: StyleProfile,
    feedback_history: list[dict],
) -> str:
    template = self._load_prompt()  # Read generator.md

    # Format core invariants
    invariants_text = "\n".join(f"- {inv}" for inv in style_profile.core_invariants)

    # Format feedback history
    feedback_lines = []
    for f in feedback_history[-10:]:  # Last 10 iterations
        status = "✓ APPROVED" if f["approved"] else "✗ REJECTED"
        line = f"- Iteration {f['iteration']} [{status}]: {f['notes']}"
        feedback_lines.append(line)
    feedback_text = "\n".join(feedback_lines)

    # Count lost traits (for emphasis)
    lost_counts = Counter()
    for f in feedback_history:
        if f.get("lost_traits"):
            lost_counts.update(f["lost_traits"])

    emphasize_traits = [
        f"- {trait} (lost {count}x)"
        for trait, count in lost_counts.most_common(8)
    ]
    emphasize_text = "\n".join(emphasize_traits) if emphasize_traits else "None identified yet."

    # Substitute into template
    filled_prompt = template.replace("{{STYLE_NAME}}", style_profile.style_name)
    filled_prompt = filled_prompt.replace("{{CORE_INVARIANTS}}", invariants_text)
    filled_prompt = filled_prompt.replace("{{STYLE_PROFILE}}", json.dumps(style_profile.model_dump(), indent=2))
    filled_prompt = filled_prompt.replace("{{FEEDBACK_HISTORY}}", feedback_text)
    filled_prompt = filled_prompt.replace("{{EMPHASIZE_TRAITS}}", emphasize_text)

    return filled_prompt
```

### Prompt Complexity Analysis

**Main Branch:**

| Prompt | Lines | Chars | Complexity | VLM Load |
|--------|-------|-------|------------|----------|
| Extractor | 260 | 6,500 | Medium | OK for llava:7b |
| Critic | 330 | 8,200 | Medium-High | OK for llava:7b |
| Generator | 195 | 4,800 | Medium | OK for llava:7b |

**Feature Branch:**

| Prompt | Lines | Chars | Complexity | VLM Load |
|--------|-------|-------|------------|----------|
| Extractor | 420 | 10,400 | High | Overwhelms llava:7b |
| Critic | 415 | 10,300 | High | Overwhelms llava:7b |
| Generator | 230 | 5,700 | Medium-High | Struggles with llava:7b |

**Complexity Factors:**

1. **Instruction Density:** How many distinct instructions per 1000 chars
2. **Schema Complexity:** Nested JSON depth and field count
3. **Conditional Logic:** If-then rules and special cases
4. **Example Count:** Number of examples provided

**Feature Branch Issues with llava:7b:**

- ❌ Extractor: Feature classification too complex (4 types + examples)
- ❌ Critic: Vectorized corrections too complex (8 directions + examples)
- ❌ Generator: Corrections consumption too complex (magnitude scales + spatial hints)

**Recommendation:**

- Main branch: llava:7b ✅
- Feature branch: llama3.2-vision:11b ✅ (or better)

### Critical Prompt Sections

**1. Identity Lock Protocol (Extractor):**

```markdown
## IDENTITY vs STYLE - Know the Difference:

- IDENTITY (frozen, never changes): WHAT subject, WHERE positioned, HOW structured
- STYLE (refinable, can evolve): colors, textures, lighting quality, rendering technique

## Core Invariants = STRUCTURAL IDENTITY LOCKS:

Example GOOD: "Black cat facing left, centered in frame, whiskers extending horizontally"
Example BAD: "Vivid colors with flowing organic shapes" ← This is style, not identity

If you can change it without changing WHAT the image shows, it's NOT an invariant.
```

**Why Critical:**
- Prevents subject drift (cat → psychedelic vortex)
- Separates identity (frozen) from style (refinable)
- Enables style transfer to new subjects post-training

**2. Profile Update Rules (Critic):**

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

**Why Critical:**
- Prevents VLM from "improving" identity constraints
- Maintains replication target throughout training
- Allows style evolution without subject drift

**3. Recovery Priority (Generator):**

```markdown
## FEEDBACK FROM PREVIOUS ITERATIONS:

**Recovery Priority**: If feedback includes "RECOVERY NEEDED", prioritize fixing
those specific issues over everything else. The previous iteration failed
catastrophically - you must restore what was lost.

**How to Use Feedback:**
- ❌ **Rejected iterations (marked "RECOVERY NEEDED")**: Critical recovery instructions
  - **LOST TRAITS**: Must be restored in your next prompt
  - **CATASTROPHIC failures**: Specific dimensions that broke - restore from approved
  - **Action**: Revert to last approved characteristics, then fix specific failures
```

**Why Critical:**
- Ensures generator reads recovery guidance
- Prioritizes restoration over creativity
- Breaks out of failure cycles

---

## VLM Integration

### Ollama API Client

**Architecture:**

```python
class VLMService:
    def __init__(self):
        self.base_url = settings.ollama_url  # http://localhost:11434
        self.model = settings.vlm_model      # llava:7b or llama3.2-vision:11b

    async def analyze(
        self,
        prompt: str,
        images: list[str],  # Base64 encoded
    ) -> str:
        """Send images + prompt to VLM, get text response."""

        # Format images for Ollama API
        image_data = [
            {
                "data": img_b64,
                "format": "png"
            }
            for img_b64 in images
        ]

        # Build request
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": image_data,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temp for structured output
                "num_ctx": 8192,     # Large context for complex prompts
            }
        }

        # Send to Ollama
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )

        result = response.json()
        return result["response"]
```

**Configuration:**

```python
# For structured JSON output (extraction, critique)
{
    "temperature": 0.1,      # Minimal randomness
    "top_p": 0.9,            # Nucleus sampling
    "num_ctx": 8192,         # Large context window
    "repeat_penalty": 1.0,   # No repetition penalty (structured output)
}

# For creative prompt generation (agent)
{
    "temperature": 0.7,      # More creative
    "top_p": 0.95,
    "num_ctx": 4096,         # Smaller context OK
}
```

### Response Parsing

**JSON Extraction Pipeline:**

```python
def _parse_json_response(response: str, fallback_profile: StyleProfile) -> dict:
    """Extract JSON from VLM response with fallback."""

    parsed = None

    # 1. Try direct JSON parsing
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from markdown code block
    if not parsed:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
            except:
                pass

    # 3. Try finding raw JSON object (greedy)
    if not parsed:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except:
                pass

    # 4. Build result with defaults + merge parsed
    result = {
        "match_scores": {
            "palette": 70,
            "line_and_shape": 70,
            "texture": 70,
            "lighting": 70,
            "composition": 70,
            "motifs": 70,
            "overall": 70,
        },
        "preserved_traits": [],
        "lost_traits": [],
        "interesting_mutations": [],
        "updated_style_profile": fallback_profile.model_dump(),
    }

    if parsed:
        # Deep merge parsed into result
        result.update(parsed)

    return result
```

**Error Handling:**

1. **Malformed JSON:** Fallback to defaults, log warning, continue
2. **Missing fields:** Merge with defaults (partial update OK)
3. **Type errors:** Coerce types (list → dict, string → int)
4. **Timeout:** Retry once, then fail gracefully

### VLM Model Comparison

| Model | Params | Context | Speed | JSON Accuracy | Feature Branch |
|-------|--------|---------|-------|---------------|----------------|
| llava:7b | 7B | 4K | Fast (2-5s) | Good | ❌ Too simple |
| llama3.2-vision:11b | 11B | 8K | Medium (5-10s) | Excellent | ✅ Recommended |
| llama3.2-vision:90b | 90B | 8K | Slow (20-40s) | Excellent | ✅ Overkill |
| Claude 3.5 Sonnet (API) | ? | 200K | Medium (3-8s) | Perfect | ✅ Best (untested) |

**Recommendation:**
- Main branch: llava:7b (production)
- Feature branch: llama3.2-vision:11b (experimental)
- Future: Claude 3.5 Sonnet API (when cost acceptable)

---

## State Management

### Database Schema

**Sessions Table:**

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mode TEXT NOT NULL,  -- 'training' | 'auto'
    status TEXT NOT NULL,  -- 'created' | 'extracting' | 'active' | 'completed'
    original_image_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**StyleProfiles Table (Versioned):**

```sql
CREATE TABLE style_profiles (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    profile_json TEXT NOT NULL,  -- Serialized StyleProfile
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE,
    UNIQUE (session_id, version)
);
```

**Iterations Table:**

```sql
CREATE TABLE iterations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    iteration_num INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    prompt_used TEXT NOT NULL,
    scores_json TEXT NOT NULL,  -- Serialized match_scores dict
    preserved_traits TEXT,  -- JSON list
    lost_traits TEXT,  -- JSON list
    approved BOOLEAN,  -- NULL = pending, TRUE = approved, FALSE = rejected
    feedback_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE,
    UNIQUE (session_id, iteration_num)
);
```

**TrainedStyles Table:**

```sql
CREATE TABLE trained_styles (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    style_name TEXT NOT NULL,
    description TEXT,
    style_profile_json TEXT NOT NULL,  -- Final converged StyleProfile
    iteration_count INTEGER NOT NULL,
    final_scores_json TEXT NOT NULL,  -- Final dimension scores
    sample_image_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
);
```

### Profile Versioning

**Version Management:**

```python
def save_style_profile(
    session_id: str,
    profile: StyleProfile,
    version: int | None = None
) -> int:
    """Save style profile with automatic versioning."""

    if version is None:
        # Auto-increment version
        latest = db.query(DBStyleProfile).filter_by(
            session_id=session_id
        ).order_by(DBStyleProfile.version.desc()).first()

        version = (latest.version + 1) if latest else 1

    # Save new version
    db_profile = DBStyleProfile(
        id=str(uuid.uuid4()),
        session_id=session_id,
        version=version,
        profile_json=profile.model_dump_json(),
        created_at=datetime.utcnow()
    )

    db.add(db_profile)
    db.commit()

    return version
```

**Version Retrieval:**

```python
def get_style_profile(session_id: str, version: int | None = None) -> StyleProfile:
    """Get style profile by version (latest if not specified)."""

    query = db.query(DBStyleProfile).filter_by(session_id=session_id)

    if version is None:
        # Get latest
        db_profile = query.order_by(DBStyleProfile.version.desc()).first()
    else:
        # Get specific version
        db_profile = query.filter_by(version=version).first()

    if not db_profile:
        raise ValueError(f"No profile found for session {session_id} version {version}")

    return StyleProfile.model_validate_json(db_profile.profile_json)
```

**Reversion on Rejection:**

```python
def revert_to_last_approved_profile(session_id: str) -> StyleProfile:
    """Revert to last approved profile version."""

    # Get all approved iterations
    approved_iterations = db.query(Iteration).filter_by(
        session_id=session_id,
        approved=True
    ).order_by(Iteration.iteration_num.desc()).all()

    if not approved_iterations:
        # No approved iterations, use v1 (extraction)
        return get_style_profile(session_id, version=1)

    # Get profile version corresponding to last approved iteration
    last_approved = approved_iterations[0]
    version = last_approved.iteration_num + 1  # Profile updated after iteration

    return get_style_profile(session_id, version=version)
```

### File System Organization

```
outputs/
├── {session_id_1}/
│   ├── original.png
│   ├── iteration_001.png
│   ├── iteration_002.png
│   ├── iteration_003.png
│   ├── ...
│   └── auto_improve_debug.txt
├── {session_id_2}/
│   ├── original.png
│   ├── ...
└── ...
```

**File Naming:**

- Original: `original.png`
- Iterations: `iteration_{num:03d}.png` (e.g., `iteration_007.png`)
- Debug log: `auto_improve_debug.txt`

**Cleanup on Delete:**

```python
def delete_session(session_id: str):
    """Delete session and all associated data."""

    # 1. Delete from database (cascades to profiles, iterations)
    session = db.query(Session).filter_by(id=session_id).first()
    db.delete(session)
    db.commit()

    # 2. Delete file system directory
    session_dir = Path(settings.outputs_dir) / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
```

---

## Error Handling

### Error Categories

**1. VLM Errors:**

- Connection refused (Ollama not running)
- Timeout (slow model, complex prompt)
- Malformed JSON response
- Missing required fields
- Type errors in response

**2. ComfyUI Errors:**

- Connection refused (ComfyUI not running)
- Workflow execution failure
- Image generation timeout
- Invalid workflow schema

**3. Database Errors:**

- Database locked (concurrent writes)
- Constraint violation (duplicate key)
- Foreign key violation

**4. Validation Errors:**

- Pydantic schema validation
- Invalid enum values
- Missing required fields

### Error Handling Strategy

**1. Graceful Degradation:**

```python
try:
    # Try VLM extraction
    profile = await extractor.extract_style(image_b64)
except VLMError as e:
    # Fallback to defaults
    logger.error(f"VLM extraction failed: {e}")
    profile = StyleProfile(
        style_name="Extracted Style",
        core_invariants=[],
        palette=default_palette,
        # ... minimal defaults
    )
```

**2. Retry with Exponential Backoff:**

```python
async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0
) -> Any:
    """Retry function with exponential backoff."""

    for attempt in range(max_retries):
        try:
            return await func()
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == max_retries - 1:
                raise

            delay = initial_delay * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
            await asyncio.sleep(delay)
```

**3. Type Coercion:**

```python
# Handle VLM returning wrong type
if isinstance(registry["features"], list):
    logger.warning("VLM returned features as list, coercing to dict")
    registry["features"] = {}

# Handle string scores instead of int
if isinstance(scores["overall"], str):
    scores["overall"] = int(scores["overall"])
```

**4. Fallback to Defaults:**

```python
result = {
    "match_scores": {
        "palette": 70,  # Neutral default
        "overall": 70,
    },
    "preserved_traits": [],
    "lost_traits": [],
}

if parsed:
    # Merge parsed data
    result.update(parsed)

return result
```

### Error Logging

**Structured Logging:**

```python
import logging

logger = logging.getLogger(__name__)

# Configure
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# Usage
logger.info(f"Starting iteration {iteration_num}")
logger.warning(f"VLM returned unexpected format: {response[:100]}")
logger.error(f"Critique failed: {e}", exc_info=True)
```

**WebSocket Logging:**

```python
async def log(message: str, level: str = "info", stage: str = "general"):
    """Log to console and WebSocket."""

    # Console
    logger.info(f"[{stage}] {message}")

    # WebSocket broadcast
    if session_id:
        await manager.broadcast_log(session_id, message, level, stage)
```

### Debug Logging

**Auto-Improve Debug File:**

Each auto-training session creates `auto_improve_debug.txt`:

```
================================================================================
AUTO-IMPROVE DEBUG LOG
Session: a9349b1d-f23e-4441-beb2-0365e85a2808
Subject: centered
Target Score: 85, Max Iterations: 10
Started: 2025-12-05T19:07:51
================================================================================

ORIGINAL STYLE EXTRACTION
Style Name: Cat Watercolor
Core Invariants:
  - Black cat facing left, centered in frame
  - Circular boundary containing subject

============================================================
ITERATION 1
============================================================

Feedback History: 0 approved, 0 rejected
Image Generation Prompt: ...

VLM Critique Analysis:
Overall Score: 70
Preserved Traits: [...]
Lost Traits: [...]

Decision: PASS (Baseline) - First iteration

============================================================
ITERATION 2
============================================================

Weighted Net Progress: +15.0 (strong≥3.0, weak≥1.0)
Decision: PASS (Tier 2 - Strong Progress)
...
```

**Benefits:**
- Complete iteration history
- Weighted delta calculations visible
- Decision reasoning transparent
- Debugging failed training runs

---

## Performance Optimization

### VLM Response Caching

**Problem:** Repeated VLM calls with same inputs

**Solution:** Cache responses with TTL

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def cached_vlm_analyze(prompt_hash: str, image_hash: str) -> str:
    """Cache VLM responses for identical inputs."""
    # Actual implementation calls vlm_service.analyze()
    pass

async def analyze_with_cache(prompt: str, images: list[str]) -> str:
    # Hash inputs
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    image_hash = hashlib.sha256(images[0].encode()).hexdigest()

    # Try cache
    cached = cached_vlm_analyze(prompt_hash, image_hash)
    if cached:
        return cached

    # Miss - call VLM
    result = await vlm_service.analyze(prompt, images)

    # Store in cache
    cached_vlm_analyze.cache_info()  # Update stats

    return result
```

**Benefits:**
- Faster iteration in development
- Reduced Ollama load
- Deterministic testing

**Limitations:**
- Temperature > 0 makes caching less effective
- Cache invalidation on prompt changes

### Parallel Processing

**Problem:** Sequential operations are slow

**Solution:** Run independent operations concurrently

```python
import asyncio

# Sequential (slow)
color_data_original = await extract_colors(original_image)
color_data_generated = await extract_colors(generated_image)

# Parallel (fast)
color_data_original, color_data_generated = await asyncio.gather(
    extract_colors(original_image),
    extract_colors(generated_image)
)
```

**Applied in:**

- Color extraction (original + generated in parallel)
- Multiple session queries
- Batch prompt writing

### Database Connection Pooling

**Problem:** Opening new connection for each query

**Solution:** SQLAlchemy connection pool

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,          # Max connections
    max_overflow=20,       # Extra connections if pool full
    pool_timeout=30,       # Wait up to 30s for connection
    pool_pre_ping=True,    # Verify connections before use
)
```

### Image Compression

**Problem:** Large PNG files (2-5MB per image)

**Solution:** Optimize PNG compression

```python
from PIL import Image

def save_optimized_png(image: Image.Image, path: Path):
    """Save PNG with optimized compression."""
    image.save(
        path,
        format="PNG",
        optimize=True,         # Enable optimization
        compress_level=9,      # Max compression
    )
```

**Savings:**
- Before: 2-5MB per image
- After: 1-3MB per image
- 30-40% reduction

---

## Design Decisions

### Why SQLite over PostgreSQL?

**Pros:**
- ✅ Zero configuration
- ✅ Single file database
- ✅ Perfect for local development
- ✅ Easy backup (copy file)
- ✅ No server process needed

**Cons:**
- ⚠️ Concurrent writes limited
- ⚠️ No network access
- ⚠️ Database locking possible

**Decision:** SQLite for MVP, migrate to PostgreSQL if needed

**Migration Path:**

```python
# Change DATABASE_URL in .env
DATABASE_URL=postgresql://user:pass@localhost/refine_agent

# SQLAlchemy is database-agnostic
# No code changes needed!
```

### Why Base64 Image Transport?

**Pros:**
- ✅ No file path dependencies
- ✅ Works across network boundaries
- ✅ Easy to embed in JSON
- ✅ Direct VLM API compatibility

**Cons:**
- ⚠️ 33% size increase (Base64 encoding)
- ⚠️ JSON payload size

**Decision:** Base64 for simplicity and portability

**Alternative Considered:** Presigned URLs (S3)
- Pro: No size overhead
- Con: Requires cloud storage
- Con: Temporary URL management

### Why WebSocket for Progress?

**Pros:**
- ✅ Real-time updates
- ✅ Bidirectional communication
- ✅ Low latency
- ✅ Perfect for long-running operations

**Cons:**
- ⚠️ Connection management complexity
- ⚠️ Reconnection handling

**Decision:** WebSocket for live progress, REST for CRUD

**Alternative Considered:** Server-Sent Events (SSE)
- Pro: Simpler (HTTP-based)
- Con: Unidirectional only
- Con: Limited browser support

### Why Pydantic over Dataclasses?

**Pros:**
- ✅ Automatic validation
- ✅ JSON serialization built-in
- ✅ Type coercion
- ✅ Rich error messages
- ✅ Schema generation (OpenAPI)

**Cons:**
- ⚠️ Slightly slower than dataclasses
- ⚠️ More verbose

**Decision:** Pydantic for safety and validation

**Example:**

```python
# Pydantic (chosen)
class StyleProfile(BaseModel):
    style_name: str
    core_invariants: list[str]
    palette: PaletteSchema

profile = StyleProfile(**data)  # Validates + coerces types

# Dataclass (rejected)
@dataclass
class StyleProfile:
    style_name: str
    core_invariants: list[str]
    palette: PaletteSchema

profile = StyleProfile(**data)  # No validation!
```

### Why Mechanical Baseline Construction?

**Problem:** VLM injects style adjectives into structural baseline

```python
# VLM output (contaminated):
suggested_test_prompt = "flowing organic shapes with deep navy colors and soft orange highlights"

# This is STYLE interpretation, not STRUCTURE
```

**Solution:** Programmatically build baseline from structural fields

```python
# Mechanical construction (pure structure):
mechanical_baseline = f"{original_subject}, {framing}, {structural_notes}"
# Result: "Black cat facing left, centered in frame, circular framing, whiskers extending horizontally"

# Zero style adjectives!
```

**Benefits:**
- ✅ Zero hallucination risk
- ✅ Deterministic output
- ✅ Reliable replication target
- ✅ VLM output serves as validation/fallback

**Decision:** Always use mechanical construction for identity baseline

---

## Appendix

### File Structure Reference

```
refine_agent/
├── backend/
│   ├── main.py                    # FastAPI app entry
│   ├── config.py                  # Settings (Pydantic)
│   ├── database.py                # SQLAlchemy setup
│   ├── websocket.py               # WebSocket manager
│   │
│   ├── models/
│   │   ├── schemas.py             # Pydantic models
│   │   └── db_models.py           # SQLAlchemy ORM
│   │
│   ├── routers/
│   │   ├── sessions.py            # Session CRUD
│   │   ├── extraction.py          # Style extraction endpoint
│   │   ├── iteration.py           # Training loop endpoints
│   │   └── styles.py              # Trained styles endpoints
│   │
│   ├── services/
│   │   ├── vlm.py                 # Ollama client
│   │   ├── comfyui.py             # ComfyUI client
│   │   ├── extractor.py           # Style extraction
│   │   ├── critic.py              # Style critique
│   │   ├── agent.py               # Prompt builder
│   │   ├── auto_improver.py       # Training loop logic
│   │   ├── prompt_writer.py       # Style application
│   │   ├── storage.py             # File I/O
│   │   └── color_extractor.py     # PIL color analysis
│   │
│   └── prompts/
│       ├── extractor.md           # Extraction prompt
│       ├── critic.md              # Critique prompt
│       └── generator.md           # Generator prompt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   │
│   │   ├── api/
│   │   │   └── client.ts          # API client + WebSocket
│   │   │
│   │   ├── components/
│   │   │   ├── ImageUpload.tsx
│   │   │   ├── SideBySide.tsx
│   │   │   ├── StyleProfileView.tsx
│   │   │   ├── FeedbackPanel.tsx
│   │   │   ├── SessionList.tsx
│   │   │   └── ProgressIndicator.tsx
│   │   │
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── Session.tsx
│   │   │   ├── StyleLibrary.tsx
│   │   │   └── PromptWriter.tsx
│   │   │
│   │   └── types/
│   │       └── index.ts           # TypeScript types
│   │
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
│
├── outputs/                       # Runtime generated
│   └── {session_id}/
│       ├── original.png
│       ├── iteration_*.png
│       └── auto_improve_debug.txt
│
├── refine_agent.db                # SQLite database
├── .env                           # Configuration
├── requirements.txt
├── DOCUMENTATION.md               # This file
├── CHANGELOG.md
├── ARCHITECTURE.md                # Deep technical docs
└── README.md
```

### Tech Stack Summary

**Backend:**
- FastAPI 0.104.1
- SQLAlchemy 2.0.23
- Pydantic 2.5.0
- Pillow 10.1.0
- httpx 0.25.1
- websockets 12.0

**Frontend:**
- React 18.2.0
- TypeScript 5.2.2
- Vite 5.0.0
- TailwindCSS 3.3.5
- @tanstack/react-query 5.8.4

**AI/ML:**
- Ollama (VLM server)
- llava:7b / llama3.2-vision:11b
- ComfyUI (image generation)
- Flux models (Stable Diffusion successor)

**Storage:**
- SQLite 3.x
- File system (PNG images)

---

*Architecture document last updated: 2025-12-05*
