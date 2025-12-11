import asyncio
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

        # Retry loop for VLM + parsing (up to 3 attempts)
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                # Send both images for proper comparison
                await log(f"Sending both images to VLM for comparison (attempt {attempt + 1}/{max_retries})...")
                response = await vlm_service.analyze(
                    prompt=prompt,
                    images=[original_image_b64, generated_image_b64],
                    request_id=session_id,
                    max_retries=1,  # VLM has its own retry, but we'll handle parsing retries here
                )
                await log(f"VLM response received ({len(response)} chars)", "success")

                # Parse JSON from response
                await log("Parsing VLM response...")
                result_dict = self._parse_json_response(response, style_profile)
                scores = result_dict.get("match_scores", {})
                await log(f"Parsed scores - Overall: {scores.get('overall', 'N/A')}, Palette: {scores.get('palette', 'N/A')}", "success")

                # Success! Break out of retry loop
                break

            except ValueError as e:
                # JSON parsing error - retry
                last_error = e
                if attempt < max_retries - 1:
                    await log(f"Parsing failed (attempt {attempt + 1}/{max_retries}): {e}", "warning")
                    await log(f"Raw response: {response[:300]}...", "warning")
                    await log("Retrying VLM request...", "info")
                    await asyncio.sleep(2)  # Brief pause before retry
                else:
                    await log(f"All {max_retries} parsing attempts failed", "error")
                    await log(f"Final response: {response[:500]}", "error")
                    raise
            except Exception as e:
                # Other errors (connection, etc) - don't retry
                await log(f"VLM request failed: {e}", "error")
                raise

        # If we exited loop without breaking, raise the last error
        if last_error and attempt == max_retries - 1:
            raise last_error

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

        await log("Building critique result...")

        # Fix VLM type mismatches before validation
        # Sometimes VLM returns lists instead of strings for certain fields
        try:
            updated_profile = result_dict.get("updated_style_profile", {})

            # Fix geometry_notes: should be string, not list
            if "line_and_shape" in updated_profile:
                geometry_notes = updated_profile["line_and_shape"].get("geometry_notes", "")
                if isinstance(geometry_notes, list):
                    # Convert list to string (join if multiple items, empty string if empty)
                    updated_profile["line_and_shape"]["geometry_notes"] = ", ".join(geometry_notes) if geometry_notes else ""
                    await log(f"Fixed geometry_notes type: list -> string", "warning")

            # Fix structural_notes: should be string, not list
            if "composition" in updated_profile:
                structural_notes = updated_profile["composition"].get("structural_notes", "")
                if isinstance(structural_notes, list):
                    updated_profile["composition"]["structural_notes"] = ", ".join(structural_notes) if structural_notes else ""
                    await log(f"Fixed structural_notes type: list -> string", "warning")

            # Fix special_effects: should be list, not string
            if "texture" in updated_profile:
                special_effects = updated_profile["texture"].get("special_effects", [])
                if isinstance(special_effects, str):
                    # Convert string to list (split on comma if has commas, otherwise empty list if empty string)
                    updated_profile["texture"]["special_effects"] = [e.strip() for e in special_effects.split(",") if e.strip()] if special_effects else []
                    await log(f"Fixed special_effects type: string -> list", "warning")

            result_dict["updated_style_profile"] = updated_profile
        except Exception as e:
            await log(f"Warning: Failed to fix VLM type mismatches: {e}", "warning")

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

    def _try_repair_truncated_json(self, response: str) -> dict | None:
        """
        Attempt to salvage data from truncated VLM JSON responses.

        The VLM often returns valid JSON that gets cut off at the end (token limits).
        This method extracts what we can, especially the critical match_scores.

        Returns dict with salvaged data, or None if nothing usable found.
        """
        import re

        result = {}

        # Extract match_scores object - this is the critical data we need
        # Pattern matches "match_scores": { ... } with nested content
        scores_pattern = r'"match_scores"\s*:\s*\{([^}]+)\}'
        scores_match = re.search(scores_pattern, response)
        if scores_match:
            try:
                scores_str = "{" + scores_match.group(1) + "}"
                # Clean up any trailing issues
                scores_str = re.sub(r',\s*}', '}', scores_str)  # Remove trailing commas
                scores_dict = json.loads(scores_str)
                result["match_scores"] = scores_dict
                logger.info(f"[repair] Salvaged match_scores from truncated JSON: {scores_dict}")
            except Exception as e:
                logger.warning(f"[repair] Could not parse match_scores: {e}")

        # Extract array fields with a more robust pattern
        for field in ["preserved_traits", "lost_traits", "interesting_mutations"]:
            # Match the field name followed by an array
            pattern = rf'"{field}"\s*:\s*\[((?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*)\]'
            match = re.search(pattern, response)
            if match:
                try:
                    array_str = "[" + match.group(1) + "]"
                    # Clean up the array string
                    array_str = re.sub(r',\s*]', ']', array_str)  # Remove trailing commas
                    result[field] = json.loads(array_str)
                except Exception as e:
                    logger.warning(f"[repair] Could not parse {field}: {e}")
                    result[field] = []
            else:
                result[field] = []

        # If we got match_scores, this repair was successful
        if "match_scores" in result and result["match_scores"]:
            # Validate that we have the essential score fields
            scores = result["match_scores"]
            required_fields = ["palette", "line_and_shape", "texture", "lighting", "composition", "motifs", "overall"]
            if all(field in scores for field in required_fields):
                logger.info(f"[repair] Successfully repaired truncated JSON - extracted all required scores")
                return result
            else:
                missing = [f for f in required_fields if f not in scores]
                logger.warning(f"[repair] Partial repair - missing score fields: {missing}")
                # Still return what we have if we got most fields
                if len([f for f in required_fields if f in scores]) >= 4:
                    return result

        return None

    def _parse_json_response(self, response: str, style_profile: StyleProfile) -> dict:
        """
        Extract JSON from VLM response.

        First tries standard JSON parsing, then falls back to repair logic
        for truncated responses (common with VLM token limits).
        """
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

        # If standard parsing failed, try to repair truncated JSON
        if not parsed:
            logger.warning(f"[critic] Standard JSON parsing failed, attempting truncated JSON repair...")
            repaired = self._try_repair_truncated_json(response)
            if repaired and "match_scores" in repaired:
                logger.info(f"[critic] Using repaired data from truncated response")
                parsed = repaired
                # Mark that we used repair so we know to use current style profile
                parsed["_was_repaired"] = True

        # Still no valid data - fail explicitly
        if not parsed:
            logger.error(f"CRITIC FAILED: Could not parse JSON from VLM response.")
            logger.error(f"Response preview: {response[:500]}")
            raise ValueError(
                f"Critic VLM failed to return valid JSON. This would corrupt training with fake scores. "
                f"Check VLM model capacity or simplify critique prompt. Response: {response[:500]}"
            )

        # Check if this was a repaired truncated response
        was_repaired = parsed.pop("_was_repaired", False)

        # Validate and merge parsed data
        result = {
            "match_scores": {},
            "preserved_traits": [],
            "lost_traits": [],
            "interesting_mutations": [],
            "updated_style_profile": style_profile.model_dump(),
        }

        # Extract match_scores (required)
        if "match_scores" not in parsed or not isinstance(parsed["match_scores"], dict):
            raise ValueError(f"Critic VLM response missing or invalid 'match_scores' field")
        result["match_scores"] = parsed["match_scores"]

        # Extract optional lists (use empty if missing)
        if "preserved_traits" in parsed and isinstance(parsed["preserved_traits"], list):
            result["preserved_traits"] = parsed["preserved_traits"]
        if "lost_traits" in parsed and isinstance(parsed["lost_traits"], list):
            result["lost_traits"] = parsed["lost_traits"]
        if "interesting_mutations" in parsed and isinstance(parsed["interesting_mutations"], list):
            result["interesting_mutations"] = parsed["interesting_mutations"]

        # Extract updated style profile (merge with current if present)
        # If response was repaired from truncation, updated_style_profile is likely missing/corrupt
        if "updated_style_profile" in parsed and isinstance(parsed["updated_style_profile"], dict):
            base_profile = style_profile.model_dump()
            self._deep_merge(base_profile, parsed["updated_style_profile"])
            result["updated_style_profile"] = base_profile
        elif was_repaired:
            logger.info(f"[repair] Using current style profile (VLM response was truncated)")

        return result

    def _deep_merge(self, base: dict, updates: dict) -> None:
        """Deep merge updates into base dict."""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value


style_critic = StyleCritic()
