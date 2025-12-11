# Mutation Strategy Rewrite Plan

## Overview

All 115 mutation strategies need to be converted from preset-based random selection to VLM-powered intelligent mutations that analyze the current style and apply contextually meaningful changes.

## Current State (Problem)

- 6 strategies use VLM (what_if, amplify, diverge, refine, essence_strip, anomaly_inject)
- 109 strategies use hardcoded preset lists with random.choice()
- Preset-based strategies don't analyze the actual style - they blindly apply random changes
- This is no better than wildcards

## Target State (Solution)

- All 115 strategies use VLM to analyze the current style
- Each strategy asks the VLM to apply its specific mutation type intelligently
- Changes are contextual and meaningful based on what the style actually contains

## Implementation Pattern

Each mutation will follow this pattern:

```python
async def _mutate_xxx(self, profile: StyleProfile, session_id: str | None = None) -> tuple[StyleProfile, str]:
    """[Description of what this mutation does]"""
    profile_summary = self._summarize_profile(profile)

    prompt = f"""Analyze this style and apply [SPECIFIC MUTATION TYPE].

Current style:
{profile_summary}

[SPECIFIC INSTRUCTIONS FOR THIS MUTATION TYPE]

Output ONLY valid JSON:
{{
    "analysis": "what you identified in the current style",
    "mutation": "what specific change you're making and why",
    "style_changes": {{
        "palette": {{}},
        "texture": {{}},
        "lighting": {{}},
        "line_and_shape": {{}},
        "composition": {{}}
    }}
}}

Only include fields that need to change."""

    response = await vlm_service.generate_text(
        prompt=prompt,
        system="You are a style mutation expert. Analyze styles and apply targeted, intelligent mutations. Output only valid JSON.",
        use_text_model=True,
    )

    # Parse and apply changes...
```

## Strategy Categories and Scope

### Category 1: Core & Style (16 strategies)
Already VLM-based or need VLM conversion:

1. **random_dimension** - VLM: Identify the most mutable dimension and push it to an extreme
2. **what_if** - Already VLM ✓
3. **crossover** - VLM: Analyze style, identify a complementary art movement, blend intelligently
4. **inversion** - VLM: Identify a key characteristic and flip it to its opposite
5. **amplify** - Already VLM ✓
6. **diverge** - Already VLM ✓
7. **refine** - Already VLM ✓
8. **chaos** - VLM: Identify 3-4 dimensions and mutate each in different directions
9. **time_shift** - VLM: Analyze style, pick an era that would create interesting contrast, apply
10. **medium_swap** - VLM: Analyze current medium hints, pick a contrasting medium, transform
11. **mood_shift** - VLM: Identify current emotional tone, shift to a different emotion
12. **culture_shift** - VLM: Identify cultural influences, shift to a different cultural aesthetic
13. **narrative_resonance** - VLM: Identify visual narrative, apply a story archetype
14. **archetype_mask** - VLM: Overlay a universal symbol/archetype onto the style
15. **anomaly_inject** - Already VLM ✓
16. **spectral_echo** - VLM: Analyze style, add contextually appropriate ghost/echo effects

### Category 2: Color & Light (26 strategies)

