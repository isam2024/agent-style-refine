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

    async def extract(self, image_b64: str, session_id: str | None = None) -> StyleProfile:
        """
        Extract style profile from an image.
        Uses PIL for accurate color extraction and VLM for style analysis.

        Args:
            image_b64: Base64 encoded image
            session_id: Optional session ID for WebSocket logging

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

        response = await vlm_service.analyze(
            prompt=prompt,
            images=[image_b64],
        )

        await log(f"VLM response received ({len(response)} chars)")
        await log("Parsing style profile from VLM response...")

        # Parse JSON from response
        profile_dict = self._parse_json_response(response)

        await log(f"Style identified: {profile_dict.get('style_name', 'Unknown')}", "success")

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

        return StyleProfile(**profile_dict)

    def _parse_json_response(self, response: str) -> dict:
        """Extract JSON from VLM response, with fallback parsing."""
        import re

        # Clean up response
        response = response.strip()

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
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object (greedy)
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: Parse markdown-style response
        logger.warning("JSON parsing failed, attempting markdown fallback parse")
        return self._parse_markdown_fallback(response)

    def _parse_markdown_fallback(self, response: str) -> dict:
        """
        Parse a markdown-formatted response into our schema.
        This handles cases where the VLM outputs text instead of JSON.
        """
        import re

        # Default structure
        result = {
            "style_name": "Extracted Style",
            "core_invariants": [],
            "palette": {
                "dominant_colors": ["#3a3a3a", "#8e8e8e", "#c0c0c0"],
                "accents": ["#e0e0e0"],
                "color_descriptions": ["dark gray", "medium gray", "light gray"],
                "saturation": "low",
                "value_range": "mid-tones"
            },
            "line_and_shape": {
                "line_quality": "soft edges",
                "shape_language": "organic",
                "geometry_notes": "natural forms"
            },
            "texture": {
                "surface": "smooth",
                "noise_level": "low",
                "special_effects": []
            },
            "lighting": {
                "lighting_type": "ambient",
                "shadows": "soft",
                "highlights": "subtle"
            },
            "composition": {
                "camera": "eye level",
                "framing": "centered",
                "negative_space_behavior": "minimal"
            },
            "motifs": {
                "recurring_elements": [],
                "forbidden_elements": []
            },
            "suggested_test_prompt": "A weathered wooden boat resting on a pebble beach at golden hour, with gentle waves lapping at its hull, seabirds circling overhead, and a distant lighthouse silhouetted against the warm evening sky"
        }

        # Try to extract style name
        name_match = re.search(r"\*\*Style Name[:\*]*\s*(.+?)(?:\*\*|\n)", response, re.IGNORECASE)
        if name_match:
            result["style_name"] = name_match.group(1).strip().strip("*")

        # Try to extract core invariants (bullet points after "Core Invariants")
        invariants_section = re.search(
            r"Core Invariants[:\*]*\s*\n((?:\s*[\*\-]\s*.+\n?)+)",
            response,
            re.IGNORECASE
        )
        if invariants_section:
            bullets = re.findall(r"[\*\-]\s*\*\*([^*]+)\*\*", invariants_section.group(1))
            if bullets:
                result["core_invariants"] = [b.strip().rstrip(":") for b in bullets[:5]]

        # Extract color mentions (hex codes)
        hex_colors = re.findall(r"#[0-9a-fA-F]{6}", response)
        if hex_colors:
            result["palette"]["dominant_colors"] = hex_colors[:3]
            result["palette"]["accents"] = hex_colors[3:5] if len(hex_colors) > 3 else []

        # Extract lighting info
        if "high contrast" in response.lower():
            result["lighting"]["lighting_type"] = "high contrast dramatic"
        if "soft" in response.lower() and "light" in response.lower():
            result["lighting"]["lighting_type"] = "soft ambient"
        if "backlit" in response.lower() or "backlighting" in response.lower():
            result["lighting"]["lighting_type"] = "backlit"

        # Extract texture info
        if "urban" in response.lower():
            result["texture"]["surface"] = "urban textured"
            result["motifs"]["recurring_elements"].append("urban textures")
        if "painterly" in response.lower():
            result["texture"]["surface"] = "painterly brushstrokes"
        if "rough" in response.lower():
            result["texture"]["surface"] = "rough textured"

        # Extract saturation
        if "muted" in response.lower():
            result["palette"]["saturation"] = "low"
        if "vibrant" in response.lower() or "saturated" in response.lower():
            result["palette"]["saturation"] = "high"

        logger.info(f"Fallback parsed style: {result['style_name']}")
        return result


style_extractor = StyleExtractor()
