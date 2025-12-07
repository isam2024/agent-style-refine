# Hypothesis-Based Style Extraction - Planning Document

## Current State Analysis

### What We Have (Training Mode)
- Single-pass extraction: VLM analyzes image once, produces one StyleProfile
- StyleProfile treated as ground truth immediately
- Training iterates to make generations fit the initial extraction
- No concept of competing interpretations
- No validation that extraction captured the "right" interpretation
- No ability to revise or branch if extraction was wrong

### Core Problem Identified
**The system has no epistemological layer.**

It cannot:
- Form competing hypotheses
- Express uncertainty
- Test interpretations
- Revise based on evidence
- Retreat from wrong paths

This causes:
- Extraction locks in first interpretation (even if wrong)
- Training tries to force reality to fit extraction
- No recovery if initial extraction missed key aspects
- Subject-style entanglement (no way to test separation)
- Missing negatives ("style NEVER has X" never captured)

### Specific Failure Mode Example

**Grid Image Scenario:**
```
Human sees: "Strict orthogonal grid, ONLY rectangles, NO curves, ALWAYS aligned"

Current system:
1. Extract: "Colorful geometric pattern" ← too vague
2. Generate: Creates something with curves (fits "pattern")
3. Critique: "Lost geometric precision" ← symptom, not diagnosis
4. Never captures: Grid is FUNDAMENTAL, curves are FORBIDDEN

Result: Training wanders, never converges to actual style
```

**What's Missing:**
- No competing hypotheses ("grid" vs "radial" vs "scattered")
- No testing ("does grid interpretation produce consistent results?")
- No negative constraints ("curves break this style")
- No confidence ("80% sure it's grid-based, 20% might be radial")

## Proposed Solution: Hypothesis Mode

### High-Level Concept

Instead of treating extraction as single truth, treat it as **hypothesis generation + testing + selection**:

```
Current (Training Mode):
  Extract Once → Lock as Truth → Train to Fit

Proposed (Hypothesis Mode):
  Generate Multiple Interpretations → Test Each → Select Best → Train (optional)
```

### Key Philosophical Shifts

1. **Extraction produces hypotheses, not facts**
   - "This could be grid-based OR radial OR scattered"
   - Each interpretation is a complete StyleProfile with different emphasis

2. **Confidence is explicit**
   - Every hypothesis has confidence score (0.0-1.0)
   - Evidence increases/decreases confidence
   - Selection based on which interpretation tests best

3. **Testing validates interpretations**
   - Generate samples using each hypothesis
   - Measure consistency with original
   - Hypothesis that produces most consistent results wins

4. **Negative constraints are discovered through testing**
   - "Grid hypothesis: when I add curves, it breaks → curves are forbidden"
   - "Radial hypothesis: when I remove center, it breaks → center is critical"

5. **Subject-style separation is enforced through testing**
   - Test each hypothesis on different subjects
   - Hypothesis must produce consistent style across subjects
   - If it doesn't → interpretation was subject-locked

## MVP Scope Definition

### What We're Building

**New Mode:** "Hypothesis Mode" (separate from existing Training/Auto modes)

**Flow:**
```
1. User uploads image, selects "Hypothesis Mode"
2. System generates 3-5 different style interpretations
3. System tests each interpretation (generates samples)
4. System ranks interpretations by test results
5. User selects best interpretation (or system auto-selects)
6. Selected interpretation becomes StyleProfile
7. Optional: Continue to Training Mode with selected profile
```

### Core Components Needed

#### 1. Multi-Hypothesis Extraction
**Input:** Single reference image
**Output:** 3-5 complete StyleProfile interpretations

**What makes interpretations "different":**
- Hypothesis 1: Emphasizes spatial/geometric organization
- Hypothesis 2: Emphasizes color/lighting treatment
- Hypothesis 3: Emphasizes texture/surface qualities
- (More if needed)

**Each hypothesis includes:**
- Complete StyleProfile (same schema as current)
- Interpretation label: "Grid-based geometric"
- Supporting evidence: Why VLM thinks this interpretation fits
- Uncertain aspects: What VLM is unsure about
- Initial confidence: Start equal (1/N)

#### 2. Hypothesis Testing
**Input:** One hypothesis + reference image
**Output:** Test results + confidence adjustment

**Testing process:**
```
For each hypothesis:
  1. Generate N test images (different subjects)
  2. Measure consistency with reference
  3. Calculate confidence delta
  4. Store test results
```