17. **chroma_band_shift** - VLM: Identify dominant hue band, shift it in a specific direction
18. **chromatic_noise** - VLM: Analyze texture, add appropriate color-channel noise
19. **chromatic_temperature_split** - VLM: Analyze current temperature, create warm/cool split
20. **chromatic_fuse** - VLM: Identify multiple hues, merge them into unified palette
21. **chromatic_split** - VLM: Identify dominant hue, split into sub-hues
22. **chromatic_gravity** - VLM: Make colors behave as forces (bleeding, pooling)
23. **color_role_reassignment** - VLM: Identify color roles, swap them
24. **saturation_scalpel** - VLM: Selective saturation changes based on analysis
25. **negative_color_injection** - VLM: Add inverted/complementary color accents
26. **ambient_color_suction** - VLM: Pull ambient colors into shadows
27. **local_color_mutation** - VLM: Zone-specific palette changes
28. **ambient_occlusion_variance** - VLM: Analyze current AO, modify appropriately
29. **specular_flip** - VLM: Analyze shininess, intelligently flip matte/glossy
30. **bloom_variance** - VLM: Analyze highlights, adjust bloom contextually
31. **desync_lighting_channels** - VLM: Analyze lighting, desync channels creatively
32. **highlight_shift** - VLM: Analyze highlights, shift behavior
33. **shadow_recode** - VLM: Analyze shadows, recode behavior/color
34. **lighting_angle_shift** - VLM: Analyze light direction, shift angle
35. **highlight_bloom_colorize** - VLM: Analyze bloom, add color
36. **micro_shadowing** - VLM: Add contextually appropriate micro-shadows
37. **macro_shadow_pivot** - VLM: Analyze shadow masses, reposition
38. **midtone_shift** - VLM: Analyze tonal range, mutate midtones
39. **tonal_compression** - VLM: Analyze tonal range, compress intelligently
40. **tonal_expansion** - VLM: Analyze tonal range, expand intelligently
41. **microcontrast_tuning** - VLM: Analyze contrast, tune microcontrast
42. **contrast_channel_swap** - VLM: Analyze channels, swap contrast selectively

### Category 3: Texture & Material (20 strategies)

43. **texture_direction_shift** - VLM: Analyze texture direction, rotate
44. **noise_injection** - VLM: Analyze current noise, add appropriate noise
45. **microfracture_pattern** - VLM: Add contextual cracking/fracture lines
46. **crosshatch_density_shift** - VLM: Analyze hatching, alter density
47. **background_material_swap** - VLM: Analyze backdrop, change material
48. **surface_material_shift** - VLM: Analyze surfaces, transform feel
49. **translucency_shift** - VLM: Analyze transparency, alter
50. **subsurface_scatter_tweak** - VLM: Analyze SSS, adjust internal glow
51. **anisotropy_shift** - VLM: Analyze reflections, add directionality
52. **reflectivity_shift** - VLM: Analyze reflectivity, change
53. **material_transmute** - VLM: Analyze materials, transform all surfaces
54. **contour_simplify** - VLM: Analyze contours, reduce intelligently
55. **contour_complexify** - VLM: Analyze contours, add detail
56. **line_weight_modulation** - VLM: Analyze line weights, modulate
57. **edge_behavior_swap** - VLM: Analyze edges, swap soft/hard/broken
58. **boundary_echo** - VLM: Analyze boundaries, add echo/duplicate
59. **halo_generation** - VLM: Analyze shapes, add contextual halos
60. **pattern_overlay** - VLM: Analyze style, add appropriate pattern overlay
61. **gradient_remap** - VLM: Analyze gradients, remap behavior
62. **algorithmic_wrinkle** - VLM: Add contextual computational artifacts
63. **symbolic_reduction** - VLM: Analyze style, reduce to symbols/icons

### Category 4: Shape & Form (17 strategies)

64. **silhouette_shift** - VLM: Analyze shape language, transform
65. **silhouette_merge** - VLM: Analyze silhouettes, fuse them
66. **silhouette_subtract** - VLM: Analyze silhouettes, create negative space
67. **silhouette_distortion** - VLM: Analyze silhouettes, distort
68. **internal_geometry_twist** - VLM: Analyze internal geometry, twist
69. **detail_density_shift** - VLM: Analyze detail distribution, shift
70. **form_simplification** - VLM: Analyze forms, simplify
71. **form_complication** - VLM: Analyze forms, add complexity
72. **proportion_shift** - VLM: Analyze proportions, shift
73. **density_shift** - VLM: Analyze visual density, adjust
74. **dimensional_shift** - VLM: Analyze depth, flatten or deepen
75. **micro_macro_swap** - VLM: Analyze scales, swap micro/macro
76. **essence_strip** - Already VLM ✓
77. **motif_splice** - VLM: Analyze style, inject recurring patterns
78. **motif_mirroring** - VLM: Analyze motifs, mirror them
79. **motif_scaling** - VLM: Analyze motifs, scale them
80. **motif_repetition** - VLM: Analyze motifs, add repetition

