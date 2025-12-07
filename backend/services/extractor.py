import json
import logging
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.services.color_extractor import extract_colors_from_b64
from backend.models.schemas import StyleProfile
from backend.websocket import manager

logger = logging.getLogger(__name__)


class StyleExtractor:
    def __init__(self):
        self.prompt_path = Path(__file__).parent.parent / "prompts" / "extractor.md"

    def _load_prompt(self) -> str:
        """Load the extraction prompt template."""
        if self.prompt_path.exists():
            return self.prompt_path.read_text()
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        return """You are a STYLE EXTRACTION ENGINE. Analyze the image and extract both its visual style AND describe what is depicted.

Output ONLY valid JSON matching this schema:

```json
{
  "style_name": "A descriptive name for this style (3-5 words)",
  "core_invariants": [
    "List 3-5 fundamental style traits that define this image",
    "These should be visual qualities, not subject matter"
  ],
  "palette": {
    "dominant_colors": ["#hex1", "#hex2", "#hex3"],
    "accents": ["#hex1", "#hex2"],
    "color_descriptions": ["name each color, e.g., 'deep navy', 'warm orange'"],
    "saturation": "low/medium/high",
    "value_range": "describe the light/dark distribution"
  },
  "line_and_shape": {
    "line_quality": "describe edge treatment and line character",
    "shape_language": "describe predominant shapes",
    "geometry_notes": "additional observations about form"
  },
  "texture": {
    "surface": "describe surface quality",
    "noise_level": "low/medium/high",
    "special_effects": ["list any special visual effects"]
  },
  "lighting": {
    "lighting_type": "describe primary lighting setup",
    "shadows": "describe shadow quality",
    "highlights": "describe highlight treatment"
  },
  "composition": {
    "camera": "describe camera position/angle",
    "framing": "describe subject placement",
    "negative_space_behavior": "how empty space is treated"
  },
  "motifs": {
    "recurring_elements": ["visual elements that characterize this style"],
    "forbidden_elements": ["elements that would break this style"]
  },
  "original_subject": "Describe exactly WHAT is shown in this image: main subject, setting, objects, scene details in 15-30 words",
  "suggested_test_prompt": "Write a CONCRETE 40-60 word prompt describing the SAME scene. Include: specific subject, setting, objects, lighting, mood, colors. Describe what you SEE, not abstract concepts."
}
```

IMPORTANT:
- For style fields: describe HOW it looks (visual qualities)
- For original_subject and suggested_test_prompt: describe WHAT you see (concrete content)
- Output ONLY valid JSON, no markdown or explanation."""

    async def extract(self, image_b64: str, session_id: str | None = None, style_hints: str | None = None) -> StyleProfile:
        """
        Extract style profile from an image.
        Uses PIL for accurate color extraction and VLM for style analysis.

        Args:
            image_b64: Base64 encoded image
            session_id: Optional session ID for WebSocket logging
            style_hints: Optional user guidance about what the style IS and ISN'T

        Returns:
            StyleProfile object
        """
        async def log(msg: str, level: str = "info"):
            logger.info(msg)
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "extract")

        # Extract colors using PIL (accurate)
        await log("Extracting colors using PIL/KMeans...")
        try:
            pil_colors = extract_colors_from_b64(image_b64)
            await log(f"Found {len(pil_colors['dominant_colors'])} dominant + {len(pil_colors['accents'])} accent colors", "success")
            await log(f"Dominant: {', '.join(pil_colors['color_descriptions'][:5])}")
            await log(f"Saturation: {pil_colors['saturation']}, Value: {pil_colors['value_range']}")
        except Exception as e:
            await log(f"PIL color extraction failed: {e}", "warning")
            pil_colors = None

        # Get style analysis from VLM
        await log("Sending image to VLM for full style analysis...")
        await log("Analyzing: style, lighting, texture, composition, motifs, subject...")
        prompt = self._load_prompt()

        # Add user style hints if provided
        if style_hints:
            await log(f"Using style hints: {style_hints}", "info")
            prompt = f"""{prompt}

**USER GUIDANCE** (CRITICAL - Follow these instructions precisely):
{style_hints}

The user has provided specific guidance about this style. You MUST incorporate their descriptions and corrections into your analysis. If they say it's NOT something (e.g., "NOT mandala"), do not use that term or similar concepts. Use their positive descriptions (e.g., "grid-like pattern") as the primary characterization."""

        # Retry loop for VLM + parsing (up to 3 attempts)
        max_retries = 3
        last_error = None
        profile_dict = None

        for attempt in range(max_retries):
            try:
                await log(f"Sending image to VLM for extraction (attempt {attempt + 1}/{max_retries})...")
                response = await vlm_service.analyze(
                    prompt=prompt,
                    images=[image_b64],
                    max_retries=1,  # VLM has its own retry
                )

                await log(f"VLM response received ({len(response)} chars)")

                # DEBUG: Log first part of VLM response
                response_preview = response[:500] if len(response) > 500 else response
                await log(f"VLM response preview: {response_preview}", "warning")

                await log("Parsing style profile from VLM response...")

                # Parse JSON from response - FAIL if invalid
                profile_dict = self._parse_json_response(response)

                # Success! Break out of retry loop
                await log(f"Style identified: {profile_dict.get('style_name', 'Unknown')}", "success")
                break

            except ValueError as e:
                # JSON parsing error - retry
                last_error = e
                if attempt < max_retries - 1:
                    await log(f"Parsing failed (attempt {attempt + 1}/{max_retries}): {e}", "warning")
                    await log(f"VLM response was: {response[:300]}", "warning")
                    await log("Retrying VLM request...", "info")
                    import asyncio
                    await asyncio.sleep(2)  # Brief pause before retry
                else:
                    await log(f"All {max_retries} parsing attempts failed", "error")
                    await log(f"Final response: {response[:500]}", "error")
                    raise RuntimeError(
                        f"Style extraction failed after {max_retries} attempts: VLM returned invalid JSON. "
                        f"Check that the model supports JSON output. Response preview: {response[:200]}"
                    )
            except Exception as e:
                # Other errors (connection, etc) - don't retry
                await log(f"VLM request failed: {e}", "error")
                raise

        # If we exited loop without breaking, raise the last error
        if profile_dict is None:
            if last_error:
                raise last_error
            raise RuntimeError("Style extraction failed: unknown error")

        # Log what was extracted
        if profile_dict.get("lighting"):
            await log(f"Lighting: {profile_dict['lighting'].get('lighting_type', 'N/A')}")
        if profile_dict.get("texture"):
            await log(f"Texture: {profile_dict['texture'].get('surface', 'N/A')}")
        if profile_dict.get("composition"):
            await log(f"Composition: {profile_dict['composition'].get('camera', 'N/A')}")
        if profile_dict.get("original_subject"):
            await log(f"Subject: {profile_dict['original_subject'][:80]}...")
        if profile_dict.get("suggested_test_prompt"):
            await log(f"Test prompt: {profile_dict['suggested_test_prompt'][:80]}...")

        # Override palette with PIL-extracted colors (more accurate)
        if pil_colors:
            await log("Applying accurate PIL color data to palette...")
            profile_dict["palette"]["dominant_colors"] = pil_colors["dominant_colors"]
            profile_dict["palette"]["accents"] = pil_colors["accents"]
            profile_dict["palette"]["color_descriptions"] = pil_colors["color_descriptions"]
            profile_dict["palette"]["saturation"] = pil_colors["saturation"]
            profile_dict["palette"]["value_range"] = pil_colors["value_range"]

        # Log core invariants
        await log("Core style invariants:")
        if profile_dict.get("core_invariants"):
            for inv in profile_dict["core_invariants"]:
                await log(f"  • {inv}")

        # BASELINE VALIDATION - Use VLM to check if baseline is structural-only
        # Let the VLM itself determine if there's style contamination (dynamic, not keyword-based)
        await log("Validating baseline with VLM...")

        vlm_baseline = profile_dict.get("suggested_test_prompt", "")

        if vlm_baseline:
            validation_prompt = f"""Analyze this description and determine if it contains ONLY structural/compositional information, or if it also includes style attributes.

Description to analyze: "{vlm_baseline}"

Structural elements (ALLOWED):
- What objects/subjects are present
- Where things are positioned (left, right, center, foreground, background)
- How things are arranged (grid, scattered, layered, symmetrical)
- Spatial relationships and composition
- Object count, size relationships

Style elements (NOT ALLOWED):
- Colors or color descriptions
- Lighting quality or shadows
- Textures or surface qualities
- Moods or atmospheres
- Rendering techniques or art styles
- Material properties

Output valid JSON:
{{
  "is_structural_only": true/false,
  "contamination_found": ["list any style elements detected"],
  "reason": "brief explanation"
}}"""

            try:
                await log("Asking VLM to validate baseline...")
                validation_response = await vlm_service.analyze(
                    prompt=validation_prompt,
                    images=None,  # Text-only validation
                    force_json=True,
                    max_retries=1,  # Quick validation, don't retry too much
                )

                validation_result = json.loads(validation_response)
                is_clean = validation_result.get("is_structural_only", False)
                contamination = validation_result.get("contamination_found", [])

                if is_clean:
                    await log(f"VLM validation: Baseline is structural-only ✓", "success")
                    await log(f"Using VLM baseline: {vlm_baseline[:100]}...", "success")
                else:
                    await log(f"VLM validation: Baseline has style contamination ✗", "warning")
                    await log(f"Contamination: {', '.join(contamination[:3])}", "warning")
                    await log(f"VLM baseline: {vlm_baseline[:100]}...", "warning")

                    # Build mechanical baseline from structural fields
                    original_subject = profile_dict.get("original_subject", "")
                    composition = profile_dict.get("composition", {})

                    baseline_parts = []
                    if original_subject:
                        baseline_parts.append(original_subject)
                    if composition.get("framing"):
                        baseline_parts.append(composition["framing"])
                    if composition.get("structural_notes"):
                        baseline_parts.append(composition["structural_notes"])

                    if baseline_parts:
                        mechanical_baseline = ", ".join(baseline_parts)
                        profile_dict["suggested_test_prompt"] = mechanical_baseline
                        await log(f"Using mechanical baseline: {mechanical_baseline[:100]}...", "success")
                    else:
                        await log("Cannot build mechanical baseline, keeping VLM baseline despite contamination", "warning")

            except Exception as e:
                # Validation failed - fall back to mechanical baseline to be safe
                await log(f"Baseline validation failed: {e}", "warning")
                await log("Falling back to mechanical baseline for safety", "info")

                original_subject = profile_dict.get("original_subject", "")
                composition = profile_dict.get("composition", {})

                baseline_parts = []
                if original_subject:
                    baseline_parts.append(original_subject)
                if composition.get("framing"):
                    baseline_parts.append(composition["framing"])
                if composition.get("structural_notes"):
                    baseline_parts.append(composition["structural_notes"])

                if baseline_parts:
                    mechanical_baseline = ", ".join(baseline_parts)
                    profile_dict["suggested_test_prompt"] = mechanical_baseline
                    await log(f"Using mechanical baseline: {mechanical_baseline[:100]}...", "success")
        else:
            await log("No VLM baseline provided, skipping validation", "warning")

        # Extract natural language image description (reverse prompt)
        await log("Extracting natural language image description...")
        try:
            image_description = await vlm_service.describe_image(image_b64)
            profile_dict["image_description"] = image_description.strip()
            await log(f"Image description: {image_description[:100]}...", "success")
        except Exception as e:
            await log(f"Image description extraction failed: {e}", "warning")
            profile_dict["image_description"] = None

        return StyleProfile(**profile_dict)

    def _parse_json_response(self, response: str) -> dict:
        """
        Extract JSON from VLM response. RAISES ValueError if JSON cannot be parsed.

        NO FALLBACK - fails explicitly to surface VLM output issues.
        """
        import re

        # Clean up response
        response = response.strip()

        # Try direct parsing first
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.debug(f"Direct JSON parse failed: {e}")

        # Try to find JSON in markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.debug(f"Markdown-wrapped JSON parse failed: {e}")

        # Try to find raw JSON object (greedy)
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError as e:
                logger.debug(f"Greedy JSON extraction parse failed: {e}")

        # NO FALLBACK - fail explicitly
        logger.error("CRITICAL: VLM did not return parseable JSON")
        logger.error(f"Response was: {response[:500]}")
        raise ValueError(
            f"VLM response is not valid JSON. "
            f"Enable JSON format in model or check prompt. "
            f"Response preview: {response[:300]}"
        )


style_extractor = StyleExtractor()