**Test subjects (for MVP):**
- Generic prompts that vary subject but preserve style
- Examples: "abstract pattern", "landscape", "portrait", "still life"
- Should NOT overlap with reference image subject

**Metrics (for MVP):**
- Visual consistency score (VLM-based comparison)
- Subject independence (does style transfer across subjects?)
- Start simple, add objective metrics later (CLIP, color histograms)

#### 3. Hypothesis Selection
**Input:** All tested hypotheses
**Output:** Selected hypothesis (becomes final StyleProfile)

**Selection criteria:**
```
Automatic:
  - Rank by confidence after testing
  - Select highest confidence if > threshold (e.g., 0.7)
  - If no clear winner, present to user

User-assisted:
  - Show all hypotheses with test results
  - User picks best based on test images
  - User can provide feedback to refine
```

#### 4. Database Schema Extensions
**New tables:**
```sql
hypothesis_sets (
  id,
  session_id,
  hypotheses_json,  -- Full HypothesisSet
  created_at
)

hypothesis_tests (
  id,
  hypothesis_id,
  test_subject,
  generated_image_path,
  scores_json,
  created_at
)
```

**Session changes:**
- Add `mode` field includes "hypothesis"
- Link to hypothesis_sets table

#### 5. API Endpoints
**New routes:**
```
POST /api/hypothesis/extract
  - Generate multiple interpretations
  - Input: session_id
  - Output: HypothesisSet

POST /api/hypothesis/test
  - Test specific hypothesis
  - Input: hypothesis_id, test_subjects[]
  - Output: test results + updated confidence

POST /api/hypothesis/explore
  - Full flow: extract + test all + rank
  - Input: session_id, optional test_subjects
  - Output: ranked hypotheses + selected

POST /api/hypothesis/select
  - User manually selects hypothesis
  - Input: session_id, hypothesis_id
  - Output: StyleProfile (selected hypothesis)

POST /api/hypothesis/to-training
  - Convert selected hypothesis to training session
  - Input: session_id
  - Output: new training session
```

#### 6. Frontend Changes
**Session creation:**
- Add "Hypothesis Mode" option to mode selector
- Explain what hypothesis mode does

**Hypothesis exploration page:**
- Show extraction progress (generating interpretations)
- Display all hypotheses side-by-side
- For each hypothesis:
  - Interpretation label
  - Confidence score
  - Supporting evidence
  - Test images (3-5 per hypothesis)
- Ranking/comparison view
- Selection button

**Optional: Refinement flow:**
- User can reject all hypotheses
- System generates new ones based on feedback
- Iterative refinement before selecting

## What We're NOT Building (Out of Scope for MVP)

### Deferred to Later
1. **Confidence tracking per field** - For MVP, confidence is per-hypothesis, not per-attribute
2. **Branching during training** - Hypothesis mode is pre-training only
3. **Continuous hypothesis revision** - No runtime hypothesis switching during training
4. **Automatic negative constraint extraction** - Will rely on VLM to include negatives in interpretations
5. **Multi-sample training iterations** - Training mode stays single-sample
6. **Objective metrics** - Start with VLM-based scoring, add CLIP/LPIPS later
7. **Covariance modeling** - Dimensions treated independently for MVP
8. **Cross-iteration pattern analysis** - Hypothesis mode doesn't iterate
9. **Embedding-based style representation** - Stay with text/JSON for now
10. **User hypothesis creation** - User can only select, not create custom

### Explicitly NOT Changing
1. **Training Mode** - Keep existing training/auto modes as-is
2. **Extraction prompt** - Current extractor.md stays for training mode
3. **Critique system** - No changes to critic
4. **Weighted evaluation** - Stays the same
5. **Finalization** - No changes to style abstraction
6. **Database schema for existing tables** - Only additions, no modifications

## Open Questions / Decisions Needed

### 1. Number of Hypotheses
**Question:** How many interpretations should we generate?

**Options:**
- Fixed: Always 3 (geometric, color, texture focus)
- Fixed: Always 5 (more coverage)
- Dynamic: 3-5 based on image complexity
- User choice: Let user specify

**Tradeoffs:**
- More hypotheses = better coverage, higher cost
- Fewer hypotheses = faster, might miss right interpretation

**Recommendation needed.**

### 2. Test Subject Selection
**Question:** What subjects should we test with?

**Options:**
- Hardcoded: ["abstract pattern", "landscape", "portrait"]
- Image-aware: Detect original subject type, test with different types
- User-provided: User specifies test subjects
- Generated: VLM suggests test subjects based on image

