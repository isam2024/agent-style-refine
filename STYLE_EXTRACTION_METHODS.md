# Style Extraction Methods

This document explores alternative approaches for extracting and understanding visual style from reference images. The goal is to produce a style representation that can be applied to novel subjects while preserving the essential aesthetic qualities.

## Current Methods

### 1. Single-Pass Extraction
**Status:** Implemented (`backend/services/extractor.py`)

The VLM analyzes the reference image once and produces a complete StyleProfile JSON covering palette, line/shape, texture, lighting, composition, and motifs.

**Strengths:**
- Fast (single VLM call)
- Deterministic output
- Simple to implement

**Weaknesses:**
- Locks into first interpretation (no uncertainty expression)
- May conflate subject with style
- No validation before training begins

---

### 2. Hypothesis-Based Extraction
**Status:** Implemented (`backend/services/hypothesis_extractor.py`)

Generates 3-5 competing style interpretations, tests each by generating sample images with different subjects, scores consistency, and selects the best hypothesis.

**Strengths:**
- Expresses uncertainty through multiple interpretations
- Tests subject-independence before committing
- User can override auto-selection

**Weaknesses:**
- Slow (multiple generation cycles per hypothesis)
- Resource intensive
- Hypotheses may still miss the "true" style

---

## Proposed Alternative Methods

### 3. Contrastive Style Extraction

**Concept:** Define style by what it *isn't* as much as what it *is*. Compare the reference against a diverse set of "negative" images to identify distinguishing characteristics.

**Process:**
1. Fetch or generate a diverse set of images (different styles, subjects, eras)
2. Ask VLM: "What makes Image A different from Images B, C, D?"
3. Cluster the distinguishing features into style dimensions
4. Weight features by how consistently they differentiate the reference

**Implementation Sketch:**
```python
async def contrastive_extraction(reference_b64: str, negative_set: list[str]) -> StyleProfile:
    differences = []
    for negative in negative_set:
        diff = await vlm.analyze(
            prompt="List 5 visual differences between these images. Focus on style, not content.",
            images=[reference_b64, negative]
        )
        differences.append(diff)

    # Cluster and weight the differences
    style_features = cluster_differences(differences)
    return build_profile_from_features(style_features)
```

**Strengths:**
- Identifies unique/distinctive style elements
- Less likely to include generic features
- Provides natural language "not like X" constraints

**Weaknesses:**
- Requires curated negative set
- May miss features common to reference and negatives
- More VLM calls

---

### 4. Multi-Scale Hierarchical Analysis

**Concept:** Style manifests differently at different scales. Analyze the image at multiple zoom levels and crop regions to capture both global composition and local texture details.

**Process:**
1. **Global pass:** Analyze full image for composition, overall palette, lighting direction
2. **Region passes:** Analyze 4-9 crops for local texture, edge treatment, detail patterns
3. **Micro pass:** Analyze highly zoomed sections for brush strokes, noise patterns, fine detail
4. Merge insights with scale-appropriate weighting

**Implementation Sketch:**
```python
async def multiscale_extraction(image_b64: str) -> StyleProfile:
    # Global analysis
    global_style = await analyze_at_scale(image_b64, scale="full", focus="composition, palette, lighting")

    # Regional analysis (3x3 grid)
    regions = extract_regions(image_b64, grid=(3, 3))
    regional_styles = [await analyze_at_scale(r, scale="region", focus="texture, edges, patterns") for r in regions]

    # Micro analysis (random detail crops)
    micro_crops = extract_random_crops(image_b64, count=5, size=256)
    micro_styles = [await analyze_at_scale(m, scale="micro", focus="noise, grain, stroke quality") for m in micro_crops]

    return merge_hierarchical(global_style, regional_styles, micro_styles)
```

**Strengths:**
- Captures style at all relevant scales
- Less likely to miss subtle texture details
- Better for complex, detailed artwork

**Weaknesses:**
- Many VLM calls (10-15 per image)
- Merging logic is complex
- May produce conflicting signals at different scales

---

### 5. Iterative Refinement Extraction

**Concept:** Start with a rough style profile and refine it through rapid generate-critique micro-cycles *before* committing to full training.

**Process:**
1. Generate initial coarse profile (5-second VLM analysis)
2. Generate 3 quick test images with simple subjects
3. Critique each: "What style elements are missing or wrong?"
4. Update profile based on critiques
5. Repeat 2-3 times until test images converge
6. Output refined profile for training

