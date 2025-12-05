import json
import logging
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.services.color_extractor import extract_colors_from_b64
from backend.models.schemas import StyleProfile

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
        return """You are a STYLE EXTRACTION ENGINE. Your task is to analyze visual style, NOT content or narrative.

Analyze the provided image and extract its visual style characteristics. Output ONLY valid JSON that matches this exact schema:

```json
{
  "style_name": "A descriptive, evocative name for this style (3-5 words)",
  "core_invariants": [
    "List 3-5 fundamental style traits that define this image",
    "These should be visual qualities, not subject matter"
  ],
  "palette": {
    "dominant_colors": ["#hex1", "#hex2", "#hex3"],
    "accents": ["#hex1", "#hex2"],
    "color_descriptions": ["name each color, e.g., 'deep navy', 'warm orange'"],
    "saturation": "low/medium/high/medium-high/medium-low",
    "value_range": "describe the light/dark distribution"
  },
  "line_and_shape": {
    "line_quality": "describe edge treatment and line character",
    "shape_language": "describe predominant shapes (organic/geometric/mixed)",
    "geometry_notes": "additional observations about form"
  },
  "texture": {
    "surface": "describe surface quality (smooth/rough/painterly/etc)",
    "noise_level": "low/medium/high",
    "special_effects": ["list any special visual effects like bloom, grain, etc"]
  },
  "lighting": {
    "lighting_type": "describe primary lighting setup",
    "shadows": "describe shadow quality and color",
    "highlights": "describe highlight treatment"
  },
  "composition": {
    "camera": "describe implied camera position/angle",
    "framing": "describe subject placement",
    "negative_space_behavior": "how empty space is treated"
  },
  "motifs": {
    "recurring_elements": ["visual elements that characterize this style"],
    "forbidden_elements": ["elements that would break this style"]
  }
}
```

IMPORTANT:
- Extract STYLE, not content. Do not describe what is depicted, describe HOW it is depicted.
- Focus on reproducible visual characteristics.
- Output ONLY the JSON, no explanation or markdown code blocks."""

    async def extract(self, image_b64: str) -> StyleProfile:
        """
        Extract style profile from an image.
        Uses PIL for accurate color extraction and VLM for style analysis.

        Args:
            image_b64: Base64 encoded image

        Returns:
            StyleProfile object
        """
        # Extract colors using PIL (accurate)
        logger.info("Extracting colors using PIL...")
        try:
            pil_colors = extract_colors_from_b64(image_b64)
            logger.info(f"PIL extracted colors: {pil_colors['dominant_colors']}")
        except Exception as e:
            logger.warning(f"PIL color extraction failed: {e}")
            pil_colors = None

        # Get style analysis from VLM
        logger.info("Analyzing style with VLM...")
        prompt = self._load_prompt()

        response = await vlm_service.analyze(
            prompt=prompt,
            images=[image_b64],
        )

        # Parse JSON from response
        profile_dict = self._parse_json_response(response)

        # Override palette with PIL-extracted colors (more accurate)
        if pil_colors:
            logger.info("Overriding VLM colors with PIL-extracted colors")
            profile_dict["palette"]["dominant_colors"] = pil_colors["dominant_colors"]
            profile_dict["palette"]["accents"] = pil_colors["accents"]
            profile_dict["palette"]["color_descriptions"] = pil_colors["color_descriptions"]
            profile_dict["palette"]["saturation"] = pil_colors["saturation"]
            profile_dict["palette"]["value_range"] = pil_colors["value_range"]

        return StyleProfile(**profile_dict)

    def _parse_json_response(self, response: str) -> dict:
        """Extract JSON from VLM response."""
        # Try direct parsing first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code block
        import re
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # Try to find raw JSON object
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))

        raise ValueError(f"Could not parse JSON from response: {response[:500]}")


style_extractor = StyleExtractor()