**Tradeoffs:**
- Hardcoded = simple, might not fit all styles
- Dynamic = more accurate, more complex
- User-provided = flexible, requires user input

**Recommendation needed.**

### 3. Confidence Threshold for Auto-Selection
**Question:** When should system auto-select vs ask user?

**Options:**
- Always auto-select highest confidence
- Auto-select only if confidence > 0.7
- Auto-select only if gap between #1 and #2 > 0.2
- Always ask user

**Tradeoffs:**
- Auto-select = faster, less user friction
- User choice = more control, better validation

**Recommendation needed.**

### 4. Test Image Count per Hypothesis
**Question:** How many test images to generate per hypothesis?

**Options:**
- 2 images (minimal)
- 3 images (balanced)
- 5 images (thorough)
- User configurable

**Tradeoffs:**
- Fewer = faster, less cost, less evidence
- More = better validation, higher cost

**Cost calculation:**
```
3 hypotheses × 3 test images = 9 generations total
3 hypotheses × 5 test images = 15 generations total
```

**Recommendation needed.**

### 5. Metrics for Hypothesis Scoring
**Question:** How do we measure which hypothesis is best?

**Options for MVP:**
- VLM visual consistency: "Does test image match reference style?" (0-100)
- VLM subject independence: "Is subject different but style same?" (0-100)
- Aggregate: Average of both scores

**Future additions:**
- CLIP embedding similarity
- Color histogram distance
- Texture statistics (Gram matrices)
- Perceptual loss (LPIPS)

**For MVP, keep simple?**

### 6. Integration with Training Mode
**Question:** What happens after hypothesis selection?

**Options:**
- Hypothesis mode ends, user starts new training session manually
- Auto-convert: "Continue to Training" button creates training session
- Hybrid: Training mode can optionally run hypothesis extraction first

**Tradeoffs:**
- Separate = cleaner separation, more steps
- Integrated = smoother flow, more coupling

**Recommendation needed.**

### 7. Storage of Test Images
**Question:** Where do test images go?

**Options:**
- Store in outputs/{session_id}/hypothesis_tests/
- Don't save, only show in UI temporarily
- Save only for selected hypothesis
- Save all with cleanup after selection

**Tradeoffs:**
- Store all = full audit trail, uses disk space
- Store minimal = saves space, loses evidence

**Recommendation needed.**

### 8. Hypothesis Refinement
**Question:** If all hypotheses score poorly, then what?

**Options:**
- Show best of bad options, let user decide
- Auto-generate new batch with different focus
- Let user provide feedback: "None of these are right because..."
- Give up, return to training mode

**For MVP:**
- Keep simple: show best, let user reject or accept

**Recommendation needed.**

## Technical Architecture

### Data Models

```python
class StyleHypothesis(BaseModel):
    id: str
    interpretation: str  # "Grid-based geometric abstraction"
    profile: StyleProfile  # Complete style profile
    confidence: float  # 0.0-1.0
    supporting_evidence: list[str]
    uncertain_aspects: list[str]
    test_results: list[HypothesisTest]

class HypothesisTest(BaseModel):
    test_subject: str  # "abstract pattern"
    generated_image_path: str
    scores: dict[str, float]  # {"visual_consistency": 85, "subject_independence": 78}
    timestamp: datetime

class HypothesisSet(BaseModel):
    session_id: str
    hypotheses: list[StyleHypothesis]
    selected_hypothesis_id: str | None
    created_at: datetime
```

### File Structure (New Files)

```
backend/
  services/
    hypothesis_extractor.py    # Generate multiple interpretations
    hypothesis_tester.py        # Test hypotheses
    hypothesis_selector.py      # Rank and select

  routers/
    hypothesis.py               # API endpoints

  models/
    hypothesis_models.py        # Pydantic models

  prompts/
    hypothesis_extractor.md     # Multi-interpretation extraction prompt
    hypothesis_tester.md        # Visual consistency scoring prompt
```

### Prompt Design Considerations

**hypothesis_extractor.md:**
```
Key requirements:
- Generate N DISTINCT interpretations
- Each interpretation focuses on different aspect
- Include supporting evidence for each
- Flag uncertain aspects
- Output complete StyleProfile for each
- Ensure interpretations are actually different (not variations)
```

**hypothesis_tester.md:**
```
Key requirements:
- Compare test image to reference
- Evaluate style consistency (not subject matching)
- Score visual consistency 0-100
- Score subject independence 0-100
- Explain score reasoning
```