**Implementation Sketch:**
```python
async def iterative_extraction(reference_b64: str, max_rounds: int = 3) -> StyleProfile:
    profile = await quick_extraction(reference_b64)  # Coarse first pass

    for round in range(max_rounds):
        test_subjects = ["a simple circle", "a tree", "a chair"]
        critiques = []

        for subject in test_subjects:
            test_image = await generate(profile, subject)
            critique = await compare_style(reference_b64, test_image)
            critiques.append(critique)

        # Aggregate critiques and update profile
        updates = aggregate_critiques(critiques)
        if updates.confidence > 0.9:
            break  # Converged
        profile = apply_updates(profile, updates)

    return profile
```

**Strengths:**
- Self-correcting before training begins
- Tests actual generation capability
- Catches extraction errors early

**Weaknesses:**
- Slower than single-pass (but faster than full hypothesis testing)
- May over-fit to test subjects
- Requires good critique prompts

---

### 6. Style Decomposition with Independent Channels

**Concept:** Extract each style dimension completely independently using specialized prompts, then validate coherence between channels.

**Process:**
1. Run 6 parallel extractions, each focused on ONE dimension:
   - Palette-only extractor (color expert)
   - Shape-only extractor (geometry expert)
   - Texture-only extractor (surface expert)
   - Lighting-only extractor (illumination expert)
   - Composition-only extractor (layout expert)
   - Motif-only extractor (pattern expert)
2. Cross-validate: Check for contradictions between channels
3. Resolve conflicts through weighted voting or user input
4. Assemble final profile from validated components

**Implementation Sketch:**
```python
DIMENSION_PROMPTS = {
    "palette": "Analyze ONLY the colors. Ignore shapes, textures, content. List dominant colors, accents, saturation, contrast.",
    "texture": "Analyze ONLY surface textures. Ignore colors, shapes. Describe grain, smoothness, patterns, noise level.",
    # ... etc
}

async def decomposed_extraction(image_b64: str) -> StyleProfile:
    # Run all extractions in parallel
    extractions = await asyncio.gather(*[
        extract_dimension(image_b64, dim, prompt)
        for dim, prompt in DIMENSION_PROMPTS.items()
    ])

    # Cross-validate
    conflicts = find_conflicts(extractions)
    if conflicts:
        resolved = await resolve_conflicts(conflicts, image_b64)
        extractions = apply_resolutions(extractions, resolved)

    return assemble_profile(extractions)
```

**Strengths:**
- Each dimension gets full VLM attention
- Easier to debug which dimension is wrong
- Parallel execution (fast wall-clock time)

**Weaknesses:**
- May miss cross-dimensional relationships
- Conflict resolution is complex
- 6+ VLM calls per extraction

---

### 7. Exemplar Ensemble Extraction

**Concept:** When multiple reference images of the same style are available, extract style from the intersection of their features.

**Process:**
1. User provides 2-5 images in the same style (different subjects)
2. Extract preliminary profile from each image independently
3. Find intersection: Features present in ALL images
4. Find union: Features present in ANY image
5. Weight features by frequency across exemplars
6. Output profile with confidence scores per feature

**Implementation Sketch:**
```python
async def ensemble_extraction(images: list[str]) -> StyleProfile:
    profiles = [await single_pass_extraction(img) for img in images]

    # Find common features (high confidence)
    common = find_intersection(profiles)

    # Find variable features (lower confidence)
    variable = find_union(profiles) - common

    # Build weighted profile
    profile = build_weighted_profile(common, variable, len(images))
    profile.confidence_map = calculate_feature_confidence(profiles)

    return profile
```

**Strengths:**
- Multiple data points reduce noise
- Naturally filters out subject-specific features
- Provides confidence scores

**Weaknesses:**
- Requires multiple reference images (often unavailable)
- Images must genuinely share style
- Averaging may lose distinctive edge cases

---

### 8. Adversarial Boundary Probing

**Concept:** Discover style boundaries by deliberately generating edge cases and seeing what "breaks" the style.

**Process:**
1. Generate initial profile
2. Generate images that intentionally push boundaries:
   - Extreme color shifts
   - Inverted lighting
   - Different aspect ratios
   - Conflicting textures
3. Have VLM judge: "Is this still the same style?"
4. Binary search to find exact boundaries
5. Encode boundaries as hard constraints in profile