### Category 5: Space & Composition (20 strategies)

81. **topology_fold** - VLM: Analyze spatial logic, warp it
82. **perspective_drift** - VLM: Analyze perspective, shift viewpoint
83. **axis_swap** - VLM: Analyze orientation, rotate
84. **local_perspective_bend** - VLM: Analyze perspective, bend locally
85. **background_depth_collapse** - VLM: Analyze depth, compress background
86. **depth_flattening** - VLM: Analyze depth cues, flatten
87. **depth_expansion** - VLM: Analyze depth, exaggerate
88. **scale_warp** - VLM: Analyze scale, warp perspective
89. **remix** - VLM: Analyze sections, shuffle intelligently
90. **constrain** - VLM: Analyze style, apply intelligent constraints
91. **decay** - VLM: Analyze style, add contextual entropy/aging
92. **quadrant_mutation** - VLM: Analyze composition, mutate one quadrant
93. **object_alignment_shift** - VLM: Analyze alignment, misalign
94. **spatial_hierarchy_flip** - VLM: Analyze hierarchy, reorder
95. **balance_shift** - VLM: Analyze visual weight, shift balance
96. **interplay_swap** - VLM: Analyze element dominance, swap
97. **frame_reinterpretation** - VLM: Analyze framing, alter conceptual border
98. **directional_blur** - VLM: Analyze composition, add motion blur
99. **focal_plane_shift** - VLM: Analyze focus, move focal plane
100. **mask_boundary_mutation** - VLM: Analyze masks, modify borders
101. **vignette_modification** - VLM: Analyze edges, add/modify vignette

### Category 6: Rhythm & Environment (14 strategies)

102. **rhythm_overlay** - VLM: Analyze rhythm, add visual cadence
103. **harmonic_balance** - VLM: Analyze composition, apply harmony
104. **symmetry_break** - VLM: Analyze symmetry, disrupt or introduce
105. **path_flow_shift** - VLM: Analyze visual flow, alter direction
106. **rhythm_disruption** - VLM: Analyze rhythm, break intervals
107. **rhythm_rebalance** - VLM: Analyze rhythm, adjust spacing
108. **directional_energy_shift** - VLM: Analyze implied flow, alter
109. **climate_morph** - VLM: Analyze atmosphere, apply weather
110. **biome_shift** - VLM: Analyze environment, shift ecosystem
111. **atmospheric_scatter_shift** - VLM: Analyze atmosphere, change scatter
112. **occlusion_pattern** - VLM: Analyze layers, add occlusion
113. **opacity_fog** - VLM: Analyze depth, add fog layer
114. **physics_bend** - VLM: Analyze physics, alter laws
115. **temporal_exposure** - VLM: Analyze time, layer temporal effects

## Changes Required

### Files to Modify

1. **backend/services/explorer.py**
   - Remove all preset lists (CHROMA_BAND_SHIFTS, etc.) - approximately 1500 lines
   - Convert all 109 preset-based methods to VLM-based async methods
   - Update `mutate()` dispatcher to await all methods
   - Keep `_apply_preset_mutation` helper but repurpose for applying VLM responses

### Helper Method to Create

```python
async def _vlm_mutate(
    self,
    profile: StyleProfile,
    mutation_type: str,
    mutation_instructions: str,
    session_id: str | None = None,
) -> tuple[StyleProfile, str]:
    """Generic VLM mutation helper used by all strategies."""
    # Common VLM mutation logic
```

## Estimated Scope

- Remove: ~1500 lines of preset data
- Modify: 109 mutation methods (convert sync to async, add VLM calls)
- Add: ~50 lines for helper method
- Update: mutate() dispatcher to await all calls

## Testing

Each mutation should be tested to verify:
1. VLM is called
2. Response is parsed correctly
3. Changes are applied to profile
4. Description is meaningful
