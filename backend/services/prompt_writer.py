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
        The VLM is NOT used here - we rely on the pre-extracted style rules.
        """
        # Build the positive prompt
        prompt_parts = []

        # 1. Subject comes first
        prompt_parts.append(subject.strip())

        # 2. Add additional context if provided
        if additional_context:
            prompt_parts.append(additional_context.strip())

        # 3. Add technique keywords (painting style, medium)
        if style_rules.technique_keywords:
            prompt_parts.extend(style_rules.technique_keywords[:3])

        # 4. Add palette description
        palette = style_profile.palette
        color_desc = ", ".join(palette.color_descriptions[:3]) if palette.color_descriptions else None
        if color_desc:
            prompt_parts.append(f"color palette of {color_desc}")
        prompt_parts.append(f"{palette.saturation} saturation")

        # 5. Add lighting
        lighting = style_profile.lighting
        prompt_parts.append(lighting.lighting_type)
        if "soft" in lighting.shadows.lower() or "diffuse" in lighting.shadows.lower():
            prompt_parts.append("soft shadows")
        elif "hard" in lighting.shadows.lower():
            prompt_parts.append("hard shadows")

        # 6. Add texture/surface quality
        texture = style_profile.texture
        prompt_parts.append(texture.surface)
        if texture.special_effects:
            prompt_parts.extend(texture.special_effects[:2])

        # 7. Add mood keywords
        if style_rules.mood_keywords:
            prompt_parts.extend(style_rules.mood_keywords[:2])

        # 8. Add "always include" rules
        if style_rules.always_include:
            prompt_parts.extend(style_rules.always_include[:3])

        # 9. Add emphasis from training feedback
        if style_rules.emphasize:
            prompt_parts.extend(style_rules.emphasize[:2])

        # 10. Add composition hints
        composition = style_profile.composition
        if "centered" in composition.framing.lower():
            prompt_parts.append("centered composition")
        elif "rule of thirds" in composition.framing.lower():
            prompt_parts.append("rule of thirds composition")

        # 11. Add recurring motifs
        if style_profile.motifs.recurring_elements:
            for motif in style_profile.motifs.recurring_elements[:2]:
                if motif.lower() not in subject.lower():
                    prompt_parts.append(motif)

        # Clean and join
        positive_prompt = ", ".join(
            part for part in prompt_parts
            if part and len(part.strip()) > 0
        )

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
            "technique": style_rules.technique_keywords[:3] if style_rules.technique_keywords else [],
            "palette": color_desc,
            "lighting": lighting.lighting_type,
            "texture": texture.surface,
            "mood": style_rules.mood_keywords[:2] if style_rules.mood_keywords else [],
            "style_rules_applied": len(style_rules.always_include) + len(style_rules.emphasize),
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
        feedback_history: list[dict] | None = None,
    ) -> StyleRules:
        """
        Extract style rules from a style profile and optional feedback history.
        Called when finalizing a training session into a trained style.
        """
        rules = StyleRules()

        # Extract technique keywords from texture and line quality
        technique = []
        if style_profile.texture.surface:
            # Extract key technique words
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

        line_quality = style_profile.line_and_shape.line_quality.lower()
        if "soft" in line_quality:
            technique.append("soft edges")
        if "sharp" in line_quality or "crisp" in line_quality:
            technique.append("sharp details")
        if "sketch" in line_quality:
            technique.append("sketch-like lines")

        rules.technique_keywords = technique[:5]

        # Extract mood keywords from lighting and overall profile
        mood = []
        lighting_type = style_profile.lighting.lighting_type.lower()
        if "warm" in lighting_type or "golden" in lighting_type:
            mood.append("warm atmosphere")
        if "cool" in lighting_type or "blue" in lighting_type:
            mood.append("cool atmosphere")
        if "dramatic" in lighting_type:
            mood.append("dramatic mood")
        if "soft" in lighting_type or "diffuse" in lighting_type:
            mood.append("soft ambiance")
        if "twilight" in lighting_type or "dusk" in lighting_type:
            mood.append("twilight mood")
        if "moody" in lighting_type:
            mood.append("moody atmosphere")

        rules.mood_keywords = mood[:4]

        # Always include from core invariants
        rules.always_include = style_profile.core_invariants[:5]

        # Always avoid from forbidden elements
        rules.always_avoid = style_profile.motifs.forbidden_elements[:5]

        # Process feedback history if provided
        if feedback_history:
            approved_notes = []
            rejected_notes = []

            for feedback in feedback_history:
                if feedback.get("approved") and feedback.get("notes"):
                    approved_notes.append(feedback["notes"])
                elif not feedback.get("approved") and feedback.get("notes"):
                    rejected_notes.append(feedback["notes"])

            # Extract common themes from approved feedback → emphasize
            # Extract common themes from rejected feedback → de-emphasize
            # For now, just store the notes directly
            if approved_notes:
                rules.emphasize = approved_notes[:3]
            if rejected_notes:
                rules.de_emphasize = rejected_notes[:3]

        return rules


prompt_writer = PromptWriter()