**Implementation Sketch:**
```python
async def boundary_probing(reference_b64: str, initial_profile: StyleProfile) -> StyleProfile:
    boundaries = {}

    for dimension in ["saturation", "contrast", "line_weight", "noise_level"]:
        # Binary search for boundary
        low, high = 0, 100
        while high - low > 5:
            mid = (low + high) // 2
            test_profile = modify_dimension(initial_profile, dimension, mid)
            test_image = await generate(test_profile, "abstract shape")

            is_same_style = await vlm.analyze(
                prompt="Is the second image the same visual style as the first? Yes/No only.",
                images=[reference_b64, test_image]
            )

            if is_same_style:
                low = mid
            else:
                high = mid

        boundaries[dimension] = {"min": low, "max": high}

    return add_boundaries_to_profile(initial_profile, boundaries)
```

**Strengths:**
- Discovers hard limits empirically
- Creates robust, well-defined style space
- Catches edge cases

**Weaknesses:**
- Very slow (many generations)
- Binary search assumes monotonic style distance
- May find false boundaries

---

### 9. Semantic-Aesthetic Disentanglement

**Concept:** Explicitly separate "what the image depicts" from "how it looks" using two-stage extraction.

**Process:**
1. **Semantic pass:** Ask VLM to describe only content/subject (ignore style)
2. **Aesthetic pass:** Ask VLM to describe only visual treatment (ignore content)
3. **Disentanglement check:** Generate the aesthetic description applied to a completely different subject
4. **Validation:** Verify the generated image shares style but not content
5. If validation fails, identify leaked semantic features and remove them

**Implementation Sketch:**
```python
async def disentangled_extraction(image_b64: str) -> StyleProfile:
    # Stage 1: Semantic extraction
    semantics = await vlm.analyze(
        prompt="Describe ONLY what this image depicts. The subject, objects, scene. Ignore colors, textures, artistic style.",
        images=[image_b64]
    )

    # Stage 2: Aesthetic extraction
    aesthetics = await vlm.analyze(
        prompt="Describe ONLY the visual style. Colors, textures, lighting, composition style. Pretend you can't see what the objects are.",
        images=[image_b64]
    )

    profile = build_profile_from_aesthetics(aesthetics)

    # Stage 3: Disentanglement validation
    opposite_subject = get_opposite_subject(semantics)  # e.g., if semantics mentions "cat", use "skyscraper"
    test_image = await generate(profile, opposite_subject)

    # Stage 4: Check for semantic leakage
    leakage = await detect_semantic_leakage(test_image, semantics)
    if leakage:
        profile = remove_leaked_features(profile, leakage)

    return profile
```

**Strengths:**
- Directly addresses subject-style entanglement
- Validation built into process
- Clear separation of concerns

**Weaknesses:**
- Two-stage process is slower
- "Opposite subject" selection is heuristic
- Some styles are inherently tied to subject matter

---

### 10. Perceptual Feature Clustering

**Concept:** Use computer vision (non-VLM) to extract low-level perceptual features, cluster them, and let VLM interpret the clusters.

**Process:**
1. Extract low-level features using traditional CV:
   - Color histograms (HSV space)
   - Edge orientation histograms (Gabor filters)
   - Texture descriptors (LBP, GLCM)
   - Spatial frequency analysis (FFT)
2. Cluster similar regions
3. Pass cluster statistics to VLM for interpretation
4. VLM translates numerical features to semantic style descriptions

**Implementation Sketch:**
```python
async def perceptual_extraction(image_b64: str) -> StyleProfile:
    image = decode_image(image_b64)

    # Extract CV features
    color_hist = extract_color_histogram(image, bins=32, space="hsv")
    edge_hist = extract_edge_orientations(image, gabor_filters=8)
    texture_desc = extract_lbp_features(image)
    freq_analysis = extract_fft_features(image)

    # Package features for VLM
    feature_summary = f"""
    Color distribution: {summarize_histogram(color_hist)}
    Dominant edge orientations: {summarize_edges(edge_hist)}
    Texture uniformity: {texture_desc['uniformity']:.2f}
    High-frequency content: {freq_analysis['hf_ratio']:.2f}
    """

    # VLM interprets features
    interpretation = await vlm.analyze(
        prompt=f"Given these visual measurements, describe the artistic style:\n{feature_summary}",
        images=[image_b64]
    )

    return build_profile_from_interpretation(interpretation, raw_features={
        "color_hist": color_hist,
        "edge_hist": edge_hist,
        "texture": texture_desc,
        "frequency": freq_analysis
    })
```

**Strengths:**
- Objective, reproducible measurements
- VLM can't hallucinate basic statistics
- Combines CV precision with VLM interpretation

**Weaknesses:**
- Low-level features may miss high-level style
- Requires CV dependencies (OpenCV, scikit-image)
- Feature selection is manual/heuristic

---

### 11. Progressive Disclosure Extraction

**Concept:** Start with the most obvious style elements and progressively extract subtler features.

