# Style Refine Agent - System Architecture Documentation

## Overview

The Style Refine Agent extracts visual style from a reference image, iteratively refines it through generation + critique cycles, and produces a reusable style profile that can be applied to new subjects.

---

## Phase 1: Style Extraction

### Input
- User uploads reference image (base64)
- Optional: User provides `style_hints` (text describing what the style IS and ISN'T)

### Components

#### 1.1 Color Extraction
**File:** `backend/services/color_extractor.py`

**Process:**
1. Decode base64 image to PIL Image
2. Use PIL's median cut quantization to extract 16-color palette
3. Sort colors by frequency
4. Select top 3 as dominant colors
5. Select next 2 as accent colors
6. Calculate saturation level (low/medium/high) based on HSV values
7. Calculate value range (e.g., "mid-tones with soft highlights")
8. Assign descriptive color names based on hue/saturation/value

**Output:**
```python
{
    "dominant_colors": ["#hex1", "#hex2", "#hex3"],
    "accents": ["#hex1", "#hex2"],
    "color_descriptions": ["vivid red", "soft amber", ...],
    "saturation": "medium-high",
    "value_range": "bright with deep shadows"
}
```

#### 1.2 VLM Style Analysis
**File:** `backend/services/extractor.py`
**Prompt:** `backend/prompts/extractor.md`
**Model:** `llama3.2-vision:11b`

**Extraction Prompt Instructions:**
- Describe at highest level of abstraction
- Focus on HOW things look (visual properties), not WHAT things are (object identification)
- Avoid categorical labels (e.g., "mandala", "impressionist")
- Core invariants should describe broad visual patterns, not subject-specific details
- Motifs start empty (will be discovered during training)

**VLM Extracts:**
```python
{
    "style_name": str,  # 3-5 word descriptive name
    "core_invariants": [str],  # Broad visual patterns
    "palette": {
        "dominant_colors": [str],  # Overridden by PIL
        "accents": [str],
        "color_descriptions": [str],
        "saturation": str,
        "value_range": str
    },
    "line_and_shape": {
        "line_quality": str,
        "shape_language": str,
        "geometry_notes": str
    },
    "texture": {
        "surface": str,
        "noise_level": str,
        "special_effects": [str]
    },
    "lighting": {
        "lighting_type": str,
        "shadows": str,
        "highlights": str
    },
    "composition": {
        "camera": str,
        "framing": str,
        "depth": str,
        "negative_space_behavior": str,
        "structural_notes": str
    },
    "motifs": {
        "recurring_elements": [],  # Empty initially
        "forbidden_elements": []   # Empty initially
    },
    "original_subject": str,  # Literal description of what's depicted
    "suggested_test_prompt": str,  # Replication baseline (structural-only)
    "image_description": str  # Natural language description (added later)
}
```

**Retry Logic:**
- Max 3 attempts if JSON parsing fails
- 2-second pause between retries
- If all retries fail, raises `RuntimeError`

**If VLM call succeeds but JSON invalid:**
- Tries to parse direct JSON
- Tries to extract from markdown code block
- Tries greedy regex match `{.*}`
- If all fail, raises `ValueError` with response preview

#### 1.3 Baseline Validation
**File:** `backend/services/extractor.py` (lines 203-297)

**Purpose:** Validate `suggested_test_prompt` contains no style contamination

**Process:**
1. Extract `suggested_test_prompt` from VLM response
2. Send validation prompt to VLM (text-only, no images):
   ```
   Analyze this description and determine if it contains ONLY
   structural/compositional information, or if it also includes
   style attributes.

   Description: "{suggested_test_prompt}"

   Structural (ALLOWED): objects, positions, arrangements, spatial relationships
   Style (NOT ALLOWED): colors, lighting, textures, moods, rendering techniques

   Output JSON: {
     "is_structural_only": bool,
     "contamination_found": [str],
     "reason": str
   }
   ```
3. Parse validation response
4. **If `is_structural_only: true`:** Keep VLM baseline
5. **If `is_structural_only: false`:** Build mechanical baseline:
   ```python
   baseline_parts = [
       original_subject,
       composition.framing,
       composition.structural_notes
   ]
   suggested_test_prompt = ", ".join(baseline_parts)
   ```

**Fallback:**
If validation VLM call fails (error, timeout, invalid JSON), build mechanical baseline

#### 1.4 Color Override
**File:** `backend/services/extractor.py` (lines 188-195)

After VLM extraction completes, palette fields are replaced with PIL-extracted colors:
```python
profile_dict["palette"]["dominant_colors"] = pil_colors["dominant_colors"]
profile_dict["palette"]["accents"] = pil_colors["accents"]
profile_dict["palette"]["color_descriptions"] = pil_colors["color_descriptions"]
profile_dict["palette"]["saturation"] = pil_colors["saturation"]
profile_dict["palette"]["value_range"] = pil_colors["value_range"]
```

#### 1.5 Image Description Extraction
**File:** `backend/services/extractor.py` (lines 299-310)

Separate VLM call to generate natural language description:
```python
prompt = """Describe this image as if writing a prompt for an AI image generator.

Focus on:
1. Subject matter and composition
2. Art style and technique
3. Color palette and mood
4. Lighting and atmosphere
5. Distinctive visual elements or textures

Write a single detailed paragraph (50-100 words).
Do NOT start with "This image shows" - write as direct prompt.
Output ONLY the description."""
```

Uses `force_json=False` to get natural prose, not JSON.

Stores result in `profile_dict["image_description"]`.

### Output: StyleProfile v1

Stored in database table `style_profiles` with:
- `session_id` - Foreign key to session
- `version` - Integer (starts at 1)
- `profile_json` - Full StyleProfile as JSON
- `created_at` - Timestamp

---

## Phase 2: Training Iteration

### 2.1 Image Generation
**File:** `backend/services/comfyui.py`

**Input:**
- Prompt (string) - Built from StyleProfile + subject
- Workflow (dict) - ComfyUI workflow JSON

**Process:**
1. Send POST to ComfyUI `/prompt` endpoint with workflow
2. Poll `/history/{prompt_id}` until complete
3. Extract output image
4. Convert to base64
5. Return base64 string

**Prompt Construction:**
Uses `suggested_test_prompt` from current StyleProfile as base.

### 2.2 Critique
**File:** `backend/services/critic.py`
**Prompt:** `backend/prompts/critic.md`
**Model:** `llama3.2-vision:11b`

**Inputs:**
1. **Original image** (base64) - Reference image
2. **Generated image** (base64) - Iteration output
3. **Current StyleProfile** (JSON) - Full profile
4. **Color analysis** (text) - PIL comparison of palettes
5. **Image description** (text) - Natural language description of original
6. **Creativity level** (0-100) - Controls mutation allowance

**Color Analysis Generation:**
```python
def _compare_colors(target_colors, generated_colors, original_extracted, generated_extracted):
    # Lists target vs generated hex colors
    # Calculates color distance (Euclidean in RGB space)
    # Assigns quality: EXCELLENT (<50), GOOD (<100), MODERATE (<150), POOR (>150)
    # Compares saturation and value range
    return formatted_text
```

**Critic Prompt Template Variables:**
- `{{CREATIVITY_LEVEL}}` - 0-100 value
- `{{STYLE_PROFILE}}` - JSON dump of current profile
- `{{COLOR_ANALYSIS}}` - Formatted color comparison text
- `{{IMAGE_DESCRIPTION}}` - Natural language description

**VLM Returns:**
```python
{
    "match_scores": {
        "palette": 0-100,
        "line_and_shape": 0-100,
        "texture": 0-100,
        "lighting": 0-100,
        "composition": 0-100,
        "motifs": 0-100,
        "overall": 0-100
    },
    "preserved_traits": [str],  # What matched well
    "lost_traits": [str],  # What drifted
    "interesting_mutations": [str],  # New characteristics
    "updated_style_profile": {
        # Full StyleProfile with edits
    }
}
```

**Retry Logic:**
- Max 3 attempts if JSON parsing fails
- 2-second pause between retries
- Catches `ValueError` specifically (parsing errors)
- Re-sends entire VLM request on each retry

**Post-Processing:**
1. Override palette in `updated_style_profile` with PIL colors from generated image:
   ```python
   updated_profile["palette"]["dominant_colors"] = generated_colors["dominant_colors"]
   updated_profile["palette"]["accents"] = generated_colors["accents"]
   updated_profile["palette"]["color_descriptions"] = generated_colors["color_descriptions"]
   ```
2. Fix type mismatches (VLM sometimes returns lists for string fields):
   - `line_and_shape.geometry_notes`: list → comma-joined string
   - `composition.structural_notes`: list → comma-joined string
   - `texture.special_effects`: string → comma-split list

**If all retries fail:**
Raises `ValueError` with response preview (no fallback scores).

### 2.3 Weighted Evaluation
**File:** `backend/services/auto_improver.py` (lines 308-427)

**Dimension Weights:**
```python
{
    "palette": 1.0,
    "line_and_shape": 2.0,
    "texture": 1.5,
    "lighting": 1.5,
    "composition": 2.0,
    "motifs": 0.8,
}
```

**Historical Tracking:**
Maintains running history of scores per dimension:
```python
dimension_history = {
    "palette": [70, 75, 80],
    "line_and_shape": [65, 70, 75],
    # ...
}
```

**Calculation Steps:**

1. **Calculate historical average** for each dimension:
   ```python
   avg = sum(history) / len(history)
   ```

2. **Calculate delta** (current - average):
   ```python
   delta = current_score - avg
   ```

3. **Apply weight**:
   ```python
   weighted_delta = delta * weight
   ```

4. **Sum weighted deltas**:
   ```python
   weighted_net_progress = sum(weighted_deltas.values())
   ```

**Thresholds:**
- `strong_net_progress_threshold`: 3.0
- `weak_net_progress_threshold`: 1.0
- `catastrophic_threshold`: -20 (dimension drops ≥20 points)

**Evaluation Tiers:**

**Tier 1: Quality Targets**
```python
if overall_score >= 70 and all(dim >= 55 for dim in dimensions.values()):
    return APPROVE, "PASS (Tier 1 - Quality Targets)"
```

**Tier 2: Strong Progress**
```python
if weighted_net_progress >= 3.0:
    return APPROVE, "PASS (Tier 2 - Strong Progress)"
```

**Tier 2b: Net Progress (Dimension Balance)**
```python
improved_dims = [d for d, delta in deltas.items() if delta >= 2]
regressed_dims = [d for d, delta in deltas.items() if delta <= -2]

if len(improved_dims) > len(regressed_dims):
    return APPROVE, "PASS (Tier 2b - Net Progress)"
```

**Tier 3: Recovery Mode**
```python
if in_recovery_mode and catastrophic_dims_improving:
    return APPROVE, "PASS (Tier 3 - Recovery Mode)"
```

**Rejection Criteria:**
```python
# Check for catastrophic regression
for dim, delta in deltas.items():
    if delta <= -20:
        return REJECT, "FAIL: Catastrophic regression in {dim}"

# Check for negative progress
if weighted_net_progress < 0:
    return REJECT, "FAIL: Weighted Δ={weighted_net_progress} (negative)"

# Check for weak progress
if weighted_net_progress < 1.0:
    return REJECT, "FAIL: Weighted Δ={weighted_net_progress} below threshold"
```

### 2.4 Profile Update
**File:** `backend/services/auto_improver.py` (lines 428-545)

**If approved:**
```python
# Increment version
new_version = current_version + 1

# Create new StyleProfileDB record
profile_db = StyleProfileDB(
    session_id=session_id,
    version=new_version,
    profile_json=updated_profile_dict
)
db.add(profile_db)

# Update session
session.current_style_version = new_version
```

**If rejected:**
```python
# Do NOT update profile
# Generate recovery guidance

guidance = {
    "lost_traits": critique.lost_traits,
    "avoid_elements": [elements that caused issues],
    "emphasis_areas": [dimensions that regressed]
}

# Add to feedback history for next iteration
feedback_history.append(guidance)
```

### 2.5 Iteration Storage
**Database:** `iterations` table

```python
iteration = Iteration(
    session_id=session_id,
    iteration_num=N,
    image_path="outputs/{session_id}/iteration_{N:03d}.png",
    prompt_used=prompt_text,
    scores_json={
        "palette": 85,
        "line_and_shape": 90,
        # ...
        "overall": 87
    },
    critique_json={
        "match_scores": {...},
        "preserved_traits": [...],
        "lost_traits": [...],
        "interesting_mutations": [...],
        "updated_style_profile": {...}
    },
    feedback=user_feedback_or_auto_reason,
    approved=True/False
)
```

Images saved to disk: `outputs/{session_id}/iteration_{num:03d}.png`

---

## Phase 3: Auto-Improve Loop

### 3.1 Loop Structure
**File:** `backend/routers/iteration.py` (`/auto-improve` endpoint)

**Parameters:**
```python
{
    "session_id": str,
    "subject": str,  # What to generate
    "max_iterations": int,  # e.g., 10
    "target_score": int,  # e.g., 95
    "creativity_level": int  # 0-100
}
```

**Loop Logic:**
```python
for iteration_num in range(1, max_iterations + 1):
    # Generate image
    image_b64 = await generate_image(profile, subject)

    # Critique
    critique = await critic.critique(
        original_image_b64,
        image_b64,
        profile,
        creativity_level
    )

    # Evaluate
    should_approve, reason = await evaluate(
        critique.match_scores,
        historical_scores
    )

    # Save iteration
    iteration = save_iteration(
        image_b64,
        scores,
        critique,
        approved=should_approve
    )

    # Update profile if approved
    if should_approve:
        profile = update_profile(critique.updated_style_profile)

        # Check if target reached
        if critique.match_scores["overall"] >= target_score:
            break

    # Update history
    update_history(critique.match_scores)
```

**Stop Conditions:**
1. `iteration_num >= max_iterations`
2. `overall_score >= target_score`
3. Exception raised (error after retries)
4. User cancellation via WebSocket

### 3.2 Focused Iteration Strategy
**File:** `backend/services/auto_improver.py` (lines 108-197)

**Weak Dimension Detection:**
```python
weak_dimensions = [
    dim for dim, score in scores.items()
    if score < 70 and dim != "overall"
]
```

**For each weak dimension, generate guidance:**
```python
guidance_map = {
    "palette": f"Current: {profile.palette.color_descriptions}. Increase accuracy.",
    "lighting": f"Current: {profile.lighting.lighting_type}. Match this precisely.",
    "texture": f"Current: {profile.texture.surface}. Replicate surface quality.",
    "composition": f"Current: {profile.composition.framing}. Match spatial arrangement.",
    "line_and_shape": f"Current: {profile.line_and_shape.line_quality}. Match edge treatment.",
    "motifs": "Ensure recurring visual elements are present."
}

focused_areas = [guidance_map[dim] for dim in weak_dimensions]
```

**Add to prompt:**
```python
if focused_areas:
    prompt += "\n\nFOCUS AREAS (prioritize these):\n"
    for area in focused_areas:
        prompt += f"- {area}\n"
```

### 3.3 Error Handling
**File:** `backend/routers/iteration.py` (lines 1083-1111)

**On exception during iteration:**
```python
except Exception as e:
    error_msg = str(e)
    logger.error(f"Auto-improve iteration failed: {error_msg}\n{traceback}")

    # Broadcast error
    await manager.broadcast_error(session_id, error_msg)

    # Set session status
    session.status = SessionStatus.ERROR.value
    await db.commit()

    # Increment rejected count
    rejected_count += 1

    # Add error result with all fields
    results.append({
        "iteration_num": iteration_num,
        "iteration_id": None,
        "image_b64": None,
        "prompt_used": None,
        "overall_score": None,
        "weak_dimensions": [],
        "focused_areas": [],
        "scores": {},
        "approved": False,
        "eval_reason": f"ERROR: {error_msg}",
        "preserved_traits": [],
        "lost_traits": [],
        "interesting_mutations": [],
        "error": error_msg,
    })

    # Break loop (stop training)
    break
```

**Return structure:**
```python
return {
    "iterations_run": len(results),
    "approved_count": approved_count,
    "rejected_count": rejected_count,
    "results": results,  # List of all iteration results
    "final_score": results[-1].get("overall_score") if results else None,
    "best_score": max([r["overall_score"] for r in approved_results]),
    "target_reached": (best_score >= target_score)
}
```

---

## Phase 4: Finalization

### 4.1 Style Abstraction
**File:** `backend/routers/styles.py` (`/finalize` endpoint)

**Input:**
```python
{
    "session_id": str,
    "name": str,
    "description": str
}
```

**Process:**
1. Load session with latest approved StyleProfile
2. Extract StyleRules from profile:
   ```python
   style_rules = {
       "core_characteristics": profile.core_invariants,
       "positive_descriptors": [
           f"Palette: {', '.join(profile.palette.color_descriptions)}",
           f"Lighting: {profile.lighting.lighting_type}",
           f"Texture: {profile.texture.surface}",
           f"Composition: {profile.composition.framing}",
           f"Line Quality: {profile.line_and_shape.line_quality}",
       ],
       "negative_descriptors": profile.motifs.forbidden_elements,
       "motifs": profile.motifs.recurring_elements
   }
   ```
3. Create TrainedStyle record:
   ```python
   trained_style = TrainedStyle(
       name=name,
       description=description,
       style_profile_json=profile.model_dump(),
       style_rules_json=style_rules,
       training_summary_json={
           "iterations": session.iteration_count,
           "final_score": final_score,
           "source_session_id": session_id
       },
       thumbnail_b64=resized_original_image,
       source_session_id=session_id,
       iterations_trained=session.iteration_count,
       final_score=final_score
   )
   ```

**Database:** `trained_styles` table

### 4.2 Prompt Writing
**File:** `backend/services/prompt_writer.py`

**Input:**
```python
{
    "style_id": str,
    "subject": str,
    "additional_context": str | None,
    "include_negative": bool,
    "variation_level": int,  # 0-100
    "use_creative_rewrite": bool  # Default: False
}
```

#### Mechanical Assembly (Default)
**File:** `backend/services/prompt_writer.py` (lines 95-156)

**Process:**
```python
def _mechanical_assembly(style_profile, style_rules, subject, variation_level):
    parts = [subject]

    # Add core characteristics
    if style_rules.core_characteristics:
        parts.extend(style_rules.core_characteristics)

    # Add positive descriptors
    if style_rules.positive_descriptors:
        parts.extend(style_rules.positive_descriptors)

    # Add motifs
    if style_rules.motifs:
        parts.extend(style_rules.motifs)

    # Join with commas
    positive_prompt = ", ".join(parts)

    # Build negative prompt
    negative_prompt = ", ".join(style_rules.negative_descriptors)

    return positive_prompt, negative_prompt
```

**Variation Handling:**
```python
if variation_level > 0:
    # Shuffle order
    random.shuffle(parts)

    # Apply synonym substitution based on variation_level
    # (not currently implemented)
```

#### Creative Rewrite (Optional)
**File:** `backend/services/prompt_writer.py` (lines 158-197)

**Process:**
```python
# Build mechanical prompt first
mechanical_prompt, mechanical_negative = _mechanical_assembly(...)

# Send to VLM for creative rewriting
rewrite_prompt = f"""Rewrite this image generation prompt to be more natural and flowing
while preserving all style information.

Original: {mechanical_prompt}

Requirements:
- Keep all style attributes (colors, lighting, texture, composition)
- Make it read naturally as a single coherent prompt
- Do not add new elements
- Do not remove style information

Output only the rewritten prompt, no explanation."""

creative_prompt = await vlm_service.generate_text(
    prompt=rewrite_prompt,
    use_text_model=True,  # Use fast text model, not vision
    force_json=False
)

return creative_prompt, mechanical_negative
```

**Fallback:**
If creative rewrite fails or returns invalid prompt, use mechanical assembly.

**Output:**
```python
{
    "positive_prompt": str,
    "negative_prompt": str,
    "style_used": str,  # Style name
    "variation_level": int
}
```

---

## VLM Service Layer

### Configuration
**File:** `backend/config.py`

```python
vlm_model = "llama3.2-vision:11b"  # Vision model for extraction/critique
text_model = "llama3.2:3b"  # Text model for prompt generation
```

### Retry Logic
**File:** `backend/services/vlm.py` (lines 29-94)

```python
async def analyze(
    prompt: str,
    images: list[str] | None = None,
    system: str | None = None,
    request_id: str | None = None,
    timeout: float = 300.0,
    model: str | None = None,
    force_json: bool = True,
    max_retries: int = 3,
):
    for attempt in range(max_retries):
        try:
            return await _do_analyze(...)
        except asyncio.CancelledError:
            raise  # Don't retry cancellation
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"VLM: Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"VLM: All {max_retries} attempts failed")
                raise
```

**Payload:**
```python
{
    "model": model_name,
    "messages": [
        {"role": "system", "content": system_prompt},  # Optional
        {
            "role": "user",
            "content": prompt,
            "images": [base64_img1, base64_img2]  # Optional
        }
    ],
    "stream": False,
    "format": "json"  # If force_json=True
}
```

**API Call:**
```
POST {ollama_url}/api/chat
```

**Response:**
```python
{
    "message": {
        "content": "..." # VLM response text
    }
}
```

---

## Database Schema

### Sessions
```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT NOT NULL,
    mode TEXT DEFAULT 'training',  -- training | auto
    status TEXT DEFAULT 'created',  -- created | extracting | ready | training | error
    original_image_path TEXT,
    style_hints TEXT,
    created_at TIMESTAMP
);
```

### StyleProfiles
```sql
CREATE TABLE style_profiles (
    id TEXT PRIMARY KEY,  -- UUID
    session_id TEXT NOT NULL,  -- FK to sessions
    version INTEGER NOT NULL,
    profile_json JSON NOT NULL,  -- Full StyleProfile
    created_at TIMESTAMP
);
```

### Iterations
```sql
CREATE TABLE iterations (
    id TEXT PRIMARY KEY,  -- UUID
    session_id TEXT NOT NULL,  -- FK to sessions
    iteration_num INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    prompt_used TEXT,
    scores_json JSON,  -- Match scores
    critique_json JSON,  -- Full critique result
    feedback TEXT,
    approved BOOLEAN,
    created_at TIMESTAMP
);
```

### TrainedStyles
```sql
CREATE TABLE trained_styles (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT NOT NULL,
    description TEXT,
    style_profile_json JSON NOT NULL,  -- Final StyleProfile
    style_rules_json JSON NOT NULL,  -- StyleRules
    training_summary_json JSON,  -- Training metadata
    thumbnail_b64 TEXT,  -- Small base64 image
    source_session_id TEXT,  -- FK to sessions (nullable)
    iterations_trained INTEGER DEFAULT 0,
    final_score INTEGER,
    tags_json JSON DEFAULT '[]',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

## File Storage Structure

```
outputs/
  {session_id}/
    original.png
    iteration_001.png
    iteration_002.png
    iteration_003.png
    ...
    auto_improve_debug.txt  # Detailed training log
```

---

## WebSocket Events

**Connection:** `/ws/{session_id}`

**Event Types:**
```python
{
    "type": "log",
    "message": str,
    "level": "info" | "warning" | "error" | "success",
    "phase": "extract" | "generate" | "critique" | "summary"
}

{
    "type": "progress",
    "phase": str,
    "percent": 0-100,
    "message": str
}

{
    "type": "complete",
    "session_id": str
}

{
    "type": "error",
    "message": str
}
```

---

## API Endpoints Summary

### Sessions
- `GET /api/sessions` - List all sessions
- `POST /api/sessions` - Create new session (upload image)
- `GET /api/sessions/{id}` - Get session with iterations and profile
- `DELETE /api/sessions/{id}` - Delete session and files
- `DELETE /api/sessions` - Delete all sessions

### Extraction
- `POST /api/extract` - Extract style from session's original image
- `POST /api/extract/reextract` - Re-run extraction (new version)
- `GET /api/extract/{session_id}/profile` - Get style profile (optional version)

### Iteration
- `POST /api/iterate/step` - Run single iteration (manual)
- `POST /api/iterate/feedback` - Submit user feedback on iteration
- `POST /api/iterate/apply` - Apply critique updates to profile
- `POST /api/iterate/auto-improve` - Run N iterations automatically

### Styles (Finalization)
- `POST /api/styles/finalize` - Finalize session into TrainedStyle
- `GET /api/styles` - List all trained styles
- `GET /api/styles/{id}` - Get trained style details
- `POST /api/styles/write-prompt` - Generate prompt from style + subject
- `POST /api/styles/write-and-generate` - Generate prompt + image
- `DELETE /api/styles/{id}` - Delete trained style

### Generation
- `POST /api/generate` - Generate image from prompt (ComfyUI)
