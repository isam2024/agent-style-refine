"""
Prompt Writer Service

Takes a trained style and a subject, produces a styled prompt ready for image generation.
"""
import logging
from pathlib import Path

from backend.models.schemas import StyleProfile, StyleRules, PromptWriteResponse

logger = logging.getLogger(__name__)


class PromptWriter:
    def __init__(self):
        self.prompt_template_path = Path(__file__).parent.parent / "prompts" / "prompt_writer.md"

    def write_prompt(
        self,
        style_profile: StyleProfile,
        style_rules: StyleRules,
        subject: str,
        additional_context: str | None = None,
        include_negative: bool = True,
    ) -> PromptWriteResponse:
        """
        Write a styled prompt from a subject and trained style.

        This uses a deterministic template-based approach for consistency.
        Constructs a natural-reading prompt that integrates the subject with style metadata.
        """
        palette = style_profile.palette
        lighting = style_profile.lighting
        texture = style_profile.texture
        line_shape = style_profile.line_and_shape
        composition = style_profile.composition

        # Build an integrated prompt that reads naturally
        prompt_segments = []

        # === SEGMENT 1: Subject with immediate style context ===
        # If we have an image description, use it as a style template
        if style_profile.image_description:
            # Use image description but inject our subject
            # The description is already style-rich
            desc = style_profile.image_description
            # Try to replace the original subject if we can identify it
            if style_profile.original_subject:
                # Simple replacement strategy
                desc_lower = desc.lower()
                orig_subject_lower = style_profile.original_subject.lower()
                if orig_subject_lower in desc_lower:
                    desc = desc.replace(style_profile.original_subject, subject)
                else:
                    # Prepend new subject
                    prompt_segments.append(subject.strip())
                    prompt_segments.append(desc)
            else:
                # Prepend new subject
                prompt_segments.append(subject.strip())
                prompt_segments.append(desc)
        else:
            # No description - build from scratch
            # Start with subject + core technique
            subject_with_technique = subject.strip()
            if style_rules.technique_keywords:
                subject_with_technique += f", {style_rules.technique_keywords[0]}"
            prompt_segments.append(subject_with_technique)

            # Add style name
            prompt_segments.append(f"{style_profile.style_name} style")

        # === SEGMENT 2: Core invariants (most important) ===
        if style_profile.core_invariants:
            prompt_segments.extend(style_profile.core_invariants[:3])

        # === SEGMENT 3: Color palette (specific colors) ===
        if palette.color_descriptions:
            colors = palette.color_descriptions[:4]
            prompt_segments.append(f"colors: {', '.join(colors)}")

        # === SEGMENT 4: Lighting (key atmosphere driver) ===
        if lighting.lighting_type:
            prompt_segments.append(lighting.lighting_type)
        if lighting.shadows:
            prompt_segments.append(f"with {lighting.shadows} shadows")
        if lighting.highlights:
            prompt_segments.append(lighting.highlights)

        # === SEGMENT 5: Texture/surface ===
        if texture.surface:
            prompt_segments.append(texture.surface)
        if texture.special_effects:
            prompt_segments.extend(texture.special_effects[:2])

        # === SEGMENT 6: Line/shape quality ===
        if line_shape.line_quality:
            prompt_segments.append(line_shape.line_quality)
        if line_shape.shape_language:
            prompt_segments.append(f"{line_shape.shape_language} forms")

        # === SEGMENT 7: Composition/framing ===
        if composition.camera:
            prompt_segments.append(composition.camera)
        if composition.framing:
            prompt_segments.append(composition.framing)

        # === SEGMENT 8: Additional technique keywords ===
        if style_rules.technique_keywords:
            prompt_segments.extend(style_rules.technique_keywords[1:4])

        # === SEGMENT 9: Mood/atmosphere ===
        if style_rules.mood_keywords:
            prompt_segments.extend(style_rules.mood_keywords[:3])

        # === SEGMENT 10: Always include from training ===
        if style_rules.always_include:
            prompt_segments.extend(style_rules.always_include[:5])

        # === SEGMENT 11: Emphasis from training feedback ===
        if style_rules.emphasize:
            prompt_segments.extend(style_rules.emphasize[:4])

        # === SEGMENT 12: Additional context ===
        if additional_context:
            prompt_segments.append(additional_context.strip())

        # Clean and deduplicate
        seen = set()
        unique_parts = []
        for part in prompt_segments:
            if part and len(part.strip()) > 0:
                part_clean = part.strip()
                normalized = part_clean.lower()
                # Skip empty fields from defaults
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    unique_parts.append(part_clean)

        positive_prompt = ", ".join(unique_parts)

        # Build negative prompt
        negative_prompt = None
        if include_negative:
            negative_parts = []

            # Add forbidden elements from style profile
            if style_profile.motifs.forbidden_elements:
                negative_parts.extend(style_profile.motifs.forbidden_elements)

            # Add "always avoid" from rules
            if style_rules.always_avoid:
                negative_parts.extend(style_rules.always_avoid)

            # Add de-emphasis items
            if style_rules.de_emphasize:
                negative_parts.extend(style_rules.de_emphasize)

            # Common quality negatives
            negative_parts.extend([
                "blurry", "low quality", "distorted", "deformed"
            ])

            negative_prompt = ", ".join(
                part for part in negative_parts
                if part and len(part.strip()) > 0
            )

        # Build breakdown for transparency
        prompt_breakdown = {
            "subject": subject,
            "additional_context": additional_context,
            "technique": style_rules.technique_keywords if style_rules.technique_keywords else [],
            "palette": palette.color_descriptions[:5] if palette.color_descriptions else [],
            "lighting": {
                "type": lighting.lighting_type,
                "shadows": lighting.shadows,
                "highlights": lighting.highlights,
            },
            "texture": {
                "surface": texture.surface,
                "noise": texture.noise_level,
                "effects": texture.special_effects,
            },
            "composition": {
                "camera": composition.camera,
                "framing": composition.framing,
                "negative_space": composition.negative_space_behavior,
            },
            "mood": style_rules.mood_keywords if style_rules.mood_keywords else [],
            "core_invariants": style_profile.core_invariants,
            "always_include": style_rules.always_include,
            "always_avoid": style_rules.always_avoid,
            "emphasize": style_rules.emphasize,
            "de_emphasize": style_rules.de_emphasize,
        }

        return PromptWriteResponse(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            style_name=style_profile.style_name,
            prompt_breakdown=prompt_breakdown,
        )

    def extract_rules_from_profile(
        self,
        style_profile: StyleProfile,
        iteration_history: list[dict] | None = None,
    ) -> StyleRules:
        """
        Extract comprehensive style rules from a style profile and iteration history.
        Called when finalizing a training session into a trained style.

        iteration_history contains:
        - iteration_num, approved, notes, scores, prompt_used
        - preserved_traits, lost_traits, interesting_mutations (from critique)
        """
        rules = StyleRules()

        # ========================================
        # 1. Extract technique keywords from texture, line quality, and composition
        # ========================================
        technique = []

        # From texture/surface
        if style_profile.texture.surface:
            surface_words = style_profile.texture.surface.lower()
            if "oil" in surface_words or "paint" in surface_words:
                technique.append("oil painting style")
            if "watercolor" in surface_words:
                technique.append("watercolor style")
            if "digital" in surface_words:
                technique.append("digital art")
            if "brush" in surface_words or "brushy" in surface_words:
                technique.append("visible brushstrokes")
            if "smooth" in surface_words:
                technique.append("smooth rendering")
            if "grain" in surface_words or "grainy" in surface_words:
                technique.append("film grain")
            if "impasto" in surface_words:
                technique.append("impasto texture")
            if "matte" in surface_words:
                technique.append("matte finish")
            if "glossy" in surface_words:
                technique.append("glossy finish")

        # From line quality
        line_quality = style_profile.line_and_shape.line_quality.lower()
        if "soft" in line_quality:
            technique.append("soft edges")
        if "sharp" in line_quality or "crisp" in line_quality:
            technique.append("sharp details")
        if "sketch" in line_quality:
            technique.append("sketch-like lines")
        if "bold" in line_quality:
            technique.append("bold outlines")
        if "minimal" in line_quality or "none" in line_quality:
            technique.append("no visible outlines")

        # From shape language
        shape_lang = style_profile.line_and_shape.shape_language.lower()
        if "geometric" in shape_lang:
            technique.append("geometric shapes")
        if "organic" in shape_lang:
            technique.append("organic forms")
        if "angular" in shape_lang:
            technique.append("angular shapes")
        if "flowing" in shape_lang or "curved" in shape_lang:
            technique.append("flowing curves")

        # From noise level
        if style_profile.texture.noise_level:
            noise = style_profile.texture.noise_level.lower()
            if "high" in noise:
                technique.append("high noise/grain")
            elif "medium" in noise:
                technique.append("subtle grain")

        rules.technique_keywords = list(dict.fromkeys(technique))[:8]

        # ========================================
        # 2. Extract mood/atmosphere keywords from lighting
        # ========================================
        mood = []
        lighting_type = style_profile.lighting.lighting_type.lower()

        # Temperature
        if "warm" in lighting_type or "golden" in lighting_type:
            mood.append("warm atmosphere")
        if "cool" in lighting_type or "blue" in lighting_type:
            mood.append("cool atmosphere")

        # Intensity/drama
        if "dramatic" in lighting_type:
            mood.append("dramatic lighting")
        if "soft" in lighting_type or "diffuse" in lighting_type:
            mood.append("soft diffused light")
        if "harsh" in lighting_type or "hard" in lighting_type:
            mood.append("harsh lighting")

        # Time of day
        if "twilight" in lighting_type or "dusk" in lighting_type:
            mood.append("twilight atmosphere")
        if "dawn" in lighting_type or "sunrise" in lighting_type:
            mood.append("dawn atmosphere")
        if "night" in lighting_type or "nocturnal" in lighting_type:
            mood.append("nighttime mood")
        if "midday" in lighting_type or "noon" in lighting_type:
            mood.append("bright daylight")

        # Lighting direction
        if "backlit" in lighting_type or "rim" in lighting_type:
            mood.append("backlit subject")
        if "side" in lighting_type:
            mood.append("side lighting")
        if "top" in lighting_type or "overhead" in lighting_type:
            mood.append("overhead lighting")

        # Mood qualifiers
        if "moody" in lighting_type:
            mood.append("moody atmosphere")
        if "ethereal" in lighting_type:
            mood.append("ethereal glow")
        if "cinematic" in lighting_type:
            mood.append("cinematic lighting")

        # From shadows
        shadows = style_profile.lighting.shadows.lower()
        if "deep" in shadows or "dark" in shadows:
            mood.append("deep shadows")
        if "soft" in shadows:
            mood.append("soft shadows")

        # From highlights
        highlights = style_profile.lighting.highlights.lower()
        if "bloom" in highlights or "glow" in highlights:
            mood.append("glowing highlights")
        if "specular" in highlights:
            mood.append("specular highlights")

        rules.mood_keywords = list(dict.fromkeys(mood))[:6]

        # ========================================
        # 3. Always include: Core invariants + key style anchors
        # ========================================
        always_include = list(style_profile.core_invariants[:5])

        # Add palette anchors
        if style_profile.palette.color_descriptions:
            colors = style_profile.palette.color_descriptions[:3]
            always_include.append(f"color palette: {', '.join(colors)}")

        # Add saturation anchor
        if style_profile.palette.saturation:
            always_include.append(f"{style_profile.palette.saturation} saturation")

        # Add value range
        if style_profile.palette.value_range:
            always_include.append(style_profile.palette.value_range)

        # Add composition anchors
        if style_profile.composition.camera:
            always_include.append(f"{style_profile.composition.camera} camera")
        if style_profile.composition.framing:
            always_include.append(f"{style_profile.composition.framing}")

        # Add special effects
        if style_profile.texture.special_effects:
            always_include.extend(style_profile.texture.special_effects[:2])

        rules.always_include = list(dict.fromkeys(always_include))[:10]

        # ========================================
        # 4. Always avoid: Forbidden elements + style breakers
        # ========================================
        always_avoid = list(style_profile.motifs.forbidden_elements[:5])

        # Add common style-breaking elements based on style type
        if style_profile.palette.saturation:
            sat = style_profile.palette.saturation.lower()
            if "low" in sat or "muted" in sat:
                always_avoid.append("oversaturated colors")
            elif "high" in sat or "vivid" in sat:
                always_avoid.append("desaturated colors")

        rules.always_avoid = list(dict.fromkeys(always_avoid))[:8]

        # ========================================
        # 5. Process iteration history for emphasize/de-emphasize
        # ========================================
        emphasize = []
        de_emphasize = []

        if iteration_history:
            all_lost_traits = []
            all_preserved_traits = []
            approved_notes = []
            rejected_notes = []
            low_score_dimensions = {}
            high_score_dimensions = {}

            for iteration in iteration_history:
                # Collect lost traits (need more emphasis)
                if iteration.get("lost_traits"):
                    all_lost_traits.extend(iteration["lost_traits"])

                # Collect preserved traits (working well)
                if iteration.get("preserved_traits"):
                    all_preserved_traits.extend(iteration["preserved_traits"])

                # Collect user feedback notes
                if iteration.get("approved") and iteration.get("notes"):
                    approved_notes.append(iteration["notes"])
                elif not iteration.get("approved") and iteration.get("notes"):
                    rejected_notes.append(iteration["notes"])

                # Track dimension scores
                if iteration.get("scores"):
                    for dim, score in iteration["scores"].items():
                        if dim == "overall":
                            continue
                        if dim not in low_score_dimensions:
                            low_score_dimensions[dim] = []
                            high_score_dimensions[dim] = []
                        if score < 60:
                            low_score_dimensions[dim].append(score)
                        elif score >= 80:
                            high_score_dimensions[dim].append(score)

            # Lost traits that appear multiple times need strong emphasis
            from collections import Counter
            lost_counts = Counter(all_lost_traits)
            frequent_lost = [trait for trait, count in lost_counts.most_common(5) if count > 1]
            emphasize.extend(frequent_lost)

            # Also add any single-occurrence lost traits
            other_lost = [trait for trait in all_lost_traits if trait not in frequent_lost]
            emphasize.extend(other_lost[:3])

            # Add approved feedback notes
            emphasize.extend(approved_notes[:2])

            # De-emphasize: rejected notes
            de_emphasize.extend(rejected_notes[:3])

            # Identify consistently weak dimensions
            weak_dims = []
            for dim, scores in low_score_dimensions.items():
                if len(scores) >= 2:  # Consistently low
                    weak_dims.append(dim)

            # Add dimension-specific emphasis
            for dim in weak_dims[:3]:
                if dim == "palette":
                    emphasize.append("maintain exact color palette")
                elif dim == "lighting":
                    emphasize.append("preserve lighting style")
                elif dim == "texture":
                    emphasize.append("maintain texture quality")
                elif dim == "composition":
                    emphasize.append("follow composition guidelines")
                elif dim == "line_quality":
                    emphasize.append("maintain line quality")

            logger.info(f"Training analysis: {len(all_lost_traits)} lost traits, {len(all_preserved_traits)} preserved")
            logger.info(f"Weak dimensions: {weak_dims}")

        rules.emphasize = list(dict.fromkeys(emphasize))[:8]
        rules.de_emphasize = list(dict.fromkeys(de_emphasize))[:5]

        return rules


prompt_writer = PromptWriter()
