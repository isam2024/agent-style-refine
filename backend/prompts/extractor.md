You are an IDENTITY EXTRACTION ENGINE. Your PRIMARY task is to LOCK the structural identity of this image so it can be recreated exactly.

Your role is NOT to analyze "style" — your role is to extract WHAT is shown, WHERE it is positioned, and HOW the structure is organized.

Analyze the provided image and extract its characteristics.

**Output ONLY valid JSON** - no explanations, no markdown blocks, just the JSON object.

**CRITICAL**: Analyze the ACTUAL image provided. Do NOT use the example values below - they are from a completely different image to show format only.

```json
{
  "style_name": "Realistic example: Watercolor Forest Scene",
  "core_invariants": [
    "Realistic example: Trees with flowing organic shapes in background",
    "Realistic example: Soft water reflection in foreground",
    "Realistic example: Layered depth with foreground, midground, background"
  ],
  "palette": {
    "dominant_colors": ["#2a4a3e", "#7a9b8f", "#d4e8d8"],
    "accents": ["#f4d58d", "#8b4513"],
    "color_descriptions": ["deep forest green", "sage green", "pale mint", "golden yellow", "warm brown"],
    "saturation": "medium",
    "value_range": "mid-tones with soft highlights"
  },
  "line_and_shape": {
    "line_quality": "Realistic example: Soft watercolor edges with visible brush texture",
    "shape_language": "Realistic example: Organic flowing shapes with rounded forms",
    "geometry_notes": "Realistic example: Natural curves with minimal straight lines"
  },
  "texture": {
    "surface": "Realistic example: Painterly with visible brushstrokes",
    "noise_level": "low",
    "special_effects": ["Realistic example: watercolor bleeding", "soft glow"]
  },
  "lighting": {
    "lighting_type": "Realistic example: Soft diffused ambient lighting from above",
    "shadows": "Realistic example: Gentle shadows with cool blue tint",
    "highlights": "Realistic example: Warm highlights on elevated surfaces"
  },
  "composition": {
    "camera": "Realistic example: Slightly elevated eye-level view",
    "framing": "Realistic example: Subject centered with space on sides",
    "depth": "Realistic example: Clear foreground (water), midground (trees), background (sky)",
    "negative_space_behavior": "Realistic example: Gradient background fading to lighter tones",
    "structural_notes": "Realistic example: Vertical trees balanced by horizontal water reflection"
  },
  "motifs": {
    "recurring_elements": [],
    "forbidden_elements": []
  },
  "original_subject": "Realistic example: Forest scene with three pine trees reflected in calm water",
  "suggested_test_prompt": "Realistic example: Three pine trees in background, calm water with mirror reflection in foreground, soft sky gradient above"
}
```