**Process:**
1. **Pass 1 (Obvious):** "What is the most striking visual characteristic?"
2. **Pass 2 (Secondary):** "Besides [Pass 1], what else defines the style?"
3. **Pass 3 (Subtle):** "What subtle details contribute to the overall feel?"
4. **Pass 4 (Negative):** "What is notably absent or avoided in this style?"
5. Build hierarchical profile with prominence weights

**Implementation Sketch:**
```python
async def progressive_extraction(image_b64: str) -> StyleProfile:
    layers = []
    context = ""

    prompts = [
        ("obvious", "What is the single most striking visual characteristic of this image's style?"),
        ("secondary", "Besides {previous}, what other elements define this style?"),
        ("subtle", "What subtle details or nuances contribute to the overall aesthetic feel?"),
        ("negative", "What visual elements are notably ABSENT or avoided in this style?")
    ]

    for layer_name, prompt_template in prompts:
        prompt = prompt_template.format(previous=context)
        response = await vlm.analyze(prompt=prompt, images=[image_b64])
        layers.append({"layer": layer_name, "features": response})
        context = response[:100]  # Feed forward for context

    return build_hierarchical_profile(layers)
```

**Strengths:**
- Captures both obvious and subtle features
- Natural priority/weighting
- Negative space is explicitly modeled

**Weaknesses:**
- 4 VLM calls minimum
- Later passes may contradict earlier ones
- "Subtle" is subjective

---

### 12. Style Transfer Validation Loop

**Concept:** Validate extraction by attempting style transfer to maximally different subjects.

**Process:**
1. Extract initial profile
2. Define 3-5 "challenge subjects" that are maximally different from the original:
   - If original is organic → test with geometric
   - If original is indoor → test with landscape
   - If original has figure → test with abstract
3. Generate challenge images
4. Score style consistency for each
5. Identify which style elements transfer well vs. poorly
6. Output profile with "transferability scores" per element

**Strengths:**
- Directly tests the goal (style transfer)
- Identifies subject-bound features
- Provides practical quality metric

**Weaknesses:**
- Requires generation (slow)
- "Maximally different" is heuristic
- Some styles genuinely don't transfer

---

## Comparison Matrix

| Method | VLM Calls | Generation Needed | Subject Independence | Speed | Complexity |
|--------|-----------|-------------------|---------------------|-------|------------|
| Single-Pass | 1 | No | Low | Fast | Low |
| Hypothesis-Based | 3-5 + tests | Yes (9-15) | High | Slow | High |
| Contrastive | 5-10 | No | Medium | Medium | Medium |
| Multi-Scale | 10-15 | No | Low | Medium | Medium |
| Iterative Refinement | 6-9 | Yes (6-9) | High | Medium | Medium |
| Decomposed | 6-8 | No | Medium | Fast (parallel) | Medium |
| Exemplar Ensemble | N images | No | High | Medium | Low |
| Adversarial Probing | 20-50 | Yes (20-50) | Medium | Very Slow | High |
| Disentanglement | 3-4 | Yes (1-2) | Very High | Medium | High |
| Perceptual Clustering | 1 | No | Low | Fast | Medium |
| Progressive Disclosure | 4-5 | No | Medium | Medium | Low |
| Transfer Validation | 1 + tests | Yes (3-5) | Very High | Medium | Medium |

---

## Recommended Combinations

### For Speed-Critical Applications
1. Single-Pass + Transfer Validation (2 calls + 3 generations)
2. Decomposed Parallel (6 calls, parallel = fast wall time)

### For Maximum Accuracy
1. Hypothesis-Based + Adversarial Boundary Probing
2. Multi-Scale + Iterative Refinement

### For Limited Reference Images
1. Contrastive + Progressive Disclosure
2. Single-Pass + Iterative Refinement

### For Multiple Reference Images
1. Exemplar Ensemble + Transfer Validation
2. Exemplar Ensemble + Disentanglement

---

## Implementation Priority Recommendations

1. **High Value, Medium Effort:** Iterative Refinement Extraction
   - Catches errors before training
   - Self-correcting
   - Reasonable speed

2. **High Value, Low Effort:** Progressive Disclosure
   - Easy to implement (just prompt engineering)
   - Captures hierarchy naturally
   - No generation needed

3. **High Value, High Effort:** Semantic-Aesthetic Disentanglement
   - Directly solves subject-style entanglement
   - Built-in validation
   - Worth the complexity for difficult styles

4. **Quick Win:** Perceptual Feature Clustering
   - Add objective measurements
   - Grounds VLM interpretation in data
   - Can run alongside existing extraction
