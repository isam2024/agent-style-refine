import json
import logging
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.services.color_extractor import extract_colors_from_b64, color_distance, hex_to_rgb
from backend.models.schemas import StyleProfile, CritiqueResult
from backend.websocket import manager

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
        return """You are a STYLE CRITIC comparing two images for style consistency.

You are given TWO IMAGES:
- IMAGE 1 (first/left): The ORIGINAL REFERENCE image that defines the target style
- IMAGE 2 (second/right): The GENERATED image that attempts to replicate that style

You also have:
- The TARGET STYLE PROFILE (JSON) extracted from the original
- IMAGE DESCRIPTION: A natural language description of the original image
- COLOR ANALYSIS comparing the palettes

ORIGINAL IMAGE DESCRIPTION:
{{IMAGE_DESCRIPTION}}

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
        session_id: str | None = None,
    ) -> CritiqueResult:
        """
        Critique a generated image against the original style.
        Works with single-image VLMs by analyzing generated image + style profile.

        Args:
            original_image_b64: Base64 encoded reference image (used for color comparison)
            generated_image_b64: Base64 encoded generated image
            style_profile: Current style profile
            creativity_level: 0-100, controls how much mutation is allowed
            session_id: Optional session ID for WebSocket logging

        Returns:
            CritiqueResult with scores, analysis, and updated profile
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[critique] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "critique")

        generated_colors = None

        # Extract colors from both images using PIL for accurate comparison
        await log("Extracting colors from original image...")
        try:
            original_colors = extract_colors_from_b64(original_image_b64)
            orig_color_list = ", ".join(original_colors.get("color_descriptions", [])[:3])
            await log(f"Original colors: {orig_color_list}")
        except Exception as e:
            await log(f"Original color extraction failed: {e}", "warning")
            original_colors = None

        await log("Extracting colors from generated image...")
        try:
            generated_colors = extract_colors_from_b64(generated_image_b64)
            gen_color_list = ", ".join(generated_colors.get("color_descriptions", [])[:3])
            await log(f"Generated colors: {gen_color_list}")
        except Exception as e:
            await log(f"Generated color extraction failed: {e}", "warning")
            generated_colors = None

        if original_colors and generated_colors:
            await log("Comparing color palettes...")
            color_analysis = self._compare_colors(
                style_profile.palette.dominant_colors,
                generated_colors["dominant_colors"],
                original_colors,
                generated_colors,
            )
            await log("Color comparison complete")
        else:
            color_analysis = "Color analysis unavailable."
            await log("Skipping color comparison due to extraction errors", "warning")

        await log("Loading critique prompt template...")
        prompt_template = self._load_prompt()

        # Fill in template
        image_description = style_profile.image_description or "No description available."
        prompt = prompt_template.replace(
            "{{CREATIVITY_LEVEL}}", str(creativity_level)
        ).replace(
            "{{STYLE_PROFILE}}", json.dumps(style_profile.model_dump(), indent=2)
        ).replace(
            "{{COLOR_ANALYSIS}}", color_analysis
        ).replace(
            "{{IMAGE_DESCRIPTION}}", image_description
        )

        await log("Connecting to VLM for style critique...")
        await log(f"Prompt length: {len(prompt)} characters")

        # Send both images for proper comparison
        try:
            await log("Sending both images to VLM for comparison...")
            response = await vlm_service.analyze(
                prompt=prompt,
                images=[original_image_b64, generated_image_b64],
            )
            await log(f"VLM response received ({len(response)} chars)", "success")
        except Exception as e:
            await log(f"VLM request failed: {e}", "error")
            raise

        # Parse JSON from response
        await log("Parsing VLM response...")
        try:
            result_dict = self._parse_json_response(response, style_profile)
            scores = result_dict.get("match_scores", {})
            await log(f"Parsed scores - Overall: {scores.get('overall', 'N/A')}, Palette: {scores.get('palette', 'N/A')}", "success")
        except Exception as e:
            await log(f"Response parsing failed: {e}", "error")
            await log(f"Raw response preview: {response[:300]}...", "warning")
            raise

        # Update palette in the result with PIL-extracted colors if available
        if generated_colors:
            try:
                await log("Applying extracted colors to updated profile...")
                updated_profile = result_dict.get("updated_style_profile", {})
                if "palette" not in updated_profile:
                    updated_profile["palette"] = style_profile.palette.model_dump()
                updated_profile["palette"]["dominant_colors"] = generated_colors["dominant_colors"]
                updated_profile["palette"]["accents"] = generated_colors["accents"]
                updated_profile["palette"]["color_descriptions"] = generated_colors["color_descriptions"]
                result_dict["updated_style_profile"] = updated_profile
            except Exception as e:
                await log(f"Failed to update palette in critique result: {e}", "warning")

        # Process vectorized corrections and update feature confidence
        corrections = result_dict.get("corrections", [])
        if corrections:
            await log(f"Processing {len(corrections)} vectorized corrections...")

            # Update feature confidence based on corrections
            updated_profile = result_dict.get("updated_style_profile", {})
            if updated_profile and "feature_registry" in updated_profile:
                feature_registry = updated_profile["feature_registry"]
                features = feature_registry.get("features", {})

                # Track which features appeared in corrections (present in generated image)
                corrected_feature_ids = {corr["feature_id"] for corr in corrections if isinstance(corr, dict)}

                await log(f"Updating confidence for {len(features)} features...")
                for feature_id, feature in features.items():
                    appeared_in_generated = feature_id in corrected_feature_ids
                    old_confidence = feature.get("confidence", 0.5)
                    new_confidence = self._update_feature_confidence(feature, appeared_in_generated)

                    if abs(new_confidence - old_confidence) > 0.05:  # Log significant changes
                        direction = "↑" if new_confidence > old_confidence else "↓"
                        await log(f"  {feature_id}: {old_confidence:.2f} {direction} {new_confidence:.2f}")

                # Log correction summary
                direction_counts = {}
                high_confidence_corrections = []
                for corr in corrections:
                    if isinstance(corr, dict):
                        direction = corr.get("direction", "unknown")
                        direction_counts[direction] = direction_counts.get(direction, 0) + 1
                        if corr.get("confidence", 0) >= 0.8:
                            high_confidence_corrections.append(f"{corr['feature_id']}:{direction}")

                await log(f"Correction directions: {', '.join([f'{k}={v}' for k, v in direction_counts.items()])}")
                if high_confidence_corrections:
                    await log(f"High-confidence corrections (>0.8): {', '.join(high_confidence_corrections[:5])}")
            else:
                await log("No feature_registry in updated profile - skipping confidence updates", "warning")
        else:
            await log("No corrections provided by VLM (may be using old critic prompt)", "warning")

        await log("Building critique result...")
        try:
            critique_result = CritiqueResult(**result_dict)
            await log("Critique result created successfully", "success")
            return critique_result
        except Exception as e:
            await log(f"Failed to create CritiqueResult: {e}", "error")
            await log(f"Result dict keys: {list(result_dict.keys())}", "error")
            raise

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

    def _update_feature_confidence(self, feature: dict, appeared_in_iteration: bool) -> float:
        """
        Update confidence score for a feature based on persistence.

        Confidence increases when:
        - Feature appears in both original AND generated (appeared_in_iteration=True)
        - Feature persists across multiple iterations

        Confidence decreases when:
        - Feature disappears in generated image (appeared_in_iteration=False)
        - Feature only appeared in 1-2 iterations (likely coincidence)

        Args:
            feature: Feature dict with confidence, persistence_count
            appeared_in_iteration: True if feature was mentioned in corrections (present in generated)

        Returns:
            Updated confidence score (0.0-1.0)
        """
        current_confidence = feature.get("confidence", 0.5)
        persistence_count = feature.get("persistence_count", 1)

        if appeared_in_iteration:
            # Feature appeared - boost confidence
            feature["persistence_count"] = persistence_count + 1

            # Confidence grows with persistence (logarithmic curve)
            # 1 iteration = 0.3, 3 iterations = 0.6, 5+ iterations = 0.85+
            new_persistence = feature["persistence_count"]
            persistence_factor = min(1.0, 0.3 + (0.15 * new_persistence))

            # Smooth update (moving average: 70% old, 30% new)
            new_confidence = 0.7 * current_confidence + 0.3 * persistence_factor
        else:
            # Feature disappeared - penalize confidence
            decay = 0.15  # Confidence drops by 15% per missed iteration
            new_confidence = current_confidence * (1.0 - decay)

        # Clamp to valid range
        new_confidence = max(0.0, min(1.0, new_confidence))

        # Update in-place
        feature["confidence"] = new_confidence

        return new_confidence

    def _parse_json_response(self, response: str, style_profile: StyleProfile) -> dict:
        """Extract JSON from VLM response, with fallback to defaults."""
        import re

        parsed = None

        # Try direct parsing first
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code block
        if not parsed:
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                except:
                    pass

        # Try to find raw JSON object (greedy match for nested objects)
        if not parsed:
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                except:
                    pass

        # Build result with defaults, merging any parsed data
        result = {
            "match_scores": {
                "palette": 70,
                "line_and_shape": 70,
                "texture": 70,
                "lighting": 70,
                "composition": 70,
                "motifs": 70,
                "overall": 70,
            },
            "preserved_traits": [],
            "lost_traits": [],
            "interesting_mutations": [],
            "updated_style_profile": style_profile.model_dump(),
        }

        if parsed:
            # Merge parsed data into result
            if "match_scores" in parsed and isinstance(parsed["match_scores"], dict):
                result["match_scores"].update(parsed["match_scores"])
            if "preserved_traits" in parsed and isinstance(parsed["preserved_traits"], list):
                result["preserved_traits"] = parsed["preserved_traits"]
            if "lost_traits" in parsed and isinstance(parsed["lost_traits"], list):
                result["lost_traits"] = parsed["lost_traits"]
            if "interesting_mutations" in parsed and isinstance(parsed["interesting_mutations"], list):
                result["interesting_mutations"] = parsed["interesting_mutations"]
            if "updated_style_profile" in parsed and isinstance(parsed["updated_style_profile"], dict):
                # Merge the parsed profile with defaults from current style
                base_profile = style_profile.model_dump()
                self._deep_merge(base_profile, parsed["updated_style_profile"])
                result["updated_style_profile"] = base_profile
        else:
            logger.warning(f"Could not parse JSON from VLM response, using defaults. Response: {response[:300]}")

        # Normalize feature_registry.features type (VLM may return [] instead of {})
        if "updated_style_profile" in result:
            profile = result["updated_style_profile"]
            if "feature_registry" in profile:
                registry = profile["feature_registry"]
                if "features" in registry and isinstance(registry["features"], list):
                    logger.warning(f"VLM returned features as list, converting to dict. Input: {registry['features']}")
                    registry["features"] = {}

        return result

    def _deep_merge(self, base: dict, updates: dict) -> None:
        """Deep merge updates into base dict."""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value


style_critic = StyleCritic()