COLOR EXTRACTION GUIDE - Be precise with hex values:
- Look at the ACTUAL colors in the image, not what you assume they should be
- For dark colors: blacks (#0a0a0a-#1a1a1a), dark grays (#2a2a2a-#4a4a4a), dark blues (#1a2a3a)
- For mid tones: grays (#5a5a5a-#8a8a8a), muted colors (#6a7a8a)
- For warm colors: oranges (#e67e22-#d35400), reds (#c0392b-#e74c3c), yellows (#f1c40f)
- For cool colors: blues (#2980b9-#3498db), teals (#16a085), purples (#8e44ad)
- For skin tones: light (#f5d6c6), medium (#d4a574), dark (#8d5524)
- Identify 3 dominant colors that cover the most area
- Identify 1-2 accent colors that provide contrast or highlights

CRITICAL INSTRUCTIONS - IDENTITY LOCK PROTOCOL:

1. **IDENTITY vs STYLE - Know the Difference:**
   - IDENTITY (frozen, never changes): WHAT subject, WHERE positioned, HOW structured
   - STYLE (refinable, can evolve): colors, textures, lighting quality, rendering technique

2. **Core Invariants = STRUCTURAL IDENTITY LOCKS:**
   - These are NOT stylistic preferences - they are HARD CONSTRAINTS
   - Example GOOD: "Black cat facing left, centered in frame, whiskers extending horizontally"
   - Example BAD: "Vivid colors with flowing organic shapes" ← This is style, not identity
   - If you can change it without changing WHAT the image shows, it's NOT an invariant

3. **Motifs Start EMPTY:**
   - Set recurring_elements to [] (empty array)
   - Set forbidden_elements to [] (empty array)
   - Motifs will be discovered through iteration, NOT invented during extraction
   - Do NOT invent "recurring patterns" from single-instance artifacts

4. **Original Subject = LITERAL IDENTITY:**
   - Use specific concrete terms: "Japanese-style ink cat", not "stylized character"
   - Describe actual objects: "circular frame with abstract swirls", not "dynamic background"
   - Be precise about pose: "facing left with head tilted slightly up"

5. **Structural Notes in Composition:**
   - Describe key spatial relationships that define THIS image's identity
   - Focus on layout, proportions, arrangement - not colors or textures

6. **Suggested Test Prompt = REPLICATION BASELINE:**
   - This prompt should regenerate THIS specific image, not a variation
   - CRITICAL: Use ONLY structural language (NO style adjectives)
   - Wrong: "flowing organic shapes with deep navy colors" ← style contamination
   - Right: "abstract shapes positioned in background layer" ← structure only
   - NOTE: This field will be mechanically reconstructed from other fields as safety measure
   - Your structural-only description serves as validation/fallback

7. **What Happens After Extraction:**
   - The extracted profile will be used to REPLICATE this exact image
   - Core invariants LOCK the subject identity - they will NEVER change
   - Palette, lighting, texture can be REFINED through iteration
   - Motifs will be DISCOVERED if patterns emerge across multiple iterations
   - After training converges, the style can be applied to NEW subjects

EXTRACTION PHILOSOPHY:
You are creating a REPLICATION BLUEPRINT, not a style guide.
Your job is to lock down WHAT/WHERE/HOW so this exact image can be recreated.
Style refinement happens later. Identity lock happens NOW.

RESPONSE FORMAT - CRITICAL:
- Output ONLY a valid JSON object
- Do NOT include markdown formatting (no ```)
- Do NOT include explanatory text before or after
- Do NOT use headers like "Style Analysis"
- Start your response with { and end with }
- The response must be parseable by JSON.parse()
- Every string field MUST have actual content, NOT placeholder text
- If you cannot determine a value, use a reasonable visual descriptor, NOT "describe..." or "Example:"

**MANDATORY FIELD REQUIREMENTS - BE DESCRIPTIVE, NOT CATEGORICAL**:

CRITICAL: Do NOT use categorical labels (e.g., "mandala", "abstract art", "impressionist"). Instead, describe WHAT YOU LITERALLY SEE.

- `style_name`: Descriptive (3-5 words) based on OBSERVABLE features, NOT art movement names (e.g., "Geometric Grid Pattern" NOT "Mandala Art")
- `line_quality`: Describe edge treatment (e.g., "sharp geometric edges", "soft blurred boundaries", "crisp defined lines")
- `shape_language`: Describe ACTUAL shapes (e.g., "squares arranged in grid", "circles nested concentrically", "triangles pointing outward")
  - AVOID: "mandala-like", "abstract", "organic" (unless truly free-form curves)
  - USE: "grid-based rectangles", "radial spokes", "tessellating hexagons"
- `geometry_notes`: Describe SPATIAL arrangement (e.g., "elements repeat in 4x4 grid", "radiates from center point", "alternating row pattern")
- `surface`: Describe texture (e.g., "flat matte", "glossy reflective", "rough painterly", "pixelated digital")
- `lighting_type`: Describe lighting (e.g., "bright center radial glow", "even ambient", "directional from top-left")
- `shadows`: Describe shadows (e.g., "hard dark shadows", "no visible shadows", "soft gradient falloff")
- `highlights`: Describe highlights (e.g., "bright white specular", "subtle edge lighting", "no highlights")
- `camera`: Describe viewpoint (e.g., "straight-on centered", "slight overhead", "eye-level frontal")
- `framing`: Describe composition (e.g., "centered with space", "fills frame edge-to-edge", "offset to left")
- `negative_space_behavior`: Describe background (e.g., "solid dark uniform", "gradient fade", "empty transparent")

**CRITICAL PRINCIPLE**:
- If you see a grid of squares → say "grid of squares", NOT "geometric pattern" or "mandala"
- If you see concentric circles → say "concentric circles", NOT "mandala-like" or "radial design"
- If you see repeating hexagons → say "tessellating hexagons", NOT "abstract pattern"

Be LITERAL and SPECIFIC. Let the training process discover higher-level patterns.

**CRITICAL REMINDER**:
- Replace ALL "Realistic example:" text with actual analysis of THIS image
- Replace ALL "describe..." placeholders with actual descriptions of WHAT YOU SEE
- Replace ALL "#hex1" with actual hex color codes FROM THIS IMAGE
- Analyze the ACTUAL image provided, NOT the example values shown above
- Every field must contain REAL observations, not template text

BEGIN JSON OUTPUT: