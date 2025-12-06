"""
Prompt Writer Service

Takes a trained style and a subject, produces a styled prompt ready for image generation.
"""
import logging
import random
from pathlib import Path

from backend.models.schemas import StyleProfile, StyleRules, PromptWriteResponse

logger = logging.getLogger(__name__)


class PromptWriter:
    def __init__(self):
        self.prompt_template_path = Path(__file__).parent.parent / "prompts" / "prompt_writer.md"

    def _select_item(self, items: list, variation_level: int, index: int = 0):
        """Select item from list with variation. Higher variation = more random."""
        if not items:
            return None
        if variation_level == 0:
            # Deterministic - always use specified index
            return items[index] if index < len(items) else items[0]
        elif variation_level < 50:
            # Low variation - slight shuffle, prefer earlier items
            if random.random() < (variation_level / 100):
                return random.choice(items[:min(3, len(items))])
            return items[index] if index < len(items) else items[0]
        else:
            # High variation - random selection from all items
            return random.choice(items)

    def _select_items(self, items: list, count: int, variation_level: int):
        """Select multiple items with variation."""
        if not items:
            return []
        if variation_level == 0:
            # Deterministic - first N items
            return items[:count]
        elif variation_level < 50:
            # Low variation - mostly first items, occasional shuffle
            if random.random() < (variation_level / 100):
                shuffled = items.copy()
                random.shuffle(shuffled)
                return shuffled[:count]
            return items[:count]
        else:
            # High variation - random selection
            available = items.copy()
            random.shuffle(available)
            return available[:min(count, len(available))]

    def _vary_phrasing(self, options: list[str], variation_level: int) -> str:
        """Choose from phrasing options based on variation level."""
        if variation_level == 0 or not options:
            return options[0] if options else ""
        if variation_level < 50:
            # Low variation - prefer first option
            return options[0] if random.random() > 0.3 else random.choice(options)
        else:
            # High variation - random choice
            return random.choice(options)

    def write_prompt(
        self,
        style_profile: StyleProfile,
        style_rules: StyleRules,
        subject: str,
        additional_context: str | None = None,
        include_negative: bool = True,
        variation_level: int = 0,
    ) -> PromptWriteResponse:
        """
        Write a styled prompt from a subject and trained style.

        Constructs a natural-reading prompt with flowing prose that integrates
        the subject with style metadata in human-readable format.

        Args:
            variation_level: 0-100, controls prompt variation
                0 = Always same (deterministic)
                50 = Moderate variation (shuffled keywords, varied phrasing)
                100 = Maximum variation (random selection, different structures)
        """
        palette = style_profile.palette
        lighting = style_profile.lighting
        texture = style_profile.texture
        line_shape = style_profile.line_and_shape
        composition = style_profile.composition

        # Build prompt as natural flowing sentences
        # NOTE: Subject is NOT included - only style information
        sentences = []

        # === SENTENCE 1: Style Technique ===
        opening_parts = []

        # Add primary technique - use variation to select
        if style_rules.technique_keywords and len(style_rules.technique_keywords) > 0:
            technique = self._select_item(style_rules.technique_keywords, variation_level, index=0)
            # Vary phrasing
            phrasing = self._vary_phrasing([
                f"Rendered in {technique}",
                f"Created in {technique}",
                f"Styled as {technique}",
                f"{technique.capitalize()}"
            ], variation_level)
            opening_parts.append(phrasing)
        elif texture.surface:
            # Fallback to texture description as technique
            opening_parts.append(f"Created with {texture.surface}")

        # Add style name if meaningful
        if style_profile.style_name and style_profile.style_name.lower() not in ["extracted style", "unnamed style"]:
            opening_parts.append(f"{style_profile.style_name} style")

        if opening_parts:
            sentences.append(". ".join(opening_parts))

        # === SENTENCE 2: Color Palette ===
        if palette.color_descriptions and len(palette.color_descriptions) > 0:
            # Use variation to select colors (3-5 colors)
            color_count = 4 if variation_level < 50 else random.randint(3, min(5, len(palette.color_descriptions)))
            colors = self._select_items(palette.color_descriptions, color_count, variation_level)

            # Build natural color description with varied phrasing
            if len(colors) == 1:
                color_desc = self._vary_phrasing([
                    f"The color palette features {colors[0]}",
                    f"Dominated by {colors[0]} tones",
                    f"Features {colors[0]}"
                ], variation_level)
            elif len(colors) == 2:
                color_desc = self._vary_phrasing([
                    f"The scene features {colors[0]} and {colors[1]} tones",
                    f"Combines {colors[0]} with {colors[1]}",
                    f"Features {colors[0]} and {colors[1]} hues"
                ], variation_level)
            elif len(colors) >= 3:
                main_colors = ", ".join(colors[:-1])
                color_desc = self._vary_phrasing([
                    f"The composition uses {main_colors}, and {colors[-1]} tones",
                    f"Features a palette of {main_colors}, and {colors[-1]}",
                    f"Combines {main_colors} with {colors[-1]} accents"
                ], variation_level)

            # Add accent colors if available
            if palette.accents and len(palette.accents) > 0:
                accent_names = palette.color_descriptions[len(palette.dominant_colors):len(palette.dominant_colors) + 2]
                if accent_names:
                    if len(accent_names) == 1:
                        color_desc += f" with {accent_names[0]} accents"
                    else:
                        color_desc += f" with {' and '.join(accent_names)} accents"

            # Add saturation level
            if palette.saturation:
                sat = palette.saturation.lower()
                if "high" in sat or "vivid" in sat:
                    color_desc += ", creating a vibrant appearance"
                elif "low" in sat or "muted" in sat:
                    color_desc += ", creating a muted and subtle appearance"
                elif "medium" in sat:
                    color_desc += " with balanced saturation"

            sentences.append(color_desc)

        # === SENTENCE 3: Lighting + Atmosphere ===
        lighting_parts = []

        if lighting.lighting_type:
            # Check if lighting_type is a full phrase or just a word
            lighting_type = lighting.lighting_type.strip()
            if len(lighting_type.split()) == 1:
                # Single word like "subtle" - needs context
                lighting_parts.append(f"The scene features {lighting_type} lighting")
            else:
                # Full phrase like "soft ambient lighting"
                lighting_parts.append(f"The scene is illuminated by {lighting_type}")

        if lighting.shadows:
            shadows = lighting.shadows.strip()
            if lighting_parts:
                lighting_parts.append(f"with {shadows}")
            else:
                lighting_parts.append(f"The scene features {shadows}")

        if lighting.highlights:
            highlights = lighting.highlights.strip()
            if lighting_parts:
                lighting_parts.append(f"and {highlights}")
            else:
                lighting_parts.append(f"The scene features {highlights}")

        # Add mood keywords - use variation to select
        if style_rules.mood_keywords and len(style_rules.mood_keywords) > 0:
            mood = self._select_item(style_rules.mood_keywords, variation_level, index=0)
            if lighting_parts:
                mood_phrase = self._vary_phrasing([
                    f"creating {mood}",
                    f"evoking {mood}",
                    f"with {mood}"
                ], variation_level)
                lighting_parts.append(mood_phrase)
            else:
                mood_phrase = self._vary_phrasing([
                    f"The atmosphere features {mood}",
                    f"Atmosphere: {mood}",
                    f"{mood.capitalize()} mood"
                ], variation_level)
                lighting_parts.append(mood_phrase)

        if lighting_parts:
            sentences.append(", ".join(lighting_parts))

        # === SENTENCE 4: Texture + Surface Quality ===
        texture_parts = []

        # Core texture description
        if texture.surface:
            texture_parts.append(texture.surface.capitalize())

        # Add technique details
        if style_rules.technique_keywords and len(style_rules.technique_keywords) > 1:
            for technique in style_rules.technique_keywords[1:3]:
                if technique.lower() not in texture.surface.lower():  # Avoid repetition
                    texture_parts.append(technique)

        # Add special effects
        if texture.special_effects and len(texture.special_effects) > 0:
            effects_str = " and ".join(texture.special_effects[:2])
            texture_parts.append(effects_str)

        if texture_parts:
            texture_sentence = " with ".join(texture_parts[:2])
            if len(texture_parts) > 2:
                texture_sentence += f", featuring {', '.join(texture_parts[2:])}"
            sentences.append(texture_sentence + " throughout")

        # === SENTENCE 5: Line Quality + Shape Language ===
        form_parts = []

        if line_shape.line_quality:
            form_parts.append(line_shape.line_quality.capitalize())

        if line_shape.shape_language:
            shape_desc = line_shape.shape_language
            if "organic" in shape_desc.lower():
                form_parts.append("flowing organic forms")
            elif "geometric" in shape_desc.lower():
                form_parts.append("geometric shapes")
            elif "angular" in shape_desc.lower():
                form_parts.append("angular forms")
            else:
                form_parts.append(f"{shape_desc} shapes")

        if form_parts:
            sentences.append(" and ".join(form_parts) + " define the visual structure")

        # === SENTENCE 6: Composition + Framing ===
        comp_parts = []

        if composition.framing:
            framing = composition.framing.lower()
            if "center" in framing:
                comp_parts.append("The composition places the subject centrally in the frame")
            elif "rule of thirds" in framing or "thirds" in framing:
                comp_parts.append("The composition follows the rule of thirds")
            elif "asymmetric" in framing:
                comp_parts.append("The composition uses asymmetric framing")
            else:
                comp_parts.append(f"The composition uses {composition.framing}")

        if composition.camera:
            camera = composition.camera.lower()
            if "eye level" in camera:
                comp_parts.append("at eye level perspective")
            elif "low" in camera:
                comp_parts.append("from a low angle perspective")
            elif "high" in camera or "bird" in camera:
                comp_parts.append("from an elevated perspective")
            else:
                comp_parts.append(f"with {composition.camera} camera angle")

        if comp_parts:
            sentences.append(" ".join(comp_parts))

        # === SENTENCE 7: Core Invariants (Important Style Anchors) ===
        # NOTE: Only include TRUE STYLE invariants, not subject-specific ones
        # Subject-specific: "Black cat facing left", "Person standing centered"
        # Style invariants: "Impressionistic style with bold brushstrokes"
        if style_profile.core_invariants and len(style_profile.core_invariants) > 0:
            # Filter to only style invariants (skip subject-specific ones)
            style_invariants = []

            # Keywords that indicate subject-specific descriptions (not style)
            subject_keywords = [
                "cat", "dog", "person", "human", "animal", "bird", "fish",
                "facing", "centered", "standing", "sitting", "lying",
                "positioned", "placed", "located", "foreground", "background",
                "subject", "figure", "character", "creature",
                "left", "right", "front", "back", "side view"
            ]

            for invariant in style_profile.core_invariants:
                invariant_lower = invariant.lower()

                # Check if it's subject-specific
                is_subject_specific = any(keyword in invariant_lower for keyword in subject_keywords)

                if not is_subject_specific:
                    # This is a true style invariant
                    style_invariants.append(invariant)

            # Add up to 2 style invariants (not subject-specific)
            for invariant in style_invariants[:2]:
                # Skip if already mentioned
                invariant_lower = invariant.lower()
                prompt_so_far = " ".join(sentences).lower()
                if invariant_lower not in prompt_so_far:
                    sentences.append(invariant.capitalize())

        # === SENTENCE 8: Additional Context ===
        if additional_context and additional_context.strip():
            sentences.append(additional_context.strip())

        # === SENTENCE 9: Training Emphasis (What to emphasize) ===
        # NOTE: Also filter out subject-specific emphasis items
        if style_rules.emphasize and len(style_rules.emphasize) > 0:
            # Filter out subject-specific emphasis items
            subject_keywords = [
                "cat", "dog", "person", "human", "animal", "bird", "fish",
                "facing", "centered", "standing", "sitting", "lying",
                "positioned", "placed", "located", "foreground", "background",
                "subject", "figure", "character", "creature",
                "left", "right", "front", "back", "side view",
                "expression", "face", "eyes", "gaze", "look"
            ]

            # Add 1-2 top emphasis items that aren't already mentioned AND aren't subject-specific
            prompt_so_far_lower = " ".join(sentences).lower()
            for emphasis in style_rules.emphasize[:5]:  # Check more since we're filtering
                emphasis_lower = emphasis.lower()

                # Skip if subject-specific
                is_subject_specific = any(keyword in emphasis_lower for keyword in subject_keywords)
                if is_subject_specific:
                    continue

                # Skip if already mentioned
                if emphasis_lower not in prompt_so_far_lower:
                    sentences.append(emphasis.capitalize())
                    # Only add up to 2 emphasis items
                    if len([s for s in sentences if s.lower() in [e.lower() for e in style_rules.emphasize]]) >= 2:
                        break

        # Join sentences with proper punctuation
        positive_prompt = ". ".join(s.strip().rstrip('.') for s in sentences if s.strip()) + "."

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
            subject=subject,  # Subject returned separately
            style_prompt=positive_prompt,  # Only style information
            positive_prompt=f"{subject.strip()}. {positive_prompt}",  # Combined for convenience
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

            # Add approved feedback notes (skip if they're system messages)
            for note in approved_notes[:2]:
                # Only add if it's a user note, not a system message
                if not note.startswith(("PASS", "FAIL", "Weighted")):
                    emphasize.append(note)

            # De-emphasize: Don't include rejected notes (they're system messages)
            # Instead, rely on lost_traits which are actual visual elements
            # rejected_notes contain things like "FAIL: Weighted Δ=-54.0..." which are debug info
            pass  # Intentionally not adding rejected_notes to de_emphasize

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
