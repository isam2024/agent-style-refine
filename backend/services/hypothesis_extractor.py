"""
Multi-hypothesis style extraction service.

Generates multiple competing interpretations of a style from a single image.
Each interpretation is a complete StyleProfile with different emphasis.
"""

import json
import logging
import uuid
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.services.color_extractor import extract_colors_from_b64
from backend.models.schemas import StyleProfile
from backend.models.hypothesis_models import (
    StyleHypothesis,
    HypothesisSet,
)
from backend.websocket import manager

logger = logging.getLogger(__name__)


class HypothesisExtractor:
    """Generates multiple competing style interpretations from an image."""

    def __init__(self):
        self.prompt_path = (
            Path(__file__).parent.parent / "prompts" / "hypothesis_extractor.md"
        )

    def _load_prompt(self) -> str:
        """Load the multi-hypothesis extraction prompt template."""
        if self.prompt_path.exists():
            return self.prompt_path.read_text()
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Fallback prompt if file doesn't exist."""
        return """Generate multiple distinct style interpretations from this image.

Output JSON with:
{
  "hypotheses": [
    {
      "interpretation": "Label for this interpretation",
      "supporting_evidence": ["observation 1", "observation 2"],
      "uncertain_aspects": ["uncertainty 1", "uncertainty 2"],
      "profile": { <complete StyleProfile> }
    }
  ]
}
"""

    async def extract_hypotheses(
        self,
        image_b64: str,
        session_id: str,
        num_hypotheses: int = 3,
        style_hints: str | None = None,
    ) -> HypothesisSet:
        """
        Extract multiple competing style interpretations from an image.

        Args:
            image_b64: Base64 encoded image
            session_id: Session ID for this extraction
            num_hypotheses: Number of distinct interpretations to generate (2-5)
            style_hints: Optional user guidance about the style

        Returns:
            HypothesisSet containing all interpretations
        """

        async def log(msg: str, level: str = "info"):
            logger.info(msg)
            await manager.broadcast_log(session_id, msg, level, "hypothesis_extract")

        await log(f"Starting multi-hypothesis extraction ({num_hypotheses} interpretations)...")

        # Extract colors once using PIL (shared across all hypotheses)
        await log("Extracting accurate colors using PIL/KMeans...")
        try:
            pil_colors = extract_colors_from_b64(image_b64)
            await log(
                f"Found {len(pil_colors['dominant_colors'])} dominant + "
                f"{len(pil_colors['accents'])} accent colors",
                "success",
            )
        except Exception as e:
            await log(f"PIL color extraction failed: {e}", "warning")
            pil_colors = None

        # Build prompt
        prompt = self._load_prompt()
        prompt = prompt.replace("{num_hypotheses}", str(num_hypotheses))

        # Add style hints if provided
        if style_hints:
            await log(f"Using style hints: {style_hints}", "info")
            style_hints_section = f"""
**USER GUIDANCE** (CRITICAL - Incorporate into ALL hypotheses):
{style_hints}

The user has provided specific guidance about this style. You MUST incorporate their descriptions into all hypotheses. If they say it's NOT something, ensure that constraint appears in all interpretations where relevant.
"""
        else:
            style_hints_section = "(No user hints provided)"

        prompt = prompt.replace("{style_hints_section}", style_hints_section)

        # Retry loop for VLM + parsing
        max_retries = 3
        hypotheses_data = None

        for attempt in range(max_retries):
            try:
                await log(
                    f"Sending to VLM for multi-hypothesis extraction "
                    f"(attempt {attempt + 1}/{max_retries})..."
                )

                response = await vlm_service.analyze(
                    prompt=prompt,
                    images=[image_b64],
                    max_retries=1,
                )

                await log(f"VLM response received ({len(response)} chars)")

                # Parse JSON response
                hypotheses_data = self._parse_json_response(response)

                # Validate structure
                if "hypotheses" not in hypotheses_data:
                    raise ValueError("Response missing 'hypotheses' field")

                if not isinstance(hypotheses_data["hypotheses"], list):
                    raise ValueError("'hypotheses' field is not a list")

                if len(hypotheses_data["hypotheses"]) < 2:
                    raise ValueError(
                        f"Need at least 2 hypotheses, got {len(hypotheses_data['hypotheses'])}"
                    )

                await log(
                    f"Successfully extracted {len(hypotheses_data['hypotheses'])} hypotheses",
                    "success",
                )
                break

            except ValueError as e:
                if attempt < max_retries - 1:
                    await log(
                        f"Parsing failed (attempt {attempt + 1}/{max_retries}): {e}",
                        "warning",
                    )
                    await log("Retrying VLM request...", "info")
                    import asyncio
                    await asyncio.sleep(2)
                else:
                    await log(f"All {max_retries} attempts failed", "error")
                    raise RuntimeError(
                        f"Hypothesis extraction failed after {max_retries} attempts: {e}"
                    )

            except Exception as e:
                await log(f"VLM request failed: {e}", "error")
                raise

        if hypotheses_data is None:
            raise RuntimeError("Hypothesis extraction failed: unknown error")

        # Build StyleHypothesis objects
        hypotheses = []
        for idx, hyp_data in enumerate(hypotheses_data["hypotheses"]):
            hypothesis_id = str(uuid.uuid4())

            # Extract profile data
            profile_data = hyp_data.get("profile", {})

            # Override palette with PIL colors if available
            if pil_colors and "palette" in profile_data:
                profile_data["palette"]["dominant_colors"] = pil_colors["dominant_colors"]
                profile_data["palette"]["accents"] = pil_colors["accents"]
                profile_data["palette"]["color_descriptions"] = pil_colors[
                    "color_descriptions"
                ]
                profile_data["palette"]["saturation"] = pil_colors["saturation"]
                profile_data["palette"]["value_range"] = pil_colors["value_range"]

            # Create StyleProfile
            try:
                profile = StyleProfile(**profile_data)
            except Exception as e:
                await log(
                    f"Failed to parse profile for hypothesis {idx + 1}: {e}", "error"
                )
                continue

            # Create StyleHypothesis
            hypothesis = StyleHypothesis(
                id=hypothesis_id,
                interpretation=hyp_data.get("interpretation", f"Interpretation {idx + 1}"),
                profile=profile,
                confidence=1.0 / len(hypotheses_data["hypotheses"]),  # Equal initial confidence
                supporting_evidence=hyp_data.get("supporting_evidence", []),
                uncertain_aspects=hyp_data.get("uncertain_aspects", []),
                test_results=[],  # No tests yet
            )

            hypotheses.append(hypothesis)

            # Log this hypothesis
            await log(f"Hypothesis {idx + 1}: {hypothesis.interpretation}")
            await log(f"  Confidence: {hypothesis.confidence:.2f}")
            await log(f"  Evidence: {len(hypothesis.supporting_evidence)} points")
            await log(f"  Uncertainties: {len(hypothesis.uncertain_aspects)} aspects")

        if not hypotheses:
            raise RuntimeError("No valid hypotheses generated")

        # Create HypothesisSet
        hypothesis_set = HypothesisSet(
            session_id=session_id,
            hypotheses=hypotheses,
            selected_hypothesis_id=None,  # No selection yet
        )

        await log(
            f"Multi-hypothesis extraction complete: {len(hypotheses)} interpretations",
            "success",
        )

        return hypothesis_set

    def _parse_json_response(self, response: str) -> dict:
        """
        Extract JSON from VLM response.

        Raises ValueError if JSON cannot be parsed.
        """
        import re

        response = response.strip()

        # Try direct parsing
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try greedy extraction
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Failed to parse
        logger.error("VLM did not return parseable JSON")
        logger.error(f"Response: {response[:500]}")
        raise ValueError(
            f"VLM response is not valid JSON. Response preview: {response[:300]}"
        )


hypothesis_extractor = HypothesisExtractor()
