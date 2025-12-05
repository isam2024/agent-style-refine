import json
import logging
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.services.color_extractor import extract_colors_from_b64, color_distance, hex_to_rgb
from backend.models.schemas import StyleProfile, CritiqueResult

logger = logging.getLogger(__name__)


class StyleCritic:
    def __init__(self):
        self.prompt_path = Path(__file__).parent.parent / "prompts" / "critic.md"

    def _load_prompt(self) -> str:
        """Load the critic prompt template."""
        if self.prompt_path.exists():
            return self.prompt_path.read_text()
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        return """You are a STYLE CRITIC analyzing a GENERATED IMAGE against a target style profile.

You are given:
1. The GENERATED IMAGE to analyze
2. The TARGET STYLE PROFILE (JSON) that describes the desired style
3. COLOR ANALYSIS comparing the generated image colors to the target palette

Your tasks:
1. Score how well the generated image matches the target style on each dimension (0-100)
2. Identify preserved traits (what was captured well)
3. Identify lost traits (what drifted or is missing from the target style)
4. Note interesting mutations (new characteristics that fit and could enhance the style)
5. Produce an UPDATED style profile with minimal, precise edits

CREATIVITY LEVEL: {{CREATIVITY_LEVEL}}/100
- 0-30: Make only tiny adjustments. Do not add new elements.
- 31-70: Allow moderate changes. May add 1-2 new motifs if they fit.
- 71-100: Encourage evolution. May de-emphasize one invariant, add multiple mutations.

TARGET STYLE PROFILE:
```json
{{STYLE_PROFILE}}
```

COLOR ANALYSIS (from pixel sampling):
{{COLOR_ANALYSIS}}

Output ONLY valid JSON in this exact format:
```json
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
  "preserved_traits": ["list of traits that were captured well"],
  "lost_traits": ["list of traits that drifted or are missing"],
  "interesting_mutations": ["list of new characteristics worth incorporating"],
  "updated_style_profile": {
    // Full StyleProfile JSON with your edits
    // Keep structure identical, only modify values where needed
  }
}
```

IMPORTANT:
- Analyze the GENERATED IMAGE against the TARGET STYLE PROFILE
- Compare STYLE, not content. The subject doesn't need to match.
- Use the COLOR ANALYSIS to inform your palette score
- Be specific about what aspects matched or drifted
- Make minimal edits to the style profile - preserve what works
- Output ONLY the JSON, no explanation."""

    async def critique(
        self,
        original_image_b64: str,
        generated_image_b64: str,
        style_profile: StyleProfile,
        creativity_level: int = 50,
    ) -> CritiqueResult:
        """
        Critique a generated image against the original style.
        Works with single-image VLMs by analyzing generated image + style profile.

        Args:
            original_image_b64: Base64 encoded reference image (used for color comparison)
            generated_image_b64: Base64 encoded generated image
            style_profile: Current style profile
            creativity_level: 0-100, controls how much mutation is allowed

        Returns:
            CritiqueResult with scores, analysis, and updated profile
        """
        # Extract colors from both images using PIL for accurate comparison
        logger.info("Extracting colors for comparison...")
        try:
            original_colors = extract_colors_from_b64(original_image_b64)
            generated_colors = extract_colors_from_b64(generated_image_b64)
            color_analysis = self._compare_colors(
                style_profile.palette.dominant_colors,
                generated_colors["dominant_colors"],
                original_colors,
                generated_colors,
            )
        except Exception as e:
            logger.warning(f"Color extraction failed: {e}")
            color_analysis = "Color analysis unavailable."

        prompt_template = self._load_prompt()

        # Fill in template
        prompt = prompt_template.replace(
            "{{CREATIVITY_LEVEL}}", str(creativity_level)
        ).replace(
            "{{STYLE_PROFILE}}", json.dumps(style_profile.model_dump(), indent=2)
        ).replace(
            "{{COLOR_ANALYSIS}}", color_analysis
        )

        logger.info("Sending generated image to VLM for critique...")

        # Only send the generated image (single-image model compatible)
        response = await vlm_service.analyze(
            prompt=prompt,
            images=[generated_image_b64],
        )

        # Parse JSON from response
        result_dict = self._parse_json_response(response)

        # Update palette in the result with PIL-extracted colors if available
        if generated_colors:
            result_dict["updated_style_profile"]["palette"]["dominant_colors"] = generated_colors["dominant_colors"]
            result_dict["updated_style_profile"]["palette"]["accents"] = generated_colors["accents"]
            result_dict["updated_style_profile"]["palette"]["color_descriptions"] = generated_colors["color_descriptions"]

        return CritiqueResult(**result_dict)

    def _compare_colors(
        self,
        target_colors: list[str],
        generated_colors: list[str],
        original_extracted: dict,
        generated_extracted: dict,
    ) -> str:
        """Generate a text comparison of colors."""
        lines = []

        lines.append("Target palette from style profile:")
        for i, color in enumerate(target_colors[:3]):
            desc = original_extracted["color_descriptions"][i] if i < len(original_extracted["color_descriptions"]) else "unknown"
            lines.append(f"  - {color} ({desc})")

        lines.append("\nGenerated image palette (extracted via pixel sampling):")
        for i, color in enumerate(generated_colors[:3]):
            desc = generated_extracted["color_descriptions"][i] if i < len(generated_extracted["color_descriptions"]) else "unknown"
            lines.append(f"  - {color} ({desc})")

        # Calculate color similarity
        total_distance = 0
        comparisons = min(len(target_colors), len(generated_colors), 3)
        for i in range(comparisons):
            try:
                target_rgb = hex_to_rgb(target_colors[i])
                gen_rgb = hex_to_rgb(generated_colors[i])
                dist = color_distance(target_rgb, gen_rgb)
                total_distance += dist
            except:
                pass

        if comparisons > 0:
            avg_distance = total_distance / comparisons
            if avg_distance < 50:
                match_quality = "EXCELLENT - colors closely match target"
            elif avg_distance < 100:
                match_quality = "GOOD - colors reasonably similar"
            elif avg_distance < 150:
                match_quality = "MODERATE - some color drift detected"
            else:
                match_quality = "POOR - significant color mismatch"
            lines.append(f"\nColor match assessment: {match_quality}")

        lines.append(f"\nTarget saturation: {original_extracted['saturation']}")
        lines.append(f"Generated saturation: {generated_extracted['saturation']}")
        lines.append(f"Target value range: {original_extracted['value_range']}")
        lines.append(f"Generated value range: {generated_extracted['value_range']}")

        return "\n".join(lines)

    def _parse_json_response(self, response: str) -> dict:
        """Extract JSON from VLM response."""
        import re

        # Try direct parsing first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # Try to find raw JSON object (greedy match for nested objects)
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass

        raise ValueError(f"Could not parse JSON from response: {response[:500]}")


style_critic = StyleCritic()