## Success Criteria

### MVP is successful if:
1. User can upload image and get 3+ different style interpretations
2. Each interpretation is meaningfully different (not just variations)
3. System can test each interpretation with generated samples
4. Testing produces confidence scores that make sense
5. User can select best interpretation or system auto-selects reasonably
6. Selected interpretation can be used for training (if desired)
7. Process takes < 5 minutes end-to-end

### MVP fails if:
- All interpretations are basically the same
- Testing doesn't differentiate between hypotheses (all score similarly)
- Computational cost is prohibitive (> 10 minutes)
- Selected hypothesis doesn't actually capture the style better than current extraction
- Integration with training mode doesn't work

## Implementation Phases

### Phase 1: Foundation (No UI)
**Goal:** Prove hypothesis extraction + testing works

**Tasks:**
1. Create data models (hypothesis_models.py)
2. Create hypothesis extractor (multi-interpretation extraction)
3. Test extractor with sample images
4. Validate that interpretations are actually different

**Deliverable:** Can extract 3 different interpretations from an image

### Phase 2: Testing Logic
**Goal:** Validate hypotheses work

**Tasks:**
1. Create hypothesis tester (generate + score test images)
2. Implement scoring metrics (VLM-based)
3. Implement confidence updating
4. Test with real hypotheses from Phase 1

**Deliverable:** Can test hypothesis and get meaningful confidence scores

### Phase 3: Selection Logic
**Goal:** Choose best hypothesis

**Tasks:**
1. Implement ranking algorithm
2. Implement selection logic (auto vs manual)
3. Test full flow: extract → test → select

**Deliverable:** Can run full hypothesis exploration and get selected profile

### Phase 4: Database + API
**Goal:** Persist and expose via API

**Tasks:**
1. Create database tables
2. Implement API endpoints
3. Wire up to existing session system
4. Test API flows

**Deliverable:** Working API for hypothesis mode

### Phase 5: Frontend (Minimal)
**Goal:** UI for hypothesis selection

**Tasks:**
1. Add mode selector to session creation
2. Create hypothesis exploration view
3. Show test results
4. Implement selection interface

**Deliverable:** User can use hypothesis mode via UI

### Phase 6: Integration + Polish
**Goal:** Connect to training mode

**Tasks:**
1. Implement "Continue to Training" flow
2. Add error handling
3. Add progress indicators
4. Documentation

**Deliverable:** Complete MVP ready for testing

## Risk Assessment

### Technical Risks
1. **VLM can't generate distinct interpretations** - All hypotheses look the same
   - Mitigation: Prompt engineering, explicit constraints, manual validation

2. **Testing doesn't differentiate** - All hypotheses score similarly
   - Mitigation: Better test subjects, more test images, different metrics

3. **Computational cost too high** - 9-15 generations per exploration
   - Mitigation: Reduce test count, make testing optional, cache results

4. **Integration breaks existing system** - Training mode stops working
   - Mitigation: Separate code paths, feature flags, thorough testing

### UX Risks
1. **User doesn't understand hypothesis mode** - Confused by multiple options
   - Mitigation: Clear explanations, good defaults, optional mode

2. **Process takes too long** - User abandons before completion
   - Mitigation: Progress indicators, allow early exit, save intermediate

3. **Selected hypothesis not actually better** - User prefers training mode
   - Mitigation: Make hypothesis mode optional, allow fallback

### Scope Risks
1. **Feature creep** - Try to solve all problems at once
   - Mitigation: Strict MVP scope, defer non-essential features

2. **Over-engineering** - Build too much complexity
   - Mitigation: Start simple, add complexity only if needed

## Open Discussion Points

1. **Is this the right approach?** - Does hypothesis mode solve the core problem?

2. **Is MVP scope realistic?** - Can we build this in reasonable time?

3. **What are priorities?** - If we have to cut features, what stays/goes?

4. **How do we validate success?** - What tests prove this works?

5. **When do we merge to main?** - What's the bar for production-ready?

6. **Should this replace training mode eventually?** - Or always be separate?

---

## Next Steps

**Before coding:**
1. Review this document
2. Answer open questions
3. Agree on MVP scope
4. Define acceptance criteria
5. Estimate effort

**After alignment:**
1. Start Phase 1: Foundation
2. Iterate based on learnings
3. Expand as needed

---

**Document Status:** Draft for Discussion
**Created:** 2025-12-07
**Branch:** hypothesis-based-extraction
