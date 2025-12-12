"""
Style Explorer Service

Divergent exploration of style space - the opposite of the trainer.
Instead of converging to match a reference, this service intentionally
mutates and diverges to discover new aesthetic directions.
"""
import asyncio
import json
import logging
import random
import re
from pathlib import Path

from backend.models.schemas import (
    StyleProfile,
    MutationStrategy,
    ExplorationScores,
    ExplorationSnapshotResponse,
)
from backend.services.vlm import vlm_service
from backend.services.comfyui import comfyui_service
from backend.services.storage import storage_service
from backend.services.extractor import style_extractor
from backend.services.prompt_writer import PromptWriter
from backend.websocket import manager

logger = logging.getLogger(__name__)



class StyleExplorer:
    """
    Service for divergent style exploration.

    Takes a style and intentionally mutates it to discover new directions,
    saving every step as a snapshot for later exploration.
    """

    def __init__(self):
        self.prompt_writer = PromptWriter()
        self.mutation_prompt_path = Path(__file__).parent.parent / "prompts" / "explorer_mutation.md"

    async def extract_base_style(
        self,
        image_b64: str,
        session_id: str | None = None,
    ) -> StyleProfile:
        """
        Extract base style profile from reference image.
        Reuses the standard extractor.
        """
        return await style_extractor.extract(image_b64, session_id)

    async def _mutate_random_dimension(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str, str]:
        """
        Apply random dimension push mutation using VLM.

        Analyzes the style and picks a dimension to push to an extreme.

        Returns:
            (mutated_profile, mutation_description, dimension_key)
        """
        instructions = """Pick ONE style dimension and push it to an EXTREME. Choose from:
- palette.saturation (push to completely desaturated/grayscale OR hyper-saturated neon)
- palette.temperature (push to freezing cold blues OR scorching hot oranges/reds)
- palette.contrast (push to nearly no contrast OR extreme stark contrast)
- line_and_shape.edges (push to impossibly soft/blurry edges OR razor sharp/hard edges)
- line_and_shape.complexity (push to extremely minimal/simple OR infinitely complex/detailed)
- texture.surface (push to perfectly smooth OR extremely rough/textured)
- texture.noise (push to completely clean OR heavily noisy/grainy)
- lighting.intensity (push to nearly black/dark OR blindingly bright/overexposed)
- lighting.direction (push to extreme top-down OR extreme side-lit OR extreme backlit)
- composition.density (push to extremely sparse/empty OR extremely cluttered/dense)
- composition.symmetry (push to perfect rigid symmetry OR chaotic asymmetry)

Choose the dimension that would create the most INTERESTING and DRAMATIC change for this specific style.
Push it to a creative extreme - go beyond realistic into stylized territory."""

        mutated, description = await self._vlm_mutate(
            profile=profile,
            mutation_type="Random Dimension Push",
            mutation_instructions=instructions,
            session_id=session_id,
        )

        # Extract dimension from description for return value
        dimension = "unknown"
        for dim in ["palette", "line_and_shape", "texture", "lighting", "composition"]:
            if dim in description.lower():
                dimension = dim
                break

        return mutated, description, dimension

    async def _mutate_what_if(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply VLM-guided "what if?" mutation.

        Asks the VLM to suggest a wild creative mutation based on the current style.

        Returns:
            (mutated_profile, mutation_description)
        """
        # Summarize current profile for the VLM
        profile_summary = self._summarize_profile(profile)

        what_if_prompt = f"""You are a creative style mutator. Looking at this visual style description, suggest ONE wild "what if?" variation that would create something visually striking and unexpected.

Current style:
{profile_summary}

Think of unexpected, dramatic transformations like:
- "What if this watercolor style used only neon colors?"
- "What if the minimal design became maximally ornate?"
- "What if the lighting came from inside the objects?"
- "What if everything was rendered as stained glass?"
- "What if the shadows were made of liquid gold?"

Suggest a SPECIFIC, DRAMATIC change. Be creative and bold!

Output ONLY valid JSON in this exact format:
{{
    "mutation_idea": "A short description of the creative change (1 sentence)",
    "style_changes": {{
        "palette": {{
            "color_descriptions": ["color1", "color2", "color3", "color4"],
            "saturation": "low/medium/high/extreme"
        }},
        "texture": {{
            "surface": "description of new surface quality"
        }},
        "lighting": {{
            "lighting_type": "description of new lighting"
        }},
        "line_and_shape": {{
            "line_quality": "description of new line treatment",
            "shape_language": "description of new shapes"
        }}
    }}
}}

Only include the fields you want to change. Be bold and creative!"""

        try:
            response = await vlm_service.generate_text(
                prompt=what_if_prompt,
                system="You are a creative AI that suggests bold, unexpected style mutations. Output only valid JSON.",
                use_text_model=True,
            )

            # Parse response
            response = response.strip()
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            mutation_idea = data.get("mutation_idea", "Creative mutation")
            style_changes = data.get("style_changes", {})

            # Apply changes to profile
            profile_dict = profile.model_dump()

            # Deep merge the style changes
            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section]:
                            profile_dict[section][key] = value

            # Update style name
            original_name = profile_dict.get("style_name", "Style")
            profile_dict["style_name"] = f"{original_name} (what-if)"

            # Add mutation to core invariants
            profile_dict["core_invariants"] = [mutation_idea] + profile_dict.get("core_invariants", [])[:4]

            mutation_description = f"What-if: {mutation_idea}"

            return StyleProfile(**profile_dict), mutation_description

        except Exception as e:
            logger.error(f"What-if mutation failed: {e}")
            raise RuntimeError(f"What-if mutation failed: {e}") from e

    async def _mutate_crossover(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply crossover mutation using VLM - blend with a complementary art style.

        Returns:
            (mutated_profile, mutation_description)
        """
        instructions = """Analyze this style and identify a DIFFERENT art movement or style that would create an interesting hybrid.

Consider styles like:
- Art movements: Art Nouveau, Art Deco, Bauhaus, Constructivism, Impressionism, Expressionism, Surrealism, Pop Art, Minimalism, Baroque, Rococo, etc.
- Cultural styles: Ukiyo-e, Celtic, Moorish, Byzantine, Indigenous, Folk art, etc.
- Design movements: Memphis, Swiss Design, Brutalism, Psychedelic, Vaporwave, etc.
- Illustration styles: Ligne claire, Manga, Comic book, Editorial illustration, etc.

Pick a style that would create CONTRAST or TENSION with the current style, then intelligently BLEND the two.

Describe specifically which elements you're borrowing from the donor style and how they merge with the original."""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Crossover",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_inversion(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply inversion mutation - flip a key characteristic to its opposite.

        Uses VLM to identify a key characteristic and intelligently invert it.

        Returns:
            (mutated_profile, mutation_description)
        """
        instructions = """Identify ONE key characteristic in this style and INVERT it to its polar opposite.

Examples of inversions:
- "warm colors" → "cool colors"
- "soft edges" → "hard edges"
- "high contrast" → "low contrast"
- "detailed textures" → "smooth textures"
- "bright lighting" → "dark/moody lighting"
- "organic shapes" → "geometric shapes"
- "saturated palette" → "desaturated/muted palette"
- "flat composition" → "deep perspective"

Pick the MOST DEFINING characteristic of this style and flip it completely.
Make the inversion dramatic and noticeable - don't be subtle.

In your response:
- "analysis": describe the key characteristic you identified
- "mutation_applied": state the inversion (e.g., "warm → cool", "soft → hard")
- "style_changes": the actual changes to apply the inversion"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Characteristic Inversion",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_amplify(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply amplification mutation - exaggerate existing traits to extremes.

        Uses VLM to identify the most distinctive trait and push it further.

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_summary = self._summarize_profile(profile)

        amplify_prompt = f"""Analyze this visual style and identify its MOST DISTINCTIVE trait, then amplify it to an extreme.

Current style:
{profile_summary}

Examples of amplification:
- If slightly desaturated → completely monochrome
- If somewhat geometric → pure mathematical shapes only
- If soft shadows → shadows that glow and pulse
- If warm colors → molten lava heat, volcanic intensity
- If textured → extremely rough, almost 3D relief

Push the most distinctive element past realistic into stylized/surreal territory.

Output ONLY valid JSON:
{{
    "distinctive_trait": "what trait you identified",
    "amplified_version": "the extreme version",
    "style_changes": {{
        "palette": {{"color_descriptions": ["color1", "color2"], "saturation": "level"}},
        "texture": {{"surface": "new surface description"}},
        "lighting": {{"lighting_type": "new lighting"}},
        "line_and_shape": {{"line_quality": "new lines", "shape_language": "new shapes"}}
    }}
}}

Only include fields that need to change for the amplification."""

        try:
            response = await vlm_service.generate_text(
                prompt=amplify_prompt,
                system="You are a style amplifier that pushes visual characteristics to creative extremes. Output only valid JSON.",
                use_text_model=True,
            )

            # Parse response
            response = response.strip()
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            distinctive_trait = data.get("distinctive_trait", "style element")
            amplified_version = data.get("amplified_version", "extreme version")
            style_changes = data.get("style_changes", {})

            # Apply changes
            profile_dict = profile.model_dump()

            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section] and value:
                            profile_dict[section][key] = value

            # Update style name
            original_name = profile_dict.get("style_name", "Style")
            profile_dict["style_name"] = f"{original_name} (amplified)"

            # Add amplification to core invariants
            profile_dict["core_invariants"] = [amplified_version] + profile_dict.get("core_invariants", [])[:4]

            mutation_description = f"Amplify: '{distinctive_trait}' → '{amplified_version}'"

            return StyleProfile(**profile_dict), mutation_description

        except Exception as e:
            logger.error(f"Amplify mutation failed: {e}")
            raise RuntimeError(f"Amplify mutation failed: {e}") from e

    async def _mutate_diverge(
        self,
        profile: StyleProfile,
        parent_image_b64: str | None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply diverge mutation - extract-and-deviate using critique-like analysis.

        This is the inverse of the training loop:
        1. Analyze the current style's most distinctive traits
        2. Ask VLM to suggest deliberate deviations from those traits
        3. Create a new profile that intentionally breaks from the original

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_summary = self._summarize_profile(profile)

        # Step 1: Ask VLM to identify what to deviate from and how
        diverge_prompt = f"""You are a style DIVERGENCE engine. Your goal is to analyze a style and create a deliberate, artistic departure from it.

Current style to diverge FROM:
{profile_summary}

Core traits that define this style:
{', '.join(profile.core_invariants[:5]) if profile.core_invariants else 'Not specified'}

Your task: Create a NEW style that is deliberately DIFFERENT but still coherent and interesting.

Think about:
- If the original is warm, go cold (or vice versa)
- If the original is soft, go sharp (or vice versa)
- If the original is busy, go minimal (or vice versa)
- If the original is realistic, go abstract (or vice versa)
- Change the mood, era, or artistic movement entirely

Be BOLD - don't make small changes, make transformative ones that result in a completely different aesthetic while maintaining artistic quality.

Output ONLY valid JSON:
{{
    "divergence_strategy": "A 1-sentence description of how you're diverging (e.g., 'Transforming from warm organic impressionism to cold geometric minimalism')",
    "traits_abandoned": ["list 2-3 key traits from the original that you're abandoning"],
    "traits_introduced": ["list 2-3 new traits you're introducing instead"],
    "new_style": {{
        "style_name": "A new name for this divergent style",
        "core_invariants": ["3-5 NEW defining traits for the divergent style"],
        "palette": {{
            "color_descriptions": ["4-5 colors for the new style"],
            "saturation": "low/medium/high"
        }},
        "texture": {{
            "surface": "description of new surface quality"
        }},
        "lighting": {{
            "lighting_type": "description of new lighting approach",
            "shadows": "description of shadow treatment"
        }},
        "line_and_shape": {{
            "line_quality": "description of new line treatment",
            "shape_language": "description of new shapes"
        }},
        "composition": {{
            "framing": "description of new composition approach"
        }}
    }}
}}"""

        try:
            response = await vlm_service.generate_text(
                prompt=diverge_prompt,
                system="You are a creative AI that transforms visual styles into deliberate artistic departures. Output only valid JSON.",
                use_text_model=True,
            )

            # Parse response
            response = response.strip()
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            divergence_strategy = data.get("divergence_strategy", "Diverging from original style")
            traits_abandoned = data.get("traits_abandoned", [])
            traits_introduced = data.get("traits_introduced", [])
            new_style = data.get("new_style", {})

            # Build the mutated profile
            profile_dict = profile.model_dump()

            # Apply the new style characteristics
            if new_style.get("style_name"):
                profile_dict["style_name"] = new_style["style_name"]

            if new_style.get("core_invariants"):
                # Ensure core_invariants are strings
                invariants = new_style["core_invariants"]
                if isinstance(invariants, list):
                    profile_dict["core_invariants"] = [str(inv) for inv in invariants if inv][:5]

            if new_style.get("palette"):
                palette = new_style["palette"]
                if palette.get("color_descriptions"):
                    colors = palette["color_descriptions"]
                    if isinstance(colors, list):
                        profile_dict["palette"]["color_descriptions"] = [str(c) for c in colors if c][:5]
                if palette.get("saturation"):
                    profile_dict["palette"]["saturation"] = str(palette["saturation"])

            if new_style.get("texture") and new_style["texture"].get("surface"):
                profile_dict["texture"]["surface"] = str(new_style["texture"]["surface"])

            if new_style.get("lighting"):
                lighting = new_style["lighting"]
                if lighting.get("lighting_type"):
                    profile_dict["lighting"]["lighting_type"] = str(lighting["lighting_type"])
                if lighting.get("shadows"):
                    profile_dict["lighting"]["shadows"] = str(lighting["shadows"])

            if new_style.get("line_and_shape"):
                line_shape = new_style["line_and_shape"]
                if line_shape.get("line_quality"):
                    profile_dict["line_and_shape"]["line_quality"] = str(line_shape["line_quality"])
                if line_shape.get("shape_language"):
                    profile_dict["line_and_shape"]["shape_language"] = str(line_shape["shape_language"])

            if new_style.get("composition") and new_style["composition"].get("framing"):
                profile_dict["composition"]["framing"] = str(new_style["composition"]["framing"])

            # Build mutation description
            abandoned_str = ", ".join(traits_abandoned[:2]) if traits_abandoned else "original traits"
            introduced_str = ", ".join(traits_introduced[:2]) if traits_introduced else "new direction"
            mutation_description = f"Diverge: {divergence_strategy}. Abandoned: {abandoned_str}. Introduced: {introduced_str}"

            return StyleProfile(**profile_dict), mutation_description

        except Exception as e:
            logger.error(f"Diverge mutation failed: {e}")
            raise RuntimeError(f"Diverge mutation failed: {e}") from e

    async def _mutate_time_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply time_shift mutation - transport the style to a different era/decade.

        Uses VLM to analyze the style and shift it to a contrasting era.

        Returns:
            (mutated_profile, mutation_description)
        """
        instructions = """Analyze this style and TRANSPORT it to a different historical era or decade.

Pick an era that creates INTERESTING CONTRAST with the current style:
- 1920s Art Deco: geometric patterns, gold/black, luxury, sharp angles
- 1950s Mid-Century: atomic age, pastels, optimistic, clean lines
- 1960s Psychedelic: vibrant colors, flowing shapes, trippy patterns
- 1970s Earthy: browns, oranges, macramé textures, organic
- 1980s Neon: bright colors, synthwave, chrome, grid patterns
- 1990s Grunge: muted, gritty, distressed, anti-establishment
- 2000s Y2K: silver, translucent, bubbly, digital glitch
- Victorian: ornate, dark, detailed, rich textures
- Art Nouveau: flowing organic lines, natural motifs, elegant curves
- Brutalist: raw concrete, stark geometry, imposing forms
- Futurism: motion blur, dynamic angles, speed, technology

Choose an era that would CREATE THE MOST INTERESTING TRANSFORMATION.
Apply that era's visual language comprehensively to the style.

In your response:
- "analysis": identify the current era/aesthetic influences
- "mutation_applied": state which era you're shifting to and why
- "style_changes": apply the era's visual characteristics"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Time Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_medium_swap(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply medium_swap mutation - change the apparent artistic medium.

        Uses VLM to analyze current medium hints and transform to a contrasting medium.

        Returns:
            (mutated_profile, mutation_description)
        """
        instructions = """Analyze this style and TRANSFORM it to a different artistic medium.

Identify what medium the style currently evokes, then pick a CONTRASTING medium:
- Oil painting: rich colors, visible brushstrokes, layered glazes, soft blending
- Watercolor: transparency, color bleeding, wet-on-wet effects, paper texture
- Gouache: matte finish, opaque layers, flat color areas, chalky texture
- Acrylic: bright colors, sharp edges, plastic sheen, fast-drying effects
- Digital art: clean vectors, gradients, pixel-perfect, glowing effects
- Pencil/Graphite: grayscale tones, hatching, soft shading, paper grain
- Charcoal: deep blacks, smudged edges, dramatic contrast, rough texture
- Ink wash: flowing gradients, bold blacks, wet effects, Japanese sumi-e
- Pastel: soft chalky texture, blended colors, powdery, luminous
- Woodcut/Linocut: bold lines, stark contrast, carved texture, graphic
- Screen print: flat colors, halftone dots, limited palette, pop art feel
- Collage: cut paper edges, mixed textures, layered elements

Choose a medium that creates DRAMATIC CONTRAST with the current feel.
Apply ALL visual characteristics of the new medium comprehensively.

In your response:
- "analysis": identify the current apparent medium
- "mutation_applied": state the new medium and why it creates contrast
- "style_changes": apply the new medium's complete visual language"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Medium Swap",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_mood_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply mood_shift mutation - transform the emotional tone.

        Uses VLM to identify current emotional tone and shift to a contrasting mood.

        Returns:
            (mutated_profile, mutation_description)
        """
        instructions = """Analyze this style's EMOTIONAL TONE and SHIFT it to a different mood.

Identify the current mood, then transform to a CONTRASTING emotion:
- Serene/Peaceful: soft colors, gentle gradients, calm composition, muted tones
- Melancholic: desaturated, cool shadows, heavy atmosphere, downward energy
- Euphoric/Joyful: bright saturated colors, uplifting composition, light-filled
- Tense/Anxious: high contrast, sharp angles, discordant colors, unstable balance
- Mysterious: deep shadows, selective lighting, hidden elements, ambiguous forms
- Romantic: warm soft lighting, rose/gold tones, dreamy edges, intimate framing
- Aggressive/Fierce: bold reds/blacks, sharp edges, dynamic angles, high energy
- Nostalgic: muted warm tones, soft focus, vintage feel, gentle fading
- Ethereal/Dreamy: soft pastels, glowing highlights, floating elements, airy
- Foreboding/Ominous: dark palette, heavy shadows, looming forms, cold accents
- Whimsical/Playful: bright colors, rounded shapes, bouncy energy, unexpected elements
- Solemn/Reverent: muted palette, vertical emphasis, restrained composition

Pick a mood that creates DRAMATIC EMOTIONAL CONTRAST.
Apply ALL visual elements that evoke the new mood.

In your response:
- "analysis": identify the current emotional tone
- "mutation_applied": state the new mood and the emotional shift
- "style_changes": apply the visual language of the new mood"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Mood Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_scale_warp(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Warp the apparent scale and perspective relationships."""
        instructions = """WARP SCALE - alter the apparent size relationships and perspective.

Scale warp approaches:
- Macro to micro: As if viewing through a microscope
- Micro to macro: Intimate details blown up to monumental scale
- Tilt-shift miniature: Real scenes look like tiny models
- Giant scale: Everything feels massive, viewer feels small
- Intimate scale: Close, personal, immediate perspective
- Cosmic scale: Vast, astronomical sense of space
- Distorted scale: Inconsistent sizes within the same scene
- Forced perspective: Manipulated depth cues

Analyze the current sense of scale and warp it to create a different relationship between viewer and subject."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Scale Warp",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_decay(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add entropy, age, and weathering effects to the style."""
        instructions = """APPLY DECAY - add entropy, aging, and weathering to the style.

Decay approaches:
- Fresh decay: Minor wear, slight fading, early aging signs
- Weathered: Sun-bleached, rain-worn, exposed to elements
- Rusted/corroded: Metal degradation, oxidation, patina
- Organic rot: Mold, moss, biological decomposition
- Crumbling: Structural breakdown, cracks, erosion
- Dust accumulation: Layers of settled particles
- Faded glory: Once-vibrant now muted, ghostly remains
- Archaeological: Ancient, buried, rediscovered quality
- Digital decay: Glitch, corruption, data degradation

Analyze the style and apply appropriate decay that tells a story of time and entropy."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Decay",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_remix(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Shuffle and swap elements between different style sections."""
        instructions = """REMIX the style by swapping and shuffling elements between sections.

Remix approaches:
- Color-to-texture: Apply color descriptions as texture qualities
- Lighting-to-shape: Use lighting characteristics to define shape language
- Texture-to-composition: Let texture patterns influence compositional structure
- Shape-to-color: Derive color relationships from shape dynamics
- Cross-pollination: Mix multiple sections in unexpected ways
- Attribute swap: Exchange specific attributes between sections

Analyze the style sections and creatively remix them - take qualities from one area and apply them to another, creating unexpected but coherent combinations."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Remix",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_constrain(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply a strict constraint that limits the style in a specific way."""
        instructions = """Apply a CONSTRAINT that limits or restricts the style in a specific way.

Constraint approaches:
- Monochromatic: Limit to single hue with value variations only
- Duotone: Restrict to exactly two colors
- Silhouette only: Remove all internal detail, pure shapes
- No curves: Only straight lines and angular shapes
- No straight lines: Only organic, curved forms
- Single light source: Simplify to one directional light
- Flat color: No gradients, only solid color areas
- Limited palette: Maximum 3-4 colors total
- Geometric only: All forms reduced to basic geometry

Analyze the style and apply a meaningful constraint that creates focus through limitation."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Constrain",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_culture_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply culture_shift mutation - apply aesthetics from a different culture.

        Uses VLM to identify cultural influences and shift to a contrasting aesthetic.

        Returns:
            (mutated_profile, mutation_description)
        """
        instructions = """Analyze this style's CULTURAL INFLUENCES and SHIFT it to a different cultural aesthetic.

Identify any current cultural influences, then transform to a CONTRASTING culture:
- Japanese (Wabi-Sabi): asymmetry, natural imperfection, muted earth tones, negative space
- Japanese (Ukiyo-e): flat color areas, bold outlines, flowing patterns, ukiyo-e compositions
- Chinese Classical: red/gold/black palette, intricate patterns, symbolic motifs, balance
- Art Deco: geometric patterns, metallic accents, symmetry, bold contrasts
- Nordic/Scandinavian: minimalist, muted pastels, clean lines, natural materials
- African: bold geometric patterns, earth tones, rhythmic repetition, carved textures
- Middle Eastern (Islamic): intricate geometric tessellations, arabesques, jewel tones
- Indian (Mughal): ornate decoration, rich jewel colors, floral motifs, gold details
- Mexican (Folk Art): vibrant saturated colors, decorative patterns, skull motifs
- Celtic: interlaced knotwork, spirals, earth tones, organic symmetry
- Art Nouveau: flowing organic lines, natural motifs, muted elegance, feminine curves
- Russian Constructivist: bold red/black, diagonal compositions, geometric shapes
- Aboriginal: dot patterns, earth colors, dreamtime imagery, symbolic landscapes

Choose a culture that creates DRAMATIC CONTRAST with current influences.
Apply the FULL visual language of the new culture comprehensively.

In your response:
- "analysis": identify current cultural aesthetic influences
- "mutation_applied": state the new cultural aesthetic and why it creates contrast
- "style_changes": apply the complete visual language of the new culture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Culture Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_chaos(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply chaos mutation - multiple simultaneous mutations across dimensions.

        Uses VLM to identify 3-5 dimensions and mutate each in different directions.

        Returns:
            (mutated_profile, mutation_description)
        """
        instructions = """Apply CHAOS to this style by mutating 3-5 DIFFERENT dimensions simultaneously.

Each mutation should:
1. Target a DIFFERENT aspect of the style (don't repeat dimensions)
2. Push in an UNEXPECTED direction (not the obvious next step)
3. Be BOLD and noticeable

Dimensions to consider:
- Palette: saturation, temperature, contrast, hue shifts
- Texture: grain, roughness, pattern overlays
- Lighting: direction, intensity, color, atmosphere
- Line/Shape: weight, quality, geometry vs organic
- Composition: framing, depth, focus, balance

The goal is controlled chaos - multiple simultaneous changes that create interesting tension.
Don't just make random changes - make PURPOSEFUL chaos that still feels cohesive.

In your response:
- "analysis": describe the current style's key characteristics
- "mutation_applied": list ALL the chaos mutations you're applying (3-5 of them)
- "style_changes": combine all the changes into the style_changes object"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Chaos Multi-Mutation",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_refine(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply refine mutation - reduce extremes toward balance.
        The opposite of amplify.
        """
        instructions = """REFINE - identify the MOST EXTREME trait and moderate it toward balance.

Examples of refinement:
- If hypersaturated → bring saturation to medium-high
- If extremely geometric → add some organic softness
- If pitch black shadows → lighten to dramatic but visible
- If blazing hot colors → warm but not overwhelming
- If maximum noise/grain → reduce to subtle texture

Find the element that is pushed furthest from center and pull it back toward moderation while keeping the style interesting."""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Refine",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    def _apply_preset_mutation(
        self,
        profile: StyleProfile,
        preset_name: str,
        preset_changes: dict,
        category: str,
        suffix: str,
    ) -> tuple[StyleProfile, str]:
        """Helper to apply preset-based mutations consistently."""
        profile_dict = profile.model_dump()

        # Apply changes
        for section, changes in preset_changes.items():
            if section == "mood":
                # Store mood in core_invariants
                continue
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section]:
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        profile_dict["style_name"] = f"{original_name} ({suffix})"

        # Add to core invariants
        mood = preset_changes.get("mood", "")
        if mood:
            profile_dict["core_invariants"] = [mood] + profile_dict.get("core_invariants", [])[:4]
        else:
            profile_dict["core_invariants"] = [preset_name] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"{category}: {preset_name}"
        return StyleProfile(**profile_dict), mutation_description

    # === SPATIAL MUTATIONS ===

    async def _mutate_topology_fold(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply non-Euclidean or impossible geometry distortions."""
        instructions = """Apply TOPOLOGY FOLD - introduce non-Euclidean or impossible geometry.

Topology fold approaches:
- Möbius surfaces: Surfaces that twist and connect impossibly
- Klein bottle logic: Inside becomes outside, boundaries blur
- Escher recursion: Impossible stairs, endless loops
- Hyperbolic space: More space than should fit, curved infinity
- Folded dimensions: Space that overlaps itself
- Portal geometry: Discontinuous space, windows to elsewhere
- Penrose triangles: Locally correct, globally impossible
- Non-orientable surfaces: Flip between inside/outside

Analyze the spatial logic and fold it in impossible ways that create visual intrigue."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Topology Fold",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_silhouette_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Modify contour/silhouette while keeping internal style traits."""
        instructions = """SHIFT THE SILHOUETTE - transform the outer contours while preserving internal style.

Silhouette shift approaches:
- Soften edges: Sharp contours become flowing, organic
- Harden edges: Organic shapes become crisp, geometric
- Fragment: Break continuous silhouettes into pieces
- Merge: Combine separate silhouettes into unified forms
- Echo: Add offset duplicate contours
- Invert figure/ground: Swap positive and negative space
- Exaggerate: Push silhouette characteristics further
- Simplify: Reduce to essential outline

Analyze the current silhouette language and shift it while maintaining the internal style qualities."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Silhouette Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_perspective_drift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply surreal camera angles and perspective distortions."""
        instructions = """Apply PERSPECTIVE DRIFT - shift to surreal or unusual viewpoints.

Perspective drift approaches:
- Bird's eye: Looking down from above
- Worm's eye: Looking up from below
- Dutch angle: Tilted, unsettling viewpoint
- Extreme close-up: Uncomfortably intimate perspective
- Infinite distance: Far away, detached, small in vast space
- Multiple simultaneous viewpoints: Cubist fragmentation
- First person: Viewer is inside the scene
- Floating/zero gravity: No fixed up or down

Analyze the current viewpoint and drift it to create a different psychological relationship with the viewer."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Perspective Drift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_axis_swap(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Rotate conceptual axes (vertical↔horizontal, center↔edge)."""
        instructions = """Apply AXIS SWAP - rotate or exchange the conceptual axes of the composition.

Axis swap approaches:
- Vertical to horizontal: What was tall becomes wide
- Horizontal to vertical: Wide becomes tall
- Center to edge: Move focal emphasis to periphery
- Edge to center: Pull peripheral elements to focus
- Diagonal dominance: Rotate to 45-degree emphasis
- Radial to linear: Circular becomes directional
- Linear to radial: Lines become radiating spokes
- Mirror axis: Flip the orientation entirely

Analyze the current axis orientation and swap it to create a different compositional dynamic."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Axis Swap",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === PHYSICS MUTATIONS ===

    async def _mutate_physics_bend(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Alter physical laws (gravity, light behavior, etc.)."""
        instructions = """BEND PHYSICS - alter the apparent physical laws governing the visual world.

Physics bend approaches:
- Zero gravity: Objects float, hair drifts, fabric billows
- Heavy gravity: Everything compressed, pressed down
- Selective gravity: Some things fall, others float
- Light bending: Impossible shadows, curved light paths
- Time dilation: Motion blur in still objects, frozen motion
- Fluid dynamics: Air becomes viscous, solid becomes liquid
- Magnetic fields: Objects attracted or repelled visually
- Quantum superposition: Things exist in multiple states

Analyze the implied physics and bend them to create surreal or impossible physical behavior."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Physics Bend",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_chromatic_gravity(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Make colors cluster or repel in new ways."""
        instructions = """Apply CHROMATIC GRAVITY - make colors behave as if they have mass and attract or repel.

Chromatic gravity approaches:
- Color pooling: Colors collect at the bottom like liquid
- Color floating: Light colors rise, dark colors sink
- Magnetic colors: Complementary colors attract each other
- Color repulsion: Similar hues push apart
- Bleeding: Colors leak into adjacent areas
- Color wells: Dark areas pull color toward them
- Chromatic orbits: Colors circle around focal points
- Static cling: Colors stick to edges

Analyze the color distribution and apply gravitational or force-based behavior to create dynamic color movement."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Chromatic Gravity",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_material_transmute(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Change surface properties (glass→fur, metal→cloth)."""
        instructions = """TRANSMUTE MATERIALS - transform surface properties into completely different materials.

Material transmute approaches:
- Hard to soft: Metal becomes cloth, stone becomes flesh
- Soft to hard: Fabric becomes metal, skin becomes porcelain
- Opaque to transparent: Solid becomes glass or crystal
- Transparent to opaque: Glass becomes stone
- Organic to synthetic: Wood becomes plastic, skin becomes rubber
- Synthetic to organic: Metal becomes bone, plastic becomes chitin
- Liquid to solid: Water frozen, mercury hardened
- Solid to liquid: Metal melting, stone liquefying

Analyze the current materials and transmute them to create surreal material contradictions."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Material Transmute",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_temporal_exposure(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Alter 'shutter speed' - long exposure, freeze frames, ghosts."""
        instructions = """Apply TEMPORAL EXPOSURE - alter the implied shutter speed and time capture.

Temporal exposure approaches:
- Long exposure: Motion trails, light streaks, ghost images
- Freeze frame: Hyper-sharp frozen moment, suspended action
- Multiple exposure: Same subject in different positions overlaid
- Time lapse: Compressed time, day-to-night in single frame
- Bullet time: Matrix-style frozen moment with implied motion
- Motion blur: Selective blur suggesting movement
- Temporal echo: Fading afterimages trailing motion
- Stroboscopic: Discrete repeated positions

Analyze the implied motion and time, then alter the temporal exposure to create different time relationships."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Temporal Exposure",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === PATTERN MUTATIONS ===

    async def _mutate_motif_splice(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Inject a foreign recurring motif (eyes, keys, spirals, etc.)."""
        instructions = """SPLICE A MOTIF - inject a recurring visual element throughout the style.

Motif splice approaches:
- Eyes: Watching eyes appearing in unexpected places
- Keys/locks: Symbols of access and secrets
- Spirals: Hypnotic recurring spiral forms
- Hands: Reaching, grasping, pointing hands
- Geometric symbols: Triangles, circles, sacred geometry
- Natural elements: Leaves, feathers, shells, bones
- Mechanical parts: Gears, cogs, pipes, wires
- Celestial: Stars, moons, suns, cosmic symbols
- Text/glyphs: Letters, runes, mysterious writing

Analyze the style and inject an appropriate recurring motif that adds symbolic or visual intrigue."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Motif Splice",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_rhythm_overlay(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply tempo-based visual patterns (staccato, legato, syncopated)."""
        instructions = """OVERLAY RHYTHM - apply musical tempo and beat patterns visually.

Rhythm overlay approaches:
- Staccato: Sharp, disconnected, punchy visual beats
- Legato: Smooth, connected, flowing transitions
- Syncopated: Off-beat accents, unexpected emphasis
- Waltz (3/4): Triple groupings, graceful repetition
- March (4/4): Strong regular beats, military precision
- Jazz swing: Loose, improvisational, irregular
- Crescendo: Building intensity, growing elements
- Diminuendo: Fading away, shrinking presence

Analyze the visual rhythm and overlay a musical tempo pattern that creates cadence and movement."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Rhythm Overlay",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_harmonic_balance(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply musical composition logic (major/minor, dissonance/harmony)."""
        instructions = """Apply HARMONIC BALANCE - use musical harmony/dissonance concepts visually.

Harmonic balance approaches:
- Major key: Bright, uplifting, resolved, harmonious
- Minor key: Melancholic, tense, emotionally complex
- Dissonance: Clashing elements, visual tension, unresolved
- Consonance: Pleasing combinations, visual resolution
- Chord progressions: Elements that lead to each other
- Counterpoint: Independent elements in conversation
- Resolution: Tension releasing to stability
- Suspension: Held tension, delayed resolution

Analyze the visual relationships and apply musical harmony concepts to create emotional resonance."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Harmonic Balance",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_symmetry_break(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Break symmetry or force symmetry onto chaos."""
        instructions = """Apply SYMMETRY BREAK - either break existing symmetry or impose order on chaos.

Symmetry break approaches:
- Break bilateral: Disrupt left-right mirror symmetry
- Break radial: Disrupt circular/rotational symmetry
- Impose bilateral: Force mirror symmetry onto asymmetric elements
- Impose radial: Create circular symmetry from chaos
- Partial symmetry: Symmetry in some areas, chaos in others
- Near-symmetry: Almost but not quite balanced
- Rotational shift: Symmetry at unusual angles
- Translational: Repeat with offset, breaking expected patterns

Analyze the current symmetry state and either break it for dynamic tension or impose it for unexpected order."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Symmetry Break",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === DENSITY MUTATIONS ===

    async def _mutate_density_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Vary visual information density (sparse↔dense)."""
        instructions = """Apply DENSITY SHIFT - change the amount of visual information per area.

Density shift approaches:
- Sparse to dense: Add detail, complexity, visual noise
- Dense to sparse: Remove detail, simplify, create emptiness
- Gradient density: Vary density across the composition
- Cluster density: Create pockets of high/low density
- Edge density: Dense edges, sparse centers (or vice versa)
- Focal density: High density at focus, sparse elsewhere
- Uniform shift: Increase or decrease density everywhere equally
- Contrast density: Extreme differences between dense and sparse

Analyze the current visual density and shift it to create different levels of visual complexity."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Density Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_dimensional_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Flatten or deepen dimensionality (2D↔2.5D↔3D)."""
        instructions = """Apply DIMENSIONAL SHIFT - change the perceived dimensionality.

Dimensional shift approaches:
- Flatten to 2D: Remove depth cues, everything on one plane
- Deepen to 3D: Add perspective, depth, volumetric quality
- 2.5D isometric: Angled flat view with implied depth
- Paper cutout: Layered flat planes with depth between
- Relief sculpture: Shallow 3D emerging from flat surface
- Holographic: Implied depth through interference patterns
- Stereoscopic: Exaggerated depth separation
- Dimensional collapse: 3D forms flattening mid-transition

Analyze the current dimensionality and shift it to create different spatial perception."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Dimensional Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_micro_macro_swap(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Switch scales internally (tiny textures→big shapes)."""
        instructions = """Apply MICRO/MACRO SWAP - exchange scales within the composition.

Micro/macro swap approaches:
- Texture to structure: Small texture patterns become large shapes
- Structure to texture: Large forms become tiny repeated patterns
- Cell to organism: Microscopic becomes macroscopic
- Universe to atom: Cosmic becomes subatomic
- Detail explosion: Tiny details enlarged to dominant features
- Pattern compression: Large patterns shrunk to texture
- Fractal inversion: Swap which scale level is detailed
- Scale contradiction: Mix incompatible scales together

Analyze the current scale relationships and swap micro and macro elements to create new visual hierarchies."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Micro/Macro Swap",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_essence_strip(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Remove secondary features to reveal core essence (more drastic than refine)."""
        profile_summary = self._summarize_profile(profile)

        strip_prompt = f"""Analyze this visual style and strip it to its absolute ESSENCE.

Current style:
{profile_summary}

Remove ALL secondary details. Keep ONLY:
1. The single most defining color relationship
2. The essential line quality (one word)
3. The core lighting approach (simplified)
4. The fundamental compositional structure

Everything else should be reduced to "minimal" or "absent".

Output ONLY valid JSON with stripped-down values:
{{
    "essence_description": "3-5 word description of pure essence",
    "style_changes": {{
        "palette": {{"color_descriptions": ["1-2 essential colors only"], "saturation": "level"}},
        "texture": {{"surface": "minimal or single texture word", "noise_level": "low"}},
        "lighting": {{"lighting_type": "simplified essential lighting"}},
        "line_and_shape": {{"line_quality": "one essential quality", "shape_language": "one essential shape type"}}
    }}
}}"""

        try:
            response = await vlm_service.generate_text(
                prompt=strip_prompt,
                system="You are a style minimalist. Strip styles to their pure essence. Output only valid JSON.",
                use_text_model=True,
            )

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found")

            essence_desc = data.get("essence_description", "pure essence")
            style_changes = data.get("style_changes", {})

            profile_dict = profile.model_dump()
            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section] and value:
                            profile_dict[section][key] = value

            profile_dict["style_name"] = f"{profile_dict.get('style_name', 'Style')} (essence)"
            profile_dict["core_invariants"] = [essence_desc] + profile_dict.get("core_invariants", [])[:2]

            return StyleProfile(**profile_dict), f"Essence Strip: {essence_desc}"

        except Exception as e:
            logger.error(f"Essence strip failed: {e}")
            raise RuntimeError(f"Essence strip failed: {e}") from e

    # === NARRATIVE MUTATIONS ===

    async def _mutate_narrative_resonance(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add implied story fragments using VLM analysis."""
        instructions = """Analyze this style and identify a NARRATIVE that resonates with its visual language.

Layer in visual elements that imply a STORY without being literal:
- Lost Civilization: crumbling edges, ancient symbols, patina of time, forgotten grandeur
- Sacred Ritual: ceremonial patterns, altar-like composition, reverent lighting, symbolic objects
- Epic Journey: horizon lines, path-like elements, worn textures, sense of distance
- Transformation/Metamorphosis: transitional forms, emergence, cocoon textures, becoming
- Apocalypse/Renewal: broken fragments, new growth, contrast of decay and rebirth
- Dream/Memory: soft focus, fragmented forms, nostalgic colors, floating elements
- Prophecy/Vision: radiant light, symbolic imagery, otherworldly atmosphere
- Battle/Conflict: dynamic tension, opposing forces, scarred textures, dramatic contrast

Choose a narrative that FITS the style's existing mood and enhance it.
Add visual elements that IMPLY the story rather than illustrate it literally.

In your response:
- "analysis": identify what story the style already hints at
- "mutation_applied": state the narrative resonance you're adding
- "style_changes": add visual elements that enhance the narrative"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Narrative Resonance",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_archetype_mask(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Map onto mythological/Jungian archetypes using VLM analysis."""
        instructions = """Analyze this style and overlay a JUNGIAN ARCHETYPE onto it.

Map the style onto a universal archetype through visual transformation:
- The Hero: upward movement, golden light, strength in forms, triumphant energy
- The Shadow: dark depths, hidden corners, ominous presence, secrets in darkness
- The Anima/Animus: flowing forms, duality, sensual curves, mysterious beauty
- The Oracle/Sage: ancient textures, wise restraint, deep seeing, cosmic awareness
- The Trickster: asymmetry, unexpected elements, playful chaos, hidden jokes
- The Mother: nurturing curves, warm embrace, protective enclosure, organic forms
- The Child: innocence in palette, wonder, simplicity, fresh perspective
- The Ruler: symmetry, grandeur, authority, structured power
- The Outlaw/Rebel: broken rules, raw edges, defiant energy, disruption
- The Magician: transformation, mystery, ethereal light, impossible forms

Choose an archetype that creates INTERESTING TENSION with the current style.
Overlay the archetype's visual language onto the existing aesthetic.

In your response:
- "analysis": identify any existing archetypal resonances
- "mutation_applied": state the archetype you're overlaying
- "style_changes": apply the archetype's visual language"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Archetype Mask",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_anomaly_inject(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add a single deliberate anomaly that violates the style rules."""
        profile_summary = self._summarize_profile(profile)

        anomaly_prompt = f"""Analyze this visual style and find its MOST RIGID RULE.
Then create ONE controlled violation of that rule to create visual tension.

Current style:
{profile_summary}

Examples:
- If style is "always warm colors" → inject one cold blue element
- If style is "soft edges" → add one sharp angular shape
- If style is "symmetrical" → introduce one asymmetric element
- If style is "muted tones" → add one saturated accent

The anomaly should be NOTICEABLE but not overwhelming - tension, not chaos.

Output ONLY valid JSON:
{{
    "rigid_rule": "the rule being violated",
    "anomaly": "the controlled violation",
    "style_changes": {{
        "texture": {{"special_effects": ["anomaly description"]}},
        "composition": {{"framing": "composition note if relevant"}}
    }}
}}"""

        try:
            response = await vlm_service.generate_text(
                prompt=anomaly_prompt,
                system="You are a style disruptor. Find the most rigid rule and create one deliberate violation. Output only valid JSON.",
                use_text_model=True,
            )

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found")

            rigid_rule = data.get("rigid_rule", "style rule")
            anomaly = data.get("anomaly", "controlled violation")
            style_changes = data.get("style_changes", {})

            profile_dict = profile.model_dump()
            for section, changes in style_changes.items():
                if section in profile_dict and isinstance(changes, dict):
                    for key, value in changes.items():
                        if key in profile_dict[section] and value:
                            if key == "special_effects":
                                current = profile_dict[section].get(key, [])
                                profile_dict[section][key] = value + current[:2]
                            else:
                                profile_dict[section][key] = value

            profile_dict["style_name"] = f"{profile_dict.get('style_name', 'Style')} (anomaly)"
            profile_dict["core_invariants"] = [f"intentional anomaly: {anomaly}"] + profile_dict.get("core_invariants", [])[:4]

            return StyleProfile(**profile_dict), f"Anomaly Inject: violates '{rigid_rule}' with {anomaly}"

        except Exception as e:
            logger.error(f"Anomaly inject failed: {e}")
            raise RuntimeError(f"Anomaly inject failed: {e}") from e

    async def _mutate_spectral_echo(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add faint ghost-layers as texture using VLM analysis."""
        instructions = """Analyze this style and add SPECTRAL ECHO effects - ghost-layers of phantom forms.

Layer in translucent echoes that suggest previous states or parallel versions:
- Ghost duplicates: faint transparent copies offset from main forms
- Temporal blurring: motion-like trails suggesting movement through time
- Memory layers: fragments of previous states bleeding through
- Parallel shadows: multiple overlapping shadow versions
- Afterimage effects: complementary color ghosts
- Phasing elements: parts appearing to shift between planes
- Echo contours: repeated edge lines at varying opacities

Consider what SPECIFIC ghost effects fit this style:
- For geometric styles: clean offset duplicates, precise echoes
- For organic styles: flowing trails, blurring memories
- For dramatic styles: bold afterimages, high-contrast ghosts
- For subtle styles: barely visible whispers, faint layering

Add effects that feel NATURAL to the style while creating ethereal depth.

In your response:
- "analysis": describe what kinds of spectral effects would suit this style
- "mutation_applied": describe the ghost-layering you're adding
- "style_changes": apply the spectral echo effects"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Spectral Echo",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === ENVIRONMENT MUTATIONS ===

    async def _mutate_climate_morph(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply environmental system changes (dust storm, fog, cosmic vacuum)."""
        instructions = """Apply CLIMATE MORPH - transform the environmental atmosphere.

Climate morph approaches:
- Dust storm: Particles in air, reduced visibility, warm tones
- Dense fog: Soft edges, limited depth, mysterious
- Cosmic vacuum: No atmosphere, stark contrasts, alien
- Underwater: Light filtering, caustics, blue-green tints
- Volcanic ash: Dark particles, orange glow, apocalyptic
- Arctic freeze: Ice crystals, blue shadows, pristine
- Tropical humidity: Haze, lush saturation, diffused light
- Desert heat: Shimmering air, harsh light, washed colors

Analyze the current atmosphere and apply a climate transformation that changes the environmental feel."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Climate Morph",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_biome_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Reframe as a new ecosystem (desert, coral reef, fungal forest)."""
        instructions = """Apply BIOME SHIFT - transform the environmental ecosystem context.

Biome shift approaches:
- Desert: Arid, sand colors, sparse life, harsh sun
- Coral reef: Underwater, vibrant colors, organic complexity
- Fungal forest: Bioluminescence, spores, alien growth
- Arctic tundra: White expanses, minimal color, survival
- Rainforest: Dense, layered, green saturation, humidity
- Deep ocean: Pressure, darkness, bioluminescent accents
- Volcanic: Molten, destruction and creation, extreme contrast
- Alien world: Non-Earth biome, impossible life, strange physics

Analyze the style and shift it to exist within a different ecosystem context."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Biome Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === TECHNICAL MUTATIONS ===

    async def _mutate_algorithmic_wrinkle(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Introduce deterministic computational artifacts (CRT, JPEG, halftone)."""
        instructions = """Apply ALGORITHMIC WRINKLE - add computational/technical artifacts.

Algorithmic wrinkle approaches:
- CRT scanlines: Horizontal lines, phosphor glow, curvature
- JPEG compression: Block artifacts, color banding
- Halftone dots: Print-style dot patterns, CMYK separation
- VHS tracking: Horizontal distortion, color bleeding
- Glitch: Data corruption, pixel displacement, color channel separation
- Dithering: Stippled patterns from limited color palette
- Moiré patterns: Interference patterns from overlapping grids
- Digital noise: Random pixel artifacts, sensor noise

Analyze the style and add appropriate computational artifacts that suggest a specific technical process."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Algorithmic Wrinkle",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_symbolic_reduction(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Turn features into metaphoric/symbolic shapes."""
        instructions = """Apply SYMBOLIC REDUCTION - reduce elements to symbolic/metaphoric representations.

Symbolic reduction approaches:
- Iconography: Elements become icons, logos, simplified symbols
- Hieroglyphic: Picture-writing, symbolic pictograms
- Alchemical: Mystical symbols, transformation signs
- Mathematical: Geometric proofs, equations as visuals
- Musical notation: Visual rhythm, score-like elements
- Road signs: Universal symbolic language
- Emoji/emoticon: Extreme simplification to emotional symbols
- Heraldic: Shields, crests, formal symbolic design

Analyze the style and reduce visual elements to their symbolic essence, creating meaning through simplified representation."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Symbolic Reduction",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # ============================================================
    # NEW MUTATION METHODS (75 new strategies)
    # ============================================================

    # === CHROMATIC MUTATIONS ===
    async def _mutate_chroma_band_shift(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Shift colors only within specific hue band."""
        instructions = """Identify the DOMINANT HUE BAND in this style and shift it in a specific direction.

Hue bands to consider:
- Reds/Oranges: warm end of spectrum, passionate, energetic
- Yellows/Golds: warm brightness, optimism, warmth
- Greens: natural, growth, tranquility
- Blues/Cyans: cool, calm, depth, melancholy
- Purples/Magentas: mysterious, royal, creative

Shift directions:
- Rotate hue clockwise (red→orange→yellow→green...)
- Rotate hue counter-clockwise (red→magenta→purple→blue...)
- Push toward warmth (add yellow/orange undertones)
- Push toward coolness (add blue/cyan undertones)

Pick ONE dominant hue band and shift it noticeably in ONE direction.
Keep other hues relatively stable to maintain contrast.

In your response:
- "analysis": identify the dominant hue band
- "mutation_applied": describe the hue shift direction
- "style_changes": apply the hue shift to palette"""
        return await self._vlm_mutate(profile, "Chroma Band Shift", instructions, image_b64, session_id)

    async def _mutate_chromatic_noise(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Add color-channel-separated noise like film grain."""
        instructions = """Add CHROMATIC NOISE to this style - color-separated grain effects.

Types of chromatic noise:
- Film grain: organic, random, varies by luminosity, warm in shadows
- Digital noise: blocky, RGB-separated, harsh in darks
- Color fringing: chromatic aberration on edges, RGB separation
- Dithering: patterned noise for smooth gradients
- Scanner artifacts: banding, streaks, channel shifts
- VHS distortion: bleeding colors, horizontal artifacts

Consider what noise type FITS the style:
- Clean digital art → subtle grain adds analog warmth
- Painterly style → organic film grain enhances texture
- Retro style → VHS/scanner artifacts fit the era
- High-contrast → digital noise adds grit

Add noise that ENHANCES rather than overwhelms.

In your response:
- "analysis": describe the current texture quality
- "mutation_applied": describe the noise type you're adding
- "style_changes": apply chromatic noise to texture"""
        return await self._vlm_mutate(profile, "Chromatic Noise", instructions, image_b64, session_id)

    async def _mutate_chromatic_temperature_split(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Split warm highlights and cool shadows (or vice versa)."""
        instructions = """Create a CHROMATIC TEMPERATURE SPLIT - different color temperatures for lights and shadows.

Classic splits:
- Warm highlights / Cool shadows: golden lights, blue shadows (sunset feel)
- Cool highlights / Warm shadows: blue-white lights, warm amber shadows
- Complementary split: orange highlights / cyan shadows (cinematic)
- Analogous warm: yellow highlights / orange-red shadows
- Analogous cool: cyan highlights / blue-purple shadows

This creates DEPTH through color temperature contrast.
The effect should be cohesive, not jarring.

Analyze current temperature balance and CREATE A SPLIT.
Push highlights and shadows to different ends of the temperature spectrum.

In your response:
- "analysis": describe current temperature balance
- "mutation_applied": describe the temperature split you're creating
- "style_changes": apply temperature split to lighting/palette"""
        return await self._vlm_mutate(profile, "Chromatic Temperature Split", instructions, image_b64, session_id)

    async def _mutate_chromatic_fuse(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Merge several hues into one unified mega-hue."""
        instructions = """FUSE multiple hues in this style into ONE unified mega-hue.

Analyze the palette and identify 2-4 hues, then MERGE them:
- If style has reds and oranges → fuse into a unified coral/salmon
- If style has blues and greens → fuse into unified teal/aqua
- If style has purples and pinks → fuse into unified magenta
- If style has yellows and greens → fuse into unified chartreuse

The goal is PALETTE SIMPLIFICATION through hue unification.
The resulting color should feel like a natural blend, not a compromise.

Keep the overall palette balance but reduce color complexity.
This creates a more COHESIVE, UNIFIED color identity.

In your response:
- "analysis": identify the distinct hues present
- "mutation_applied": describe which hues you're fusing and into what
- "style_changes": apply the unified palette"""
        return await self._vlm_mutate(profile, "Chromatic Fuse", instructions, image_b64, session_id)

    async def _mutate_chromatic_split(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Separate one hue into sub-hues for palette complexity."""
        instructions = """SPLIT a dominant hue into multiple sub-hues for palette complexity.

Find the most dominant single hue and SPLIT it:
- Blue → separate into cyan, azure, navy, ultramarine
- Red → separate into crimson, scarlet, coral, burgundy
- Green → separate into emerald, lime, forest, sage
- Yellow → separate into gold, lemon, amber, cream
- Purple → separate into violet, lavender, plum, magenta

This creates PALETTE RICHNESS from simplicity.
The sub-hues should all clearly relate to the parent hue.

Use the split to add NUANCE:
- Different sub-hues for shadows vs highlights
- Different sub-hues for foreground vs background
- Gradients between sub-hues

In your response:
- "analysis": identify the dominant hue to split
- "mutation_applied": describe the sub-hues you're creating
- "style_changes": apply the split palette"""
        return await self._vlm_mutate(profile, "Chromatic Split", instructions, image_b64, session_id)

    # === LIGHTING/SHADOW MUTATIONS ===
    async def _mutate_ambient_occlusion_variance(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Alter ambient occlusion softness/darkness."""
        instructions = """Modify the AMBIENT OCCLUSION in this style - how shadows gather in crevices and corners.

AO variations:
- Soft/diffuse: gentle shadow gradients, smooth transitions
- Hard/crisp: sharp shadow edges in corners, high contrast
- Deep/dark: intensified corner shadows, dramatic depth
- Subtle/faint: barely visible ambient shadows, flat feel
- Colored AO: shadows tinted (blue, purple, warm brown)
- Inverted AO: light gathering in corners instead of shadow

Consider the current lighting and ADD or MODIFY ambient occlusion appropriately.
This affects the sense of depth and form.

In your response:
- "analysis": describe current shadow behavior
- "mutation_applied": describe the AO change
- "style_changes": apply to lighting"""
        return await self._vlm_mutate(profile, "Ambient Occlusion Variance", instructions, image_b64, session_id)

    async def _mutate_specular_flip(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Swap matte/glossy behavior."""
        instructions = """FLIP the specular/reflectivity behavior in this style.

If surfaces are currently MATTE → make them GLOSSY:
- Add sharp highlights, reflective sheen, wet look
- Increase specularity, add reflections

If surfaces are currently GLOSSY → make them MATTE:
- Remove shine, add powder/chalk texture
- Diffuse reflections, soft absorption

Variations:
- Full flip: complete reversal of all surfaces
- Partial flip: flip only key elements
- Selective flip: make matte elements shiny OR vice versa

Make the change DRAMATIC and noticeable.

In your response:
- "analysis": describe current surface reflectivity
- "mutation_applied": describe the specular flip
- "style_changes": apply to texture"""
        return await self._vlm_mutate(profile, "Specular Flip", instructions, image_b64, session_id)

    async def _mutate_bloom_variance(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Adjust bloom amount/radius/aura."""
        instructions = """Modify the BLOOM effect in this style - the glow around bright areas.

Bloom adjustments:
- Increase bloom: stronger glow, larger radius, dreamier feel
- Decrease bloom: sharper highlights, more defined edges
- Add colored bloom: tinted glow (warm gold, cool blue, pink)
- Expand radius: wide soft auras around lights
- Intensify core: bright centers with falloff
- Add anamorphic: horizontal streak bloom (cinematic)

Consider what bloom level FITS the style:
- Romantic/dreamy → heavy soft bloom
- Dramatic/intense → selective bright bloom
- Clean/modern → minimal or no bloom
- Retro/nostalgic → warm diffused bloom

In your response:
- "analysis": describe current bloom/glow behavior
- "mutation_applied": describe the bloom change
- "style_changes": apply to lighting"""
        return await self._vlm_mutate(profile, "Bloom Variance", instructions, image_b64, session_id)

    async def _mutate_desync_lighting_channels(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Independently randomize lighting intensity/color/direction."""
        instructions = """DESYNC the lighting channels - make different light properties behave independently.

Desync options:
- Color/intensity split: warm light but cool shadows
- Direction mismatch: shadows don't match light direction
- Multiple sources: conflicting light directions
- Channel separation: RGB light sources from different angles
- Temporal offset: light and shadow seem from different moments
- Logical break: physically impossible but aesthetically interesting

This creates SURREAL or STYLIZED lighting that breaks physics.
The effect should feel INTENTIONAL, not broken.

In your response:
- "analysis": describe current lighting coherence
- "mutation_applied": describe the desync effect
- "style_changes": apply to lighting"""
        return await self._vlm_mutate(profile, "Desync Lighting", instructions, image_b64, session_id)

    async def _mutate_highlight_shift(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Modify highlight behavior."""
        instructions = """SHIFT how highlights behave in this style.

Highlight modifications:
- Harden: sharp specular points, crisp reflections
- Soften: diffuse glows, gentle bright areas
- Expand: larger highlight areas, more coverage
- Concentrate: tight, focused highlight spots
- Color shift: tint highlights (warm, cool, colored)
- Add secondary: create rim lights, edge highlights
- Invert: dark highlights, light shadows (stylized)

Consider what highlight style ENHANCES the aesthetic.

In your response:
- "analysis": describe current highlight behavior
- "mutation_applied": describe the highlight shift
- "style_changes": apply to lighting"""
        return await self._vlm_mutate(profile, "Highlight Shift", instructions, image_b64, session_id)

    async def _mutate_shadow_recode(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Rewrite shadow behavior/color."""
        instructions = """RECODE how shadows behave in this style.

Shadow modifications:
- Color shadows: purple, blue, warm brown, complementary
- Harden edges: crisp shadow boundaries
- Soften edges: diffuse, gradient shadows
- Deepen: more intense, darker shadows
- Lighten: lifted shadows, more visible detail
- Add bounce light: warm reflected light in shadows
- Stylize: flat shadow shapes, graphic treatment

Shadows dramatically affect mood - make intentional choices.

In your response:
- "analysis": describe current shadow behavior
- "mutation_applied": describe the shadow recode
- "style_changes": apply to lighting"""
        return await self._vlm_mutate(profile, "Shadow Recode", instructions, image_b64, session_id)

    async def _mutate_lighting_angle_shift(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Move light source direction."""
        instructions = """SHIFT the apparent lighting angle/direction in this style.

Direction changes:
- Top-down: overhead light, short shadows below
- Side-lit: dramatic raking light, long shadows
- Under-lit: eerie uplighting, inverted shadows
- Back-lit: rim lighting, silhouettes, halo effects
- Front-lit: flat, even, minimal shadows
- Diagonal: dynamic 45-degree lighting
- Multiple: conflicting light directions

The lighting angle dramatically affects DRAMA and MOOD.

In your response:
- "analysis": describe current light direction
- "mutation_applied": describe the angle shift
- "style_changes": apply to lighting"""
        return await self._vlm_mutate(profile, "Lighting Angle Shift", instructions, image_b64, session_id)

    async def _mutate_highlight_bloom_colorize(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Change highlight bloom color."""
        instructions = """COLORIZE the highlight bloom/glow in this style.

Color options:
- Warm gold/amber: sunset, nostalgic, comforting
- Cool blue/cyan: moonlight, digital, futuristic
- Pink/magenta: romantic, neon, synthwave
- Green: toxic, supernatural, matrix
- Orange: fire, warmth, energy
- White/neutral: pure, clean, bright
- Complementary: bloom opposite to shadow color

The bloom color affects emotional tone significantly.

In your response:
- "analysis": describe current bloom/highlight color
- "mutation_applied": describe the color change
- "style_changes": apply to lighting/palette"""
        return await self._vlm_mutate(profile, "Highlight Bloom Colorize", instructions, image_b64, session_id)

    async def _mutate_micro_shadowing(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Create small crisp micro-shadows."""
        instructions = """Add MICRO-SHADOWING to this style - small, detailed shadows that add depth.

Micro-shadow types:
- Contact shadows: tiny dark lines where objects meet
- Pore/texture shadows: shadows in surface details
- Edge shadows: thin dark lines along edges
- Wrinkle shadows: shadows in folds/creases
- Ambient micro-occlusion: tiny crevice darkening
- Hatching shadows: fine lines suggesting shadow

This adds DETAIL and TACTILE quality without changing overall lighting.

In your response:
- "analysis": describe current detail level
- "mutation_applied": describe the micro-shadows added
- "style_changes": apply to texture/lighting"""
        return await self._vlm_mutate(profile, "Micro-Shadowing", instructions, image_b64, session_id)

    async def _mutate_macro_shadow_pivot(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Reposition large shadow masses."""
        instructions = """PIVOT the large shadow masses in this style - reposition major areas of darkness.

Shadow repositioning:
- Shift left/right: move shadow emphasis
- Push to edges: center bright, dark perimeter
- Pull to center: vignette with central shadow
- Top-heavy: shadows concentrated above
- Bottom-heavy: shadows pooling below
- Diagonal: dramatic diagonal shadow division
- Fragmented: break up shadow masses

This affects COMPOSITION and VISUAL WEIGHT dramatically.

In your response:
- "analysis": describe current shadow mass distribution
- "mutation_applied": describe the shadow pivot
- "style_changes": apply to lighting/composition"""
        return await self._vlm_mutate(profile, "Macro Shadow Pivot", instructions, image_b64, session_id)

    # === CONTOUR/EDGE MUTATIONS ===
    async def _mutate_contour_simplify(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Reduce contour lines for poster-like shapes."""
        instructions = """SIMPLIFY contours in this style - reduce to cleaner, bolder shapes.

Simplification approaches:
- Reduce line count: fewer contour lines
- Smooth curves: remove jagged details
- Bold outlines: thick, confident lines
- Flat shapes: poster-like silhouettes
- Remove internal lines: only outer contours
- Geometric reduction: angular simplification

The goal is CLARITY and GRAPHIC IMPACT.

In your response:
- "analysis": describe current contour complexity
- "mutation_applied": describe the simplification
- "style_changes": apply to line_and_shape"""
        return await self._vlm_mutate(profile, "Contour Simplify", instructions, image_b64, session_id)

    async def _mutate_contour_complexify(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Add secondary/tertiary contour lines."""
        instructions = """COMPLEXIFY contours in this style - add more detail and line work.

Complexity additions:
- Secondary contours: inner detail lines
- Hatching: parallel lines for shading
- Cross-hatching: intersecting line patterns
- Texture lines: surface detail indication
- Multiple outlines: layered edge lines
- Decorative flourishes: ornamental additions

The goal is RICHNESS and DETAIL.

In your response:
- "analysis": describe current contour simplicity
- "mutation_applied": describe the added complexity
- "style_changes": apply to line_and_shape"""
        return await self._vlm_mutate(profile, "Contour Complexify", instructions, image_b64, session_id)

    async def _mutate_line_weight_modulation(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Change outline weight/tapering."""
        instructions = """MODULATE line weights in this style - vary thickness for expression.

Weight variations:
- Uniform thick: bold, graphic, strong
- Uniform thin: delicate, precise, refined
- Thick-to-thin: calligraphic, dynamic
- Pressure variation: organic, hand-drawn feel
- Hierarchy: thick for main, thin for detail
- Tapered ends: elegant pointed terminations
- Variable: expressive, energetic variation

Line weight dramatically affects CHARACTER and ENERGY.

In your response:
- "analysis": describe current line weight behavior
- "mutation_applied": describe the weight modulation
- "style_changes": apply to line_and_shape"""
        return await self._vlm_mutate(profile, "Line Weight Modulation", instructions, image_b64, session_id)

    async def _mutate_edge_behavior_swap(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Swap between soft/hard/broken/feathered edges."""
        instructions = """SWAP the edge behavior in this style.

Edge types:
- Hard: crisp, defined, sharp boundaries
- Soft: blurred, gradient, gentle transitions
- Broken: interrupted, sketchy, fragmented
- Feathered: soft fade at edges
- Lost and found: varying edge definition
- Haloed: light outline around shapes
- Double: parallel edge lines

If style has HARD edges → swap to SOFT (or vice versa).
Make the change DRAMATIC and consistent.

In your response:
- "analysis": describe current edge behavior
- "mutation_applied": describe the edge swap
- "style_changes": apply to line_and_shape/texture"""
        return await self._vlm_mutate(profile, "Edge Behavior Swap", instructions, image_b64, session_id)

    async def _mutate_boundary_echo(self, profile: StyleProfile, image_b64: str | None = None, session_id: str | None = None) -> tuple[StyleProfile, str]:
        """Add thin duplicated outlines."""
        instructions = """Add BOUNDARY ECHOES to this style - duplicated/parallel outline effects.

Echo types:
- Offset outline: second line parallel to edge
- Multiple echoes: 2-3 parallel lines
- Color variation: each echo in different shade
- Fading echoes: decreasing opacity outward
- Inner echoes: lines inside the shape
- Outer echoes: lines outside the shape
- Chromatic echo: RGB-separated outlines

This creates DEPTH and GRAPHIC INTEREST.

In your response:
- "analysis": describe current edge treatment
- "mutation_applied": describe the echo effect
- "style_changes": apply to line_and_shape"""
        return await self._vlm_mutate(profile, "Boundary Echo", instructions, image_b64, session_id)

    async def _mutate_halo_generation(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Create outline glow around shapes."""
        instructions = """Add HALO GENERATION to this style - glowing outlines around shapes.

Halo types:
- Soft glow: diffuse light emanating from edges
- Hard halo: crisp bright outline
- Colored halo: tinted glow (warm, cool, neon)
- Inner glow: light inside shapes near edges
- Outer glow: light outside shapes
- Double halo: multiple rings of light
- Gradient halo: color-shifting glow

Consider what halo style FITS the aesthetic:
- Mystical/ethereal → soft colored glow
- Digital/cyber → hard neon outlines
- Dreamy/romantic → warm soft halos
- Dramatic → high-contrast bright edges

In your response:
- "analysis": describe current edge treatment
- "mutation_applied": describe the halo effect
- "style_changes": apply to lighting/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Halo Generation",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === TEXTURE MUTATIONS ===
    async def _mutate_texture_direction_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Rotate texture direction."""
        instructions = """SHIFT the direction of textures in this style.

Texture direction options:
- Horizontal: brushstrokes/grain running left-right
- Vertical: textures running up-down
- Diagonal (45°): dynamic angled textures
- Radial: textures radiating from center
- Concentric: circular texture patterns
- Cross-grain: perpendicular texture layers
- Chaotic: multi-directional texture mix

This affects the ENERGY and MOVEMENT in the image.
Horizontal = calm, vertical = growth, diagonal = dynamic.

In your response:
- "analysis": describe current texture direction
- "mutation_applied": describe the direction shift
- "style_changes": apply to texture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Texture Direction Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_noise_injection(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add controlled micro-noise."""
        instructions = """INJECT controlled noise/grain into this style.

Noise types:
- Fine grain: subtle, organic film-like texture
- Coarse grain: larger, more visible particles
- Monochromatic: grayscale noise only
- Color noise: RGB-varied speckling
- Luminosity noise: noise in brightness only
- Shadow noise: noise concentrated in darks
- Uniform: even noise distribution
- Gradient: noise varying by tone

Add noise that ENHANCES the style without overwhelming it.
Consider what noise level and type fits the aesthetic.

In your response:
- "analysis": describe current texture smoothness
- "mutation_applied": describe the noise injection
- "style_changes": apply to texture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Noise Injection",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_microfracture_pattern(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add cracking/crazing lines."""
        instructions = """Add MICROFRACTURE PATTERNS to this style - cracking, crazing, or craquelure effects.

Fracture types:
- Craquelure: fine web of cracks (aged paint)
- Ice cracks: geometric fracture patterns
- Dried mud: organic crack networks
- Shattered glass: radiating break patterns
- Ceramic crazing: fine surface cracking
- Bark/wood grain: organic linear splits
- Marble veining: irregular natural lines

This adds AGE, HISTORY, or TENSION to surfaces.
Consider what fracture pattern fits the style's mood.

In your response:
- "analysis": describe current surface integrity
- "mutation_applied": describe the fracture pattern
- "style_changes": apply to texture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Microfracture Pattern",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_crosshatch_density_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Alter crosshatching density."""
        instructions = """SHIFT the density of crosshatching/line-based shading in this style.

Density options:
- Dense: tight, closely-spaced lines, dark shadows
- Sparse: widely-spaced lines, lighter feel
- Variable: density changes with value
- Single-direction: parallel lines only
- Cross-hatched: intersecting line layers
- Multi-angle: 3+ directions of lines
- Stippled: dots instead of lines

If style has hatching, INCREASE or DECREASE density dramatically.
If no hatching, ADD hatching as a shading technique.

In your response:
- "analysis": describe current shading technique
- "mutation_applied": describe the density shift
- "style_changes": apply to texture/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Crosshatch Density Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === MATERIAL/SURFACE MUTATIONS ===
    async def _mutate_background_material_swap(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Change backdrop material."""
        instructions = """SWAP the background material in this style - change the apparent surface/substrate.

Background materials:
- Canvas: woven texture, fabric feel, painterly
- Paper: smooth or textured, absorbent quality
- Metal: reflective, industrial, cold
- Wood: grain patterns, warm, organic
- Stone: rough, ancient, heavy
- Glass: transparent, reflective, modern
- Concrete: urban, brutalist, raw
- Fabric: soft, draped, textile patterns
- Digital: clean, perfect, synthetic

Consider what background material creates INTERESTING CONTRAST with the style.
The material should enhance, not distract from, the content.

In your response:
- "analysis": describe current background quality
- "mutation_applied": describe the material swap
- "style_changes": apply to texture/composition"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Background Material Swap",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_surface_material_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Transform surface feel."""
        instructions = """SHIFT the surface material quality in this style - transform how surfaces feel.

Surface qualities:
- Matte/Chalky: soft, powdery, light-absorbing
- Glossy/Wet: shiny, reflective, liquid-like
- Rough/Textured: bumpy, tactile, imperfect
- Smooth/Polished: slick, clean, refined
- Organic/Natural: skin-like, plant-like, living
- Metallic/Industrial: hard, cold, manufactured
- Translucent/Waxy: semi-transparent, diffuse glow
- Velvet/Fabric: soft, plush, luxurious

Transform the dominant surface quality to something CONTRASTING.
This changes the TACTILE FEEL of the entire style.

In your response:
- "analysis": describe current surface materiality
- "mutation_applied": describe the surface shift
- "style_changes": apply to texture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Surface Material Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_translucency_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Alter transparency levels."""
        instructions = """SHIFT the translucency/transparency in this style.

Translucency options:
- Increase opacity: make elements more solid, opaque
- Increase transparency: make elements see-through, ghostly
- Add layering: translucent overlapping planes
- Selective transparency: some elements clear, others solid
- Gradient opacity: fading from solid to transparent
- Glass-like: clear but with refraction/distortion
- Frosted: diffuse semi-transparency
- Veil effect: sheer fabric-like translucency

This affects DEPTH and MYSTERY in the composition.
More transparency = more ethereal, more opacity = more grounded.

In your response:
- "analysis": describe current transparency behavior
- "mutation_applied": describe the translucency shift
- "style_changes": apply to texture/composition"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Translucency Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_subsurface_scatter_tweak(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Adjust internal glow in translucent materials."""
        instructions = """TWEAK the subsurface scattering (SSS) in this style - the internal glow in translucent materials.

SSS adjustments:
- Increase SSS: more internal glow, light passing through
- Decrease SSS: more opaque, less translucent glow
- Warm SSS: orange/red internal light (flesh, wax)
- Cool SSS: blue/green internal light (ice, jade)
- Add SSS: introduce internal glow where there was none
- Color shift: change the internal light color
- Depth variation: shallow vs deep scatter

SSS creates LIFE and ORGANIC QUALITY:
- Skin, leaves, wax, marble all have SSS
- It makes materials feel ALIVE and DIMENSIONAL

In your response:
- "analysis": describe current material translucency
- "mutation_applied": describe the SSS tweak
- "style_changes": apply to texture/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Subsurface Scatter Tweak",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_anisotropy_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Change directional light reflection."""
        instructions = """SHIFT the anisotropy in this style - directional light reflection behavior.

Anisotropy types:
- Hair/fiber: stretched highlights along strands
- Brushed metal: elongated reflections in brush direction
- Silk/satin: directional sheen following weave
- Vinyl/records: concentric reflection rings
- Water ripples: wavy light patterns
- Wood grain: highlights following grain
- Isotropic (none): uniform reflection in all directions

Anisotropy creates MATERIAL CHARACTER:
- Adds realism to hair, metal, fabric
- Creates directional energy and movement

Add or modify anisotropic highlights to enhance material feel.

In your response:
- "analysis": describe current reflection behavior
- "mutation_applied": describe the anisotropy shift
- "style_changes": apply to texture/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Anisotropy Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_reflectivity_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Change reflectivity without color change."""
        instructions = """SHIFT the reflectivity levels in this style - how much surfaces mirror their environment.

Reflectivity levels:
- Mirror-like: perfect environment reflections
- High gloss: clear but imperfect reflections
- Semi-gloss: soft, blurred reflections
- Satin: subtle directional sheen
- Matte: no visible reflections
- Fresnel: reflection increases at grazing angles
- Metallic: colored reflections (gold, copper, steel)

Adjust reflectivity to change MATERIAL FEEL:
- More reflection = wet, polished, precious
- Less reflection = dry, aged, matte

Keep colors the same but change how light interacts.

In your response:
- "analysis": describe current reflectivity
- "mutation_applied": describe the reflectivity shift
- "style_changes": apply to texture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Reflectivity Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === TONAL MUTATIONS ===
    async def _mutate_midtone_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Mutate midtones only."""
        instructions = """SHIFT the midtones in this style - adjust the middle values while preserving highlights and shadows.

Midtone adjustments:
- Lighten midtones: airier, more open feel
- Darken midtones: moodier, more weight
- Warm midtones: add golden/amber to mid values
- Cool midtones: add blue/cyan to mid values
- Increase midtone contrast: more punch in middle range
- Flatten midtones: more uniform mid-range
- Color shift: change midtone hue selectively

Midtones carry most of the IMAGE INFORMATION.
Shifting them changes the overall mood without losing detail.

Keep highlights and deep shadows relatively stable.

In your response:
- "analysis": describe current midtone character
- "mutation_applied": describe the midtone shift
- "style_changes": apply to palette/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Midtone Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_tonal_compression(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Compress tonal range for flatter look."""
        instructions = """COMPRESS the tonal range in this style - reduce the difference between lights and darks.

Compression approaches:
- Lift shadows: brighten dark areas
- Lower highlights: dim bright areas
- Both: squeeze toward midtones from both ends
- Selective: compress only darks OR only lights
- Zone compression: compress specific tonal zones

Compression creates:
- Flatter, more graphic look
- Vintage/faded photograph feel
- Softer, dreamier mood
- Reduced drama and contrast

The goal is to REDUCE tonal range for a specific aesthetic effect.

In your response:
- "analysis": describe current tonal range
- "mutation_applied": describe the compression
- "style_changes": apply to lighting/palette"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Tonal Compression",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_tonal_expansion(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Expand tonal range for deeper contrast."""
        instructions = """EXPAND the tonal range in this style - increase the difference between lights and darks.

Expansion approaches:
- Deepen shadows: push darks toward black
- Brighten highlights: push lights toward white
- Both: expand from both ends
- Selective: expand only darks OR only lights
- S-curve: expand midtone contrast

Expansion creates:
- More dramatic, punchy look
- Higher contrast, bolder feel
- Increased depth and dimension
- More visual impact

The goal is to INCREASE tonal range for dramatic effect.

In your response:
- "analysis": describe current tonal range
- "mutation_applied": describe the expansion
- "style_changes": apply to lighting/palette"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Tonal Expansion",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_microcontrast_tuning(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Adjust small-scale contrast."""
        instructions = """TUNE the microcontrast in this style - the small-scale local contrast that creates texture and clarity.

Microcontrast adjustments:
- Increase: sharper, more defined, crispy detail
- Decrease: softer, smoother, dreamier
- Texture emphasis: enhance surface detail visibility
- Edge clarity: increase definition at boundaries
- Gritty: high microcontrast for rough feel
- Smooth: low microcontrast for soft feel

Microcontrast affects PERCEIVED SHARPNESS:
- High = more texture, more "pop", more detail
- Low = softer, more blended, painterly

This is different from overall contrast - it's about LOCAL detail.

In your response:
- "analysis": describe current detail/texture clarity
- "mutation_applied": describe the microcontrast tuning
- "style_changes": apply to texture/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Microcontrast Tuning",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_contrast_channel_swap(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Modify contrast selectively by channel."""
        instructions = """SWAP contrast behavior between channels - modify contrast selectively by color channel.

Channel contrast options:
- High red contrast: punchy reds, compressed cyan
- High green contrast: vibrant greens, muted magenta
- High blue contrast: deep blues, warm tones compressed
- Luminosity only: contrast in brightness, not saturation
- Saturation contrast: vivid vs muted, not light vs dark
- Split channels: different contrast per RGB channel
- Cross-process: inverted channel contrast (film effect)

This creates UNUSUAL COLOR RELATIONSHIPS:
- Can make certain colors pop while others recede
- Creates stylized, non-photographic looks
- Film cross-processing effects

In your response:
- "analysis": describe current channel balance
- "mutation_applied": describe the channel contrast swap
- "style_changes": apply to palette/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Contrast Channel Swap",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === BLUR/FOCUS MUTATIONS ===
    async def _mutate_directional_blur(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply motion-like blur along vector."""
        instructions = """Add DIRECTIONAL BLUR to this style - motion-like blur along a specific direction.

Blur directions:
- Horizontal: side-to-side motion, panning feel
- Vertical: up-down motion, falling/rising sense
- Diagonal: dynamic movement, action feel
- Radial: zoom blur, explosive energy
- Circular: spinning, rotational motion
- Selective: blur only background or foreground
- Speed lines: implied motion without actual blur

Blur intensity:
- Subtle: slight softness suggesting movement
- Moderate: clear motion indication
- Extreme: strong speed/action feel

This adds DYNAMISM and ENERGY to the style.

In your response:
- "analysis": describe current motion/stillness quality
- "mutation_applied": describe the directional blur
- "style_changes": apply to texture/composition"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Directional Blur",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_focal_plane_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Move focus point."""
        instructions = """SHIFT the focal plane in this style - move the point of sharp focus.

Focal plane options:
- Near focus: sharp foreground, blurred background
- Far focus: sharp background, blurred foreground
- Mid-plane: sharp middle ground, soft front and back
- Shallow depth: very thin focus plane, extreme bokeh
- Deep focus: everything sharp, large depth of field
- Tilt-shift: angled focus plane, miniature effect
- Split focus: multiple focal points

Focus affects ATTENTION and NARRATIVE:
- Guides viewer's eye to important elements
- Creates depth and dimension
- Can make subjects feel closer or more distant

In your response:
- "analysis": describe current focus behavior
- "mutation_applied": describe the focal plane shift
- "style_changes": apply to composition/texture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Focal Plane Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_mask_boundary_mutation(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Modify mask borders."""
        instructions = """MUTATE the mask/border boundaries in this style - change how element edges are defined.

Boundary options:
- Soft feather: gradual fade at edges
- Hard cut: sharp, defined boundaries
- Irregular: organic, rough edge shapes
- Geometric: clean, angular mask edges
- Torn: ragged, paper-tear effect
- Dissolve: pixelated or noisy edge transition
- Glow edge: luminous boundary region
- Double edge: outlined mask border

This affects how ELEMENTS SEPARATE from each other:
- Clean masks = graphic, designed feel
- Soft masks = painterly, blended feel
- Irregular masks = organic, natural feel

In your response:
- "analysis": describe current edge/boundary treatment
- "mutation_applied": describe the mask boundary change
- "style_changes": apply to composition/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Mask Boundary Mutation",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === SILHOUETTE MUTATIONS (EXTENDED) ===
    async def _mutate_silhouette_merge(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Fuse two silhouettes into composite."""
        instructions = """MERGE silhouettes in this style - fuse shapes into composite forms.

Merge approaches:
- Overlap blend: shapes layered and fused
- Boolean union: combine into single unified shape
- Interpenetration: forms passing through each other
- Shadow merge: shadows connecting separate elements
- Contour fusion: outlines flowing into each other
- Gradient blend: shapes fading into one another
- Negative space merge: backgrounds unifying

This creates VISUAL CONNECTION between elements:
- Suggests relationship, unity, transformation
- Can create new hybrid forms
- Adds compositional cohesion

In your response:
- "analysis": describe current shape separation
- "mutation_applied": describe the silhouette merge
- "style_changes": apply to line_and_shape/composition"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Silhouette Merge",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_silhouette_subtract(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Remove chunks for negative-space shapes."""
        instructions = """SUBTRACT from silhouettes - create negative-space shapes by removing chunks.

Subtraction techniques:
- Boolean difference: cut geometric shapes from forms
- Bite marks: irregular chunks removed from edges
- Window cutouts: rectangular/circular holes through shapes
- Erosion: edges eaten away, creating ragged boundaries
- Slice removal: clean cuts removing sections
- Scatter holes: multiple small perforations
- Crescent bites: curved chunks missing

Negative space effects:
- Reveals background through foreground
- Creates visual interest through absence
- Suggests decay, transformation, incompleteness
- Can create secondary shapes in the gaps
- Adds rhythm through solid/void alternation

In your response:
- "analysis": describe current silhouette solidity
- "mutation_applied": describe the subtraction approach
- "style_changes": apply to line_and_shape/composition"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Silhouette Subtract",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_silhouette_distortion(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Stretch/bend/fracture silhouette."""
        instructions = """DISTORT silhouettes - stretch, bend, or fracture the shape outlines.

Distortion types:
- Stretch: elongate in one direction, compress in another
- Bend: curve rigid forms, add organic flow to geometric
- Fracture: break silhouettes into shards, fragments
- Melt: forms drooping, flowing downward
- Twist: spiral/helical deformation
- Bulge: localized expansion or swelling
- Pinch: localized compression or narrowing
- Wave: undulating edges, ripple effects

Distortion intensity:
- Subtle: barely perceptible warping
- Moderate: clearly visible but still recognizable
- Extreme: heavily transformed, barely recognizable

Effects on visual perception:
- Movement and dynamism
- Emotional tension or release
- Surreal/dreamlike quality
- Physical forces made visible

In your response:
- "analysis": describe current silhouette stability
- "mutation_applied": describe the distortion type and intensity
- "style_changes": apply to line_and_shape/composition"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Silhouette Distortion",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_internal_geometry_twist(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Twist inside while keeping silhouette."""
        instructions = """TWIST internal geometry while preserving the outer silhouette.

The silhouette stays the same, but everything inside transforms:
- Spiral twist: contents rotate around a central axis
- Vortex: swirling from edges to center
- Torsion: different parts twist at different rates
- Fold: internal planes bending over themselves
- Knot: interweaving internal structures
- Ribbon curl: linear elements becoming coiled
- Corkscrew: helical transformation of internals

Effects of internal twist:
- Creates visual tension (stable outside, chaotic inside)
- Suggests motion or transformation in progress
- Adds dynamism without changing overall form
- Can create optical illusion effects
- Implies hidden energy or force

Preserve:
- Outer boundary/silhouette stays intact
- Overall recognizable form

Transform:
- Internal lines, textures, patterns
- Inner structure and geometry

In your response:
- "analysis": describe current internal structure
- "mutation_applied": describe the internal twist type
- "style_changes": apply to line_and_shape/texture"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Internal Geometry Twist",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === DEPTH MUTATIONS ===
    async def _mutate_background_depth_collapse(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Compress background depth."""
        instructions = """COLLAPSE background depth - compress the sense of space behind foreground elements.

Depth collapse techniques:
- Flat backdrop: remove all depth cues from background
- Stage flat: background becomes theatrical painted flat
- Poster space: everything pushed to 2D picture plane
- Compressed atmosphere: reduce atmospheric perspective
- Stacked planes: depth layers flatten onto each other
- Ambient blur: background loses detail, becomes solid
- Color compression: background becomes uniform tone

Effects of collapsed depth:
- Focuses attention on foreground
- Creates graphic, poster-like quality
- Removes distraction of deep space
- Can create claustrophobic or intimate feeling
- Emphasizes silhouettes against flat backgrounds

Preserve:
- Foreground detail and depth
- Subject separation from background

Flatten:
- Background spatial recession
- Atmospheric depth cues
- Far-distance detail

In your response:
- "analysis": describe current background depth treatment
- "mutation_applied": describe the depth collapse approach
- "style_changes": apply to composition/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Background Depth Collapse",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_depth_flattening(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Reduce depth cues."""
        instructions = """FLATTEN depth - reduce all depth cues throughout the entire image.

Depth flattening techniques:
- Remove atmospheric perspective (no haze/fade with distance)
- Eliminate size scaling (near/far objects similar size)
- Remove overlap cues (no occlusion hierarchy)
- Flatten shadows (no depth-indicating cast shadows)
- Uniform focus (no depth of field)
- Isometric treatment (no perspective convergence)
- Equal detail everywhere (no detail falloff)

Flattening approaches:
- Graphic/posterized: bold flat shapes
- Ukiyo-e style: layered flat planes
- Paper cutout: shapes without depth
- Stained glass: outlined flat areas
- Cartoon flat: cel-shaded no-depth look
- Map view: bird's eye flat representation

Effects:
- Creates 2D graphic quality
- Emphasizes pattern over space
- Removes "window into world" feeling
- Creates decorative, design-like aesthetic

In your response:
- "analysis": describe current depth cues present
- "mutation_applied": describe the flattening approach
- "style_changes": apply to composition/lighting/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Depth Flattening",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_depth_expansion(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Exaggerate depth/perspective."""
        instructions = """EXPAND depth - exaggerate all depth cues to create dramatic spatial recession.

Depth expansion techniques:
- Extreme atmospheric perspective (heavy haze/fade with distance)
- Exaggerated size scaling (dramatic near/far size difference)
- Strong overlap hierarchy (clear layering of planes)
- Deep cast shadows (long, dramatic shadows)
- Extreme depth of field (sharp foreground, blurred background)
- Forced perspective (exaggerated convergence)
- Detail falloff (crisp near, vague far)

Expansion approaches:
- Baroque deep space: dramatic recession into darkness
- Wide-angle distortion: fisheye-like depth exaggeration
- Theatrical depth: stage-like receding planes
- Infinite regression: space extending forever
- Vertiginous: dizzying sense of depth/height
- Tunnel effect: space pulling viewer inward

Effects:
- Creates immersive, 3D quality
- Adds drama and grandeur
- Pulls viewer into the scene
- Emphasizes spatial relationships

In your response:
- "analysis": describe current depth treatment
- "mutation_applied": describe the depth expansion approach
- "style_changes": apply to composition/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Depth Expansion",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === COMPOSITION MUTATIONS (NEW) ===
    async def _mutate_quadrant_mutation(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Mutate only one quadrant."""
        instructions = """MUTATE only ONE QUADRANT - apply a localized style change to one quarter of the composition.

Choose a quadrant:
- Top-left: upper left quarter
- Top-right: upper right quarter
- Bottom-left: lower left quarter
- Bottom-right: lower right quarter

Quadrant mutation types:
- Color shift: different palette in one quadrant
- Texture change: different surface treatment
- Style shift: different rendering approach
- Detail density: more or less detail
- Lighting variation: different light quality
- Line weight change: thicker or thinner
- Saturation zone: more or less vivid

Effects of quadrant mutation:
- Creates visual tension/interest
- Draws attention to specific area
- Suggests transition or boundary
- Can create surreal collage effect
- Establishes visual hierarchy

The mutation should feel intentional and interesting, not like an error.
Keep 3 quadrants consistent, dramatically change 1.

In your response:
- "analysis": describe current composition uniformity
- "mutation_applied": describe which quadrant and what change
- "style_changes": apply localized changes to relevant sections"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Quadrant Mutation",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_object_alignment_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Rotate/offset/misalign objects."""
        instructions = """SHIFT object alignment - rotate, offset, or misalign elements from their expected positions.

Alignment shift types:
- Rotation: elements tilted from vertical/horizontal
- Offset: elements displaced from center or grid
- Stagger: elements arranged in irregular steps
- Drift: elements floating away from anchor points
- Cant: slight angular tilt across composition
- Scatter: elements dispersed from organized arrangement
- Skew: parallel lines no longer parallel

Misalignment approaches:
- Subtle tilt: barely perceptible rotation (1-5°)
- Moderate offset: noticeable but comfortable displacement
- Extreme misalignment: jarring, disorienting placement
- Organic scatter: natural, random-feeling arrangement
- Rhythmic offset: patterned displacement
- Gravity defiant: elements floating/falling

Effects:
- Creates dynamism and movement
- Adds tension or unease
- Suggests instability or transformation
- Can feel playful or unsettling
- Breaks rigid formality

In your response:
- "analysis": describe current alignment/grid structure
- "mutation_applied": describe the alignment shift
- "style_changes": apply to composition/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Object Alignment Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_spatial_hierarchy_flip(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Reorder visual priority."""
        instructions = """FLIP spatial hierarchy - reorder the visual priority of elements in the composition.

Hierarchy elements to consider:
- Foreground vs background dominance
- Primary subject vs secondary elements
- Figure vs ground relationship
- Positive vs negative space prominence
- Detail focus areas
- Light/dark emphasis

Hierarchy flip approaches:
- Background promotion: make background the focal point
- Subject demotion: reduce primary subject emphasis
- Negative space dominance: voids become more important than forms
- Detail inversion: detailed areas become simple, simple becomes detailed
- Edge vs center: shift focus from center to periphery
- Scale reversal: small elements become visually dominant

Techniques to flip hierarchy:
- Adjust contrast (boost background, reduce foreground)
- Shift detail distribution
- Change color saturation hierarchy
- Alter lighting focus
- Modify edge definition
- Adjust scale relationships

Effects:
- Creates unexpected focal points
- Subverts viewer expectations
- Adds conceptual depth
- Can create surreal or unsettling feeling

In your response:
- "analysis": describe current visual hierarchy
- "mutation_applied": describe the hierarchy flip
- "style_changes": apply to composition/lighting/palette"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Spatial Hierarchy Flip",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_balance_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Shift overall visual weight."""
        instructions = """SHIFT visual balance - redistribute the visual weight across the composition.

Visual weight factors:
- Tonal mass (dark areas are heavier)
- Color saturation (vivid is heavier)
- Detail density (detailed areas draw attention)
- Size and scale
- Isolation (lone elements stand out)
- Position (top feels lighter, bottom heavier)

Balance shift directions:
- Left-heavy: weight concentrated on left side
- Right-heavy: weight concentrated on right side
- Top-heavy: weight concentrated at top
- Bottom-heavy: weight concentrated at bottom
- Center-heavy: weight pulled to center
- Edge-heavy: weight pushed to periphery
- Corner anchor: weight concentrated in one corner

Balance types:
- Symmetrical: equal weight both sides
- Asymmetrical: unequal but balanced
- Radial: balanced around a center point
- Crystallographic: even scatter throughout
- Imbalanced: intentionally unstable

Effects:
- Changes visual flow and reading direction
- Creates tension or calm
- Guides eye movement
- Establishes mood (stable vs dynamic)

In your response:
- "analysis": describe current visual balance
- "mutation_applied": describe the balance shift direction
- "style_changes": apply to composition/palette/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Balance Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_interplay_swap(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Swap dominance between elements."""
        instructions = """SWAP interplay dominance - exchange which elements dominate vs recede in the composition.

Element pairs to consider swapping:
- Figure/ground: make background dominant, subject recessive
- Light/shadow: shadows become primary, lit areas secondary
- Color/neutrals: neutrals dominate, colors become accents
- Lines/shapes: swap emphasis between linework and mass
- Texture/smooth: textured areas recede, smooth becomes focal
- Detail/void: empty space becomes prominent, detail recedes
- Warm/cool: temperature dominance reversal

Swap mechanisms:
- Scale inversion: dominant element shrinks, recessive grows
- Contrast redistribution: shift contrast to previously subtle areas
- Saturation swap: desaturate what was vivid, saturate what was muted
- Focus shift: blur what was sharp, sharpen what was blurred
- Position exchange: reposition elements in visual hierarchy
- Edge treatment: soften what was hard, define what was soft

Effects of interplay swap:
- Subverts visual expectations
- Creates new focal dynamics
- Reveals overlooked elements
- Can dramatically transform perception of scene

In your response:
- "analysis": describe current element dominance relationships
- "mutation_applied": describe which elements were swapped
- "style_changes": apply to relevant sections"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Interplay Swap",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_vignette_modification(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add/modify vignette."""
        instructions = """MODIFY vignette - add or alter edge darkening/lightening effects.

Vignette types:
- Classic dark: edges fade to black/dark
- Light vignette: edges fade to white/bright
- Color vignette: edges tinted with a specific hue
- Burned edges: harsh, irregular darkening
- Soft fade: gentle gradient to edge
- Hard edge: sharp transition at border
- Asymmetric: vignette stronger on certain sides

Vignette shapes:
- Circular/oval: classic photographic look
- Rectangular: following frame edge
- Irregular: organic, painterly edges
- Directional: stronger on one side
- Corner emphasis: darkening in corners only
- Split: different treatment top/bottom or left/right

Vignette intensity:
- Subtle: barely noticeable edge darkening
- Moderate: clearly present but not distracting
- Dramatic: strong, theatrical darkening
- Extreme: severe, almost masking edges

Effects:
- Focuses attention on center
- Creates intimate, enclosed feeling
- Adds vintage or cinematic quality
- Frames the composition
- Can add drama or mystery

In your response:
- "analysis": describe current edge treatment
- "mutation_applied": describe the vignette modification
- "style_changes": apply to composition/lighting"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Vignette Modification",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === MOTIF MUTATIONS (NEW) ===
    async def _mutate_motif_mirroring(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Mirror motif H/V/diagonal."""
        instructions = """MIRROR motifs - reflect recurring visual elements across an axis.

Mirror axes:
- Horizontal: top-bottom reflection
- Vertical: left-right reflection
- Diagonal: corner-to-corner reflection
- Radial: reflection around a center point
- Multiple: reflections creating kaleidoscope effect

Mirroring approaches:
- Perfect symmetry: exact reflection
- Approximate symmetry: nearly mirrored with subtle variation
- Partial mirror: only some elements reflected
- Interrupted mirror: reflection with breaks/gaps
- Layered reflection: multiple mirror planes

What to mirror:
- Shapes and forms
- Color patterns
- Texture directions
- Line work
- Motif arrangements
- Compositional elements

Effects of mirroring:
- Creates formal symmetry
- Adds visual stability and order
- Can create butterfly/Rorschach effects
- Suggests duality or reflection
- Creates pattern and rhythm
- Can feel ceremonial or sacred

In your response:
- "analysis": describe current motif arrangement
- "mutation_applied": describe the mirror axis and approach
- "style_changes": apply to composition/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Motif Mirroring",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_motif_scaling(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Scale repeated motifs."""
        instructions = """SCALE motifs - change the size of recurring visual elements.

Scaling directions:
- Enlarge: make motifs bigger, more prominent
- Shrink: make motifs smaller, more subtle
- Variable: different sizes for different instances
- Progressive: gradual size change across composition
- Inverse: small becomes large, large becomes small

Scaling patterns:
- Uniform scaling: all motifs same size change
- Hierarchical: size indicates importance
- Distance-based: size suggests depth
- Random scatter: varied sizes for organic feel
- Nested: smaller versions inside larger
- Cascading: diminishing sizes in sequence

Scale relationships:
- Micro to macro: tiny details vs large forms
- Foreground/background: size for depth
- Focal hierarchy: important elements larger
- Rhythmic variation: alternating sizes

Effects of scaling:
- Creates depth and perspective
- Establishes visual hierarchy
- Adds variety and interest
- Can suggest distance or importance
- Creates pattern density variation

In your response:
- "analysis": describe current motif sizes
- "mutation_applied": describe the scaling approach
- "style_changes": apply to composition/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Motif Scaling",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_motif_repetition(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Duplicate and scatter motif."""
        instructions = """ADD motif REPETITION - duplicate and scatter recurring visual elements.

Repetition patterns:
- Grid repeat: regular rows and columns
- Scattered: random placement across composition
- Radial: repeating around a center point
- Linear: along a line or path
- Clustered: grouped repetitions
- Graduated: density changes across space
- Border/frame: repetition along edges

Repetition variations:
- Exact copies: identical repetitions
- Varied scale: different sizes
- Rotated: different orientations
- Color shifted: hue variations
- Degraded: quality decreasing with each repeat
- Overlapping: repetitions intersecting
- Fading: opacity decreasing

Effects of repetition:
- Creates rhythm and pattern
- Emphasizes motif importance
- Fills space decoratively
- Can suggest motion or time
- Creates visual texture
- Adds complexity and richness

In your response:
- "analysis": describe current motif presence
- "mutation_applied": describe the repetition pattern
- "style_changes": apply to composition/line_and_shape"""

        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Motif Repetition",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === COLOR ROLE MUTATIONS ===
    async def _mutate_color_role_reassignment(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Swap color roles - reassign which colors serve as dominant, accent, background."""
        instructions = """Identify the COLOR ROLES in this style and SWAP them to create a new hierarchy.

Color roles to analyze:
- Dominant color: The most prominent, attention-grabbing hue
- Secondary/supporting color: Complements or contrasts with dominant
- Accent color: Used sparingly for highlights or emphasis
- Background/negative space color: Base or recessive tones

Possible reassignments:
- Promote accent to dominant (what was subtle becomes bold)
- Demote dominant to background (former star becomes backdrop)
- Swap dominant and secondary (flip the hierarchy)
- Elevate background to accent (negative space becomes punctuation)

Analyze the current color hierarchy and perform a meaningful role swap that transforms the visual impact."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Color Role Reassignment",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_saturation_scalpel(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply selective saturation changes to specific areas or color ranges."""
        instructions = """Apply SURGICAL SATURATION changes - not uniform, but targeted to specific areas or color ranges.

Selective saturation approaches:
- Edge saturation: Boost saturation at edges, desaturate centers (or vice versa)
- Focal saturation: High saturation at focal point, fading outward
- Hue-selective: Saturate only warm colors while desaturating cools (or vice versa)
- Depth-based: Saturated foreground, desaturated background (atmospheric)
- Tonal saturation: Saturate midtones, desaturate highlights/shadows
- Complementary split: Saturate complementary pairs, mute everything else

Analyze which areas or colors currently carry the most saturation, then apply a selective adjustment that creates visual interest through contrast."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Saturation Scalpel",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_negative_color_injection(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Inject inverted or complementary color accents into the style."""
        instructions = """INJECT NEGATIVE or INVERTED colors as accent elements into the style.

Negative color injection approaches:
- Complementary injection: Add the exact complement of the dominant hue as sharp accents
- Inverted shadows: Shadows take on inverted/negative colors
- Chromatic aberration: Color separation at edges with opposing hues
- Pop accents: Small areas of color-inverted highlights
- Negative space color: Fill negative space with color opposites
- Film negative zones: Selective areas rendered as color negatives

Analyze the current palette and identify where injecting inverted/complementary colors would create maximum visual tension or interest."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Negative Color Injection",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_ambient_color_suction(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Pull ambient environmental colors into shadow areas."""
        instructions = """PULL AMBIENT COLORS into the shadow regions, creating color bleeding and environmental influence.

Ambient color suction approaches:
- Sky suction: Pull blue/atmospheric colors into upward-facing shadows
- Ground bounce: Pull warm earth tones into downward shadows
- Environmental bleed: Nearby dominant colors seep into adjacent shadows
- Complementary shadow fill: Shadows absorb the complement of highlights
- Rim light color pull: Edge light colors bleed into shadow boundaries
- Subsurface scatter simulation: Warm skin tones or translucent color in shadows

Analyze the current lighting and palette, then define how ambient colors should infiltrate shadow regions to create richer, more atmospheric color interactions."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Ambient Color Suction",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_local_color_mutation(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply zone-specific palette changes - different colors in different areas."""
        instructions = """Apply ZONE-SPECIFIC color mutations - different color treatments in different spatial regions.

Local color mutation approaches:
- Quadrant split: Each quadrant or region gets a different color treatment
- Depth zones: Foreground/midground/background each have distinct palettes
- Radial zones: Center vs. periphery have different color temperatures
- Subject isolation: Subject in one palette, environment in another
- Gradient territory: Color shifts as you move across the composition
- Light pool zones: Areas of different light color create local palettes

Analyze the composition's spatial structure and apply distinct color mutations to different zones while maintaining overall visual coherence."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Local Color Mutation",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === DETAIL/FORM MUTATIONS ===
    async def _mutate_detail_density_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Shift where detail clusters - redistribute visual complexity."""
        instructions = """Analyze WHERE DETAIL CLUSTERS in this style and SHIFT the distribution.

Detail density patterns to consider:
- Center-heavy: Detail concentrated at focal point, sparse edges
- Edge-heavy: Rich detail at periphery, minimal center
- Gradient density: Detail increases/decreases along an axis
- Clustered nodes: Detail concentrated in isolated pockets
- Even distribution: Uniform detail throughout
- Hierarchical: Primary subject detailed, secondary elements simplified

Analyze the current detail distribution and shift it to a different pattern. Consider how this affects visual weight, eye movement, and compositional balance."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Detail Density Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_form_simplification(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Reduce forms to simpler, more essential geometry."""
        instructions = """SIMPLIFY the forms in this style - reduce complexity to essential shapes.

Form simplification approaches:
- Geometric reduction: Organic forms become basic shapes (circles, triangles, rectangles)
- Silhouette priority: Internal detail removed, only outlines remain
- Planar simplification: 3D forms flattened to 2D planes
- Iconic reduction: Complex subjects become symbol-like representations
- Mass blocking: Fine detail merged into larger shape masses
- Contour smoothing: Jagged or complex edges become flowing curves

Analyze the current form complexity and apply meaningful simplification that retains the essence while reducing visual complexity."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Form Simplification",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_form_complication(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add complexity to forms - micro-folds, greebles, intricate detail."""
        instructions = """COMPLICATE the forms in this style - add detail, texture, and visual complexity.

Form complication approaches:
- Greebling: Add small technical/mechanical details to surfaces
- Micro-folds: Introduce wrinkles, creases, fabric-like complexity
- Fractal detail: Self-similar patterns at multiple scales
- Organic growth: Add tendrils, veins, branching structures
- Surface articulation: Break smooth surfaces into facets or panels
- Ornamental addition: Decorative flourishes, filigree, embellishments

Analyze the current form simplicity and add meaningful complexity that enriches the visual without overwhelming the composition."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Form Complication",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_proportion_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Alter the proportional relationships between elements."""
        instructions = """SHIFT PROPORTIONS - alter the size relationships between visual elements.

Proportion shift approaches:
- Exaggeration: Enlarge key features, shrink secondary ones
- Miniaturization: Make dominant elements smaller, elevate the minor
- Elongation: Stretch forms vertically or horizontally
- Compression: Squash or compact proportions
- Head-body ratio: Alter figure proportions (chibi, heroic, realistic)
- Negative space expansion: Grow empty space relative to subjects
- Detail scaling: Make small details proportionally larger

Analyze the current proportional relationships and shift them to create a new visual dynamic. Consider how proportion affects mood, emphasis, and style character."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Proportion Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === FLOW/RHYTHM MUTATIONS ===
    async def _mutate_path_flow_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Alter the dominant directional flow that guides the eye."""
        instructions = """SHIFT THE VISUAL PATH FLOW - change how the eye moves through the composition.

Path flow approaches:
- Diagonal dominance: Strong diagonal lines guide movement
- Circular/spiral: Eye travels in curves or spirals
- Z-pattern or S-curve: Classic reading patterns
- Centripetal: All lines draw toward center
- Centrifugal: Lines radiate outward from center
- Vertical cascade: Downward or upward flow
- Horizontal scan: Left-right movement emphasis
- Chaotic/scattered: Multiple competing paths

Analyze the current visual flow and redirect it. Consider how lines, edges, contrast, and color create implicit paths for the viewer's eye."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Path Flow Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_rhythm_disruption(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Break or introduce visual repetition intervals."""
        instructions = """DISRUPT THE VISUAL RHYTHM - break existing patterns or introduce new intervals.

Rhythm disruption approaches:
- Syncopation: Offset regular intervals, create unexpected beats
- Break the pattern: Interrupt a repeating element with something different
- Stutter effect: Repeat elements at irregular, jarring intervals
- Silence insertion: Add unexpected gaps in visual rhythm
- Tempo change: Speed up or slow down repetition frequency
- Polyrhythm: Overlay multiple conflicting rhythmic patterns
- Accent displacement: Move emphasis to unexpected positions

Analyze the current visual rhythm (repeating elements, spacing, intervals) and introduce meaningful disruption that creates tension or interest."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Rhythm Disruption",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_rhythm_rebalance(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Rebalance visual rhythm by adjusting motif spacing and intervals."""
        instructions = """REBALANCE THE VISUAL RHYTHM - adjust spacing and intervals for better flow.

Rhythm rebalance approaches:
- Regularize: Make irregular intervals more consistent
- Golden ratio spacing: Apply mathematical harmony to intervals
- Breathing room: Add more space between repeated elements
- Tighten cadence: Compress spacing for more intensity
- Progressive spacing: Intervals that gradually increase or decrease
- Alternating density: Vary spacing in a predictable pattern
- Weight distribution: Balance heavy and light rhythmic elements

Analyze the current motif spacing and repetition intervals, then rebalance them to create a more harmonious or intentionally structured visual rhythm."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Rhythm Rebalance",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_directional_energy_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Alter the implied directional energy and movement."""
        instructions = """SHIFT DIRECTIONAL ENERGY - change the implied movement and force vectors.

Directional energy approaches:
- Upward thrust: Aspiration, growth, lightness
- Downward pull: Weight, gravity, grounding
- Explosive outward: Expansion, release, burst
- Implosive inward: Compression, focus, concentration
- Rotational: Spinning, swirling, cyclonic energy
- Lateral sweep: Horizontal movement, scanning, wind
- Tension vectors: Opposing forces creating dynamic stability
- Static equilibrium: Balanced forces, calm, stillness

Analyze the current implied energy direction and shift it to create different emotional and kinetic qualities."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Directional Energy Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === PERSPECTIVE MUTATIONS ===
    async def _mutate_local_perspective_bend(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply localized perspective distortions."""
        instructions = """BEND PERSPECTIVE LOCALLY - apply non-uniform perspective distortions.

Local perspective bend approaches:
- Fisheye zones: Bulging distortion in specific areas
- Barrel/pincushion: Curved perspective at edges
- Tilt-shift: Selective focus with perspective compression
- Multi-point perspective: Different vanishing points in different zones
- Impossible geometry: Escher-like local contradictions
- Anamorphic stretch: Elongation in specific directions
- Spherical mapping: As if wrapped around a sphere locally
- Reverse perspective: Objects get larger with distance

Analyze the current perspective and apply localized bending that creates visual interest or surreal qualities without completely breaking spatial coherence."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Local Perspective Bend",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_atmospheric_scatter_shift(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Change how light scatters through the atmosphere."""
        instructions = """SHIFT ATMOSPHERIC SCATTER - change how light diffuses and scatters.

Atmospheric scatter approaches:
- Rayleigh scatter: Blue skies, warm sunsets, color shifts with distance
- Mie scatter: Hazy, milky quality, particles in air
- Tyndall effect: Visible light beams, god rays through particles
- Clear atmosphere: Minimal scatter, sharp distant details
- Dense particle: Heavy scatter, reduced visibility, soft everything
- Chromatic scatter: Different colors scatter differently
- Volumetric density: Variable scatter in different depth zones
- Backscatter: Light bouncing back toward viewer

Analyze the current atmospheric quality and shift the scatter characteristics to create different depth, mood, and light behavior."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Atmospheric Scatter Shift",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_occlusion_pattern(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add imagined layers that partially hide parts of the scene."""
        instructions = """ADD OCCLUSION PATTERNS - introduce elements that partially hide or layer over the scene.

Occlusion pattern approaches:
- Foreground framing: Branches, windows, doorways partially obscure view
- Layered depth: Multiple translucent planes stacked
- Partial reveal: Key elements peek through occluding shapes
- Shadow occlusion: Dark areas hide detail, suggest depth
- Atmospheric layers: Fog, smoke, or haze obscure distant elements
- Geometric masks: Abstract shapes cut across the composition
- Organic overgrowth: Vines, leaves, or organic forms creep over
- Architectural screening: Lattice, screens, or grids filter view

Analyze the composition and add occluding elements that create mystery, depth, or visual intrigue through partial concealment."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Occlusion Pattern",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_opacity_fog(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Add translucent fog or haze layers."""
        instructions = """ADD OPACITY FOG - introduce translucent atmospheric layers.

Fog and haze approaches:
- Ground fog: Low-lying mist obscuring lower portions
- High haze: Upper atmosphere softening, sky blending
- Depth fog: Progressive opacity with distance
- Volumetric pockets: Localized fog volumes in specific areas
- Color fog: Tinted atmospheric layers (warm, cool, colored)
- Light fog: Fog that glows or carries light
- Morning mist: Soft, romantic, diffused atmosphere
- Industrial haze: Urban, smoky, pollution-tinged
- Mystical veil: Ethereal, magical, dreamlike opacity

Analyze the current atmosphere and add fog/haze that enhances mood, depth, or mystery."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Opacity Fog",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    # === OVERLAY/PATTERN MUTATIONS ===
    async def _mutate_pattern_overlay(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Apply a repeating pattern overlay to the style."""
        instructions = """ADD A PATTERN OVERLAY - superimpose a repeating pattern onto the style.

Pattern overlay approaches:
- Geometric grid: Regular squares, triangles, hexagons
- Organic pattern: Leaves, waves, natural forms repeating
- Halftone dots: Print-style dot patterns at various scales
- Crosshatch: Overlapping line patterns
- Textile pattern: Fabric-like weaves, knits, prints
- Digital artifacts: Scanlines, pixels, glitch patterns
- Cultural motifs: Damask, paisley, tribal, art deco
- Noise patterns: Film grain, static, organic noise

Analyze the style and choose an appropriate pattern overlay that complements or contrasts with the existing visual language."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Pattern Overlay",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_gradient_remap(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Reassign how gradients behave throughout the style."""
        instructions = """REMAP GRADIENTS - change how color and value transitions work.

Gradient remap approaches:
- Linear to radial: Convert straight gradients to circular
- Smooth to stepped: Continuous gradients become banded/posterized
- Reversed gradients: Flip the direction of existing transitions
- Multi-stop complexity: Add intermediate color stops
- Asymmetric falloff: Non-linear transition curves
- Directional change: Rotate gradient angles
- Hard edge gradients: Sharpen soft transitions
- Noise-disrupted: Add grain or distortion to gradients

Analyze the current gradient behavior (color transitions, value falloffs, blending) and remap them to create different visual dynamics."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Gradient Remap",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    async def _mutate_frame_reinterpretation(
        self,
        profile: StyleProfile,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """Reinterpret the conceptual frame or border of the image."""
        instructions = """REINTERPRET THE FRAME - change how the image boundary relates to content.

Frame reinterpretation approaches:
- Breaking the frame: Elements extend beyond or interact with edges
- Frame within frame: Nested borders, windows, screens
- Bleeding edges: Content fades or bleeds off edges
- Hard crop: Aggressive cropping that cuts into subjects
- Ornamental border: Decorative frame becomes part of style
- Frameless: No boundary acknowledgment, infinite extension implied
- Meta-frame: The frame itself becomes subject matter
- Irregular boundary: Non-rectangular, organic, or broken edges
- Vignette frame: Gradual edge treatment drawing eye inward

Analyze the current edge treatment and reinterpret how the frame functions in the composition."""
        return await self._vlm_mutate(
            profile=profile,
            image_b64=image_b64,
            mutation_type="Frame Reinterpretation",
            mutation_instructions=instructions,
            session_id=session_id,
        )

    def _summarize_profile(self, profile: StyleProfile) -> str:
        """Create a text summary of a style profile for VLM prompts."""
        parts = []

        if profile.style_name:
            parts.append(f"Style: {profile.style_name}")

        if profile.core_invariants:
            parts.append(f"Key traits: {', '.join(profile.core_invariants[:3])}")

        if profile.palette.color_descriptions:
            parts.append(f"Colors: {', '.join(profile.palette.color_descriptions[:4])}")

        if profile.palette.saturation:
            parts.append(f"Saturation: {profile.palette.saturation}")

        if profile.texture.surface:
            parts.append(f"Texture: {profile.texture.surface}")

        if profile.lighting.lighting_type:
            parts.append(f"Lighting: {profile.lighting.lighting_type}")

        if profile.line_and_shape.line_quality:
            parts.append(f"Lines: {profile.line_and_shape.line_quality}")

        if profile.line_and_shape.shape_language:
            parts.append(f"Shapes: {profile.line_and_shape.shape_language}")

        if profile.composition.framing:
            parts.append(f"Composition: {profile.composition.framing}")

        return "\n".join(parts)

    async def _vlm_mutate(
        self,
        profile: StyleProfile,
        mutation_type: str,
        mutation_instructions: str,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Generic VLM-powered mutation helper.

        All mutation strategies use this to get intelligent, context-aware mutations.
        When an image is provided, the VLM analyzes the actual visual content.

        Args:
            profile: Current style profile to mutate
            mutation_type: Name of the mutation (e.g., "Chroma Band Shift")
            mutation_instructions: Specific instructions for this mutation type
            image_b64: Optional base64 image to analyze (if provided, VLM sees the actual image)
            session_id: Optional session ID for logging

        Returns:
            (mutated_profile, mutation_description)
        """
        profile_summary = self._summarize_profile(profile)

        # If we have an image, tell the VLM to analyze it
        image_context = ""
        if image_b64:
            image_context = """
I'm showing you the actual image. Analyze what you SEE in this image - the actual colors, lighting, textures, composition, and visual elements. Base your mutation on the real visual content, not just the text description.

"""

        prompt = f"""Analyze this visual style and apply a {mutation_type} mutation.
{image_context}
Current style profile (for reference):
{profile_summary}

{mutation_instructions}

You must output ONLY valid JSON with this exact structure:
{{
    "analysis": "Brief description of what you observe in the current style relevant to this mutation",
    "mutation_applied": "Specific description of the change you're making",
    "style_changes": {{
        "palette": {{
            "dominant_colors": ["color1", "color2"],
            "accents": ["accent1"],
            "color_descriptions": ["description of colors"],
            "saturation": "low/medium/high/vibrant",
            "value_range": "description of light/dark range"
        }},
        "texture": {{
            "surface": "surface texture description",
            "noise_level": "minimal/low/medium/high",
            "special_effects": ["effect1", "effect2"]
        }},
        "lighting": {{
            "lighting_type": "type of lighting",
            "shadows": "shadow description",
            "highlights": "highlight description"
        }},
        "line_and_shape": {{
            "line_quality": "line description",
            "shape_language": "shape description",
            "geometry_notes": "geometry notes"
        }},
        "composition": {{
            "camera": "camera/viewpoint",
            "framing": "framing description",
            "negative_space_behavior": "negative space usage"
        }},
        "motifs": {{
            "recurring_elements": ["element1"],
            "forbidden_elements": ["forbidden1"]
        }}
    }}
}}

IMPORTANT:
- Only include sections and fields that need to change for this mutation
- Leave out any sections/fields that should stay the same
- Be specific and descriptive in your changes
- The mutation should be noticeable but coherent"""

        system_prompt = f"You are a style mutation expert specializing in {mutation_type}. Analyze the given style and apply intelligent, contextual mutations. Output only valid JSON."

        # Retry loop for VLM call + JSON parsing
        max_retries = 3
        last_error = None
        data = None

        for attempt in range(max_retries):
            try:
                # Use vision model if we have an image, otherwise text model
                if image_b64:
                    response = await vlm_service.analyze(
                        prompt=prompt,
                        images=[image_b64],
                        system=system_prompt,
                        force_json=True,
                        max_retries=1,  # VLM has its own retry, we handle retry at this level
                    )
                else:
                    response = await vlm_service.generate_text(
                        prompt=prompt,
                        system=system_prompt,
                        use_text_model=True,
                        force_json=True,
                    )

                # Parse response
                response = response.strip()
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if not json_match:
                    raise ValueError(f"No JSON found in VLM response")

                json_str = json_match.group(0)

                # Try to parse JSON, with fallback fixes for common VLM errors
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    # Try to fix common JSON errors from VLM
                    logger.warning(f"JSON parse error for {mutation_type}: {e}. Attempting fixes...")

                    # Fix 1: Remove trailing commas before } or ]
                    fixed = re.sub(r',(\s*[}\]])', r'\1', json_str)

                    # Fix 2: Add missing commas between values
                    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
                    fixed = re.sub(r'}\s*\n\s*"', '},\n"', fixed)
                    fixed = re.sub(r']\s*\n\s*"', '],\n"', fixed)

                    # Fix 3: Remove any non-JSON text after the closing brace
                    brace_count = 0
                    end_idx = 0
                    for i, c in enumerate(fixed):
                        if c == '{':
                            brace_count += 1
                        elif c == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    if end_idx > 0:
                        fixed = fixed[:end_idx]

                    data = json.loads(fixed)
                    logger.info(f"JSON fixed successfully for {mutation_type}")

                # Success - break out of retry loop
                break

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(f"Mutation {mutation_type} attempt {attempt + 1}/{max_retries} failed: {e}. Retrying...")
                    await asyncio.sleep(1)  # Brief pause before retry
                else:
                    logger.error(f"Mutation {mutation_type} failed after {max_retries} attempts")
                    raise ValueError(f"Mutation {mutation_type} failed after {max_retries} attempts: {e}")

        if data is None:
            raise ValueError(f"Mutation {mutation_type} failed: no valid response")

        analysis = data.get("analysis", "")
        mutation_applied = data.get("mutation_applied", mutation_type)
        # Ensure mutation_applied is a string (VLM sometimes returns dicts)
        if not isinstance(mutation_applied, str):
            mutation_applied = str(mutation_applied) if mutation_applied else mutation_type
        style_changes = data.get("style_changes", {})

        if not style_changes:
            raise ValueError(f"No style_changes in VLM response for {mutation_type}")

        # Apply changes to profile
        profile_dict = profile.model_dump()

        for section, changes in style_changes.items():
            if section in profile_dict and isinstance(changes, dict):
                for key, value in changes.items():
                    if key in profile_dict[section] and value is not None:
                        existing = profile_dict[section][key]
                        # Coerce types to match existing schema
                        if isinstance(existing, str) and not isinstance(value, str):
                            # Convert non-string to string
                            if isinstance(value, list):
                                value = ", ".join(str(v) for v in value)
                            else:
                                value = str(value)
                        elif isinstance(existing, list) and not isinstance(value, list):
                            # Convert non-list to list
                            value = [value] if value else []
                        profile_dict[section][key] = value

        # Update style name
        original_name = profile_dict.get("style_name", "Style")
        suffix = mutation_type.lower().replace(" ", "-")
        profile_dict["style_name"] = f"{original_name} ({suffix})"

        # Add mutation to core invariants
        profile_dict["core_invariants"] = [mutation_applied] + profile_dict.get("core_invariants", [])[:4]

        mutation_description = f"{mutation_type}: {mutation_applied}"

        return StyleProfile(**profile_dict), mutation_description

    async def mutate(
        self,
        profile: StyleProfile,
        strategy: MutationStrategy,
        image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str]:
        """
        Apply a mutation strategy to create a divergent style.

        Args:
            profile: The current style profile to mutate
            strategy: Which mutation strategy to use
            image_b64: The current image to analyze for mutations
            session_id: Optional session ID for WebSocket logging

        Returns:
            (mutated_profile, mutation_description)
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        await log(f"Applying mutation strategy: {strategy.value}")

        if strategy == MutationStrategy.RANDOM_DIMENSION:
            mutated, description, _ = await self._mutate_random_dimension(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.WHAT_IF:
            mutated, description = await self._mutate_what_if(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CROSSOVER:
            mutated, description = await self._mutate_crossover(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.INVERSION:
            mutated, description = await self._mutate_inversion(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.AMPLIFY:
            mutated, description = await self._mutate_amplify(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DIVERGE:
            mutated, description = await self._mutate_diverge(profile, None, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.TIME_SHIFT:
            mutated, description = await self._mutate_time_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MEDIUM_SWAP:
            mutated, description = await self._mutate_medium_swap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MOOD_SHIFT:
            mutated, description = await self._mutate_mood_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SCALE_WARP:
            mutated, description = await self._mutate_scale_warp(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DECAY:
            mutated, description = await self._mutate_decay(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.REMIX:
            mutated, description = await self._mutate_remix(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CONSTRAIN:
            mutated, description = await self._mutate_constrain(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CULTURE_SHIFT:
            mutated, description = await self._mutate_culture_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHAOS:
            mutated, description = await self._mutate_chaos(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.REFINE:
            mutated, description = await self._mutate_refine(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === SPATIAL MUTATIONS ===
        elif strategy == MutationStrategy.TOPOLOGY_FOLD:
            mutated, description = await self._mutate_topology_fold(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SILHOUETTE_SHIFT:
            mutated, description = await self._mutate_silhouette_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.PERSPECTIVE_DRIFT:
            mutated, description = await self._mutate_perspective_drift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.AXIS_SWAP:
            mutated, description = await self._mutate_axis_swap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === PHYSICS MUTATIONS ===
        elif strategy == MutationStrategy.PHYSICS_BEND:
            mutated, description = await self._mutate_physics_bend(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHROMATIC_GRAVITY:
            mutated, description = await self._mutate_chromatic_gravity(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MATERIAL_TRANSMUTE:
            mutated, description = await self._mutate_material_transmute(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.TEMPORAL_EXPOSURE:
            mutated, description = await self._mutate_temporal_exposure(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === PATTERN MUTATIONS ===
        elif strategy == MutationStrategy.MOTIF_SPLICE:
            mutated, description = await self._mutate_motif_splice(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.RHYTHM_OVERLAY:
            mutated, description = await self._mutate_rhythm_overlay(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.HARMONIC_BALANCE:
            mutated, description = await self._mutate_harmonic_balance(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SYMMETRY_BREAK:
            mutated, description = await self._mutate_symmetry_break(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === DENSITY MUTATIONS ===
        elif strategy == MutationStrategy.DENSITY_SHIFT:
            mutated, description = await self._mutate_density_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DIMENSIONAL_SHIFT:
            mutated, description = await self._mutate_dimensional_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MICRO_MACRO_SWAP:
            mutated, description = await self._mutate_micro_macro_swap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ESSENCE_STRIP:
            mutated, description = await self._mutate_essence_strip(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === NARRATIVE MUTATIONS ===
        elif strategy == MutationStrategy.NARRATIVE_RESONANCE:
            mutated, description = await self._mutate_narrative_resonance(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ARCHETYPE_MASK:
            mutated, description = await self._mutate_archetype_mask(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ANOMALY_INJECT:
            mutated, description = await self._mutate_anomaly_inject(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SPECTRAL_ECHO:
            mutated, description = await self._mutate_spectral_echo(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === ENVIRONMENT MUTATIONS ===
        elif strategy == MutationStrategy.CLIMATE_MORPH:
            mutated, description = await self._mutate_climate_morph(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.BIOME_SHIFT:
            mutated, description = await self._mutate_biome_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === TECHNICAL MUTATIONS ===
        elif strategy == MutationStrategy.ALGORITHMIC_WRINKLE:
            mutated, description = await self._mutate_algorithmic_wrinkle(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SYMBOLIC_REDUCTION:
            mutated, description = await self._mutate_symbolic_reduction(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === CHROMATIC MUTATIONS ===
        elif strategy == MutationStrategy.CHROMA_BAND_SHIFT:
            mutated, description = await self._mutate_chroma_band_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHROMATIC_NOISE:
            mutated, description = await self._mutate_chromatic_noise(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHROMATIC_TEMPERATURE_SPLIT:
            mutated, description = await self._mutate_chromatic_temperature_split(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHROMATIC_FUSE:
            mutated, description = await self._mutate_chromatic_fuse(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CHROMATIC_SPLIT:
            mutated, description = await self._mutate_chromatic_split(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === LIGHTING/SHADOW MUTATIONS ===
        elif strategy == MutationStrategy.AMBIENT_OCCLUSION_VARIANCE:
            mutated, description = await self._mutate_ambient_occlusion_variance(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SPECULAR_FLIP:
            mutated, description = await self._mutate_specular_flip(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.BLOOM_VARIANCE:
            mutated, description = await self._mutate_bloom_variance(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DESYNC_LIGHTING_CHANNELS:
            mutated, description = await self._mutate_desync_lighting_channels(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.HIGHLIGHT_SHIFT:
            mutated, description = await self._mutate_highlight_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SHADOW_RECODE:
            mutated, description = await self._mutate_shadow_recode(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.LIGHTING_ANGLE_SHIFT:
            mutated, description = await self._mutate_lighting_angle_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.HIGHLIGHT_BLOOM_COLORIZE:
            mutated, description = await self._mutate_highlight_bloom_colorize(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MICRO_SHADOWING:
            mutated, description = await self._mutate_micro_shadowing(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MACRO_SHADOW_PIVOT:
            mutated, description = await self._mutate_macro_shadow_pivot(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === CONTOUR/EDGE MUTATIONS ===
        elif strategy == MutationStrategy.CONTOUR_SIMPLIFY:
            mutated, description = await self._mutate_contour_simplify(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CONTOUR_COMPLEXIFY:
            mutated, description = await self._mutate_contour_complexify(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.LINE_WEIGHT_MODULATION:
            mutated, description = await self._mutate_line_weight_modulation(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.EDGE_BEHAVIOR_SWAP:
            mutated, description = await self._mutate_edge_behavior_swap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.BOUNDARY_ECHO:
            mutated, description = await self._mutate_boundary_echo(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.HALO_GENERATION:
            mutated, description = await self._mutate_halo_generation(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === TEXTURE MUTATIONS ===
        elif strategy == MutationStrategy.TEXTURE_DIRECTION_SHIFT:
            mutated, description = await self._mutate_texture_direction_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.NOISE_INJECTION:
            mutated, description = await self._mutate_noise_injection(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MICROFRACTURE_PATTERN:
            mutated, description = await self._mutate_microfracture_pattern(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CROSSHATCH_DENSITY_SHIFT:
            mutated, description = await self._mutate_crosshatch_density_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === MATERIAL/SURFACE MUTATIONS ===
        elif strategy == MutationStrategy.BACKGROUND_MATERIAL_SWAP:
            mutated, description = await self._mutate_background_material_swap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SURFACE_MATERIAL_SHIFT:
            mutated, description = await self._mutate_surface_material_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.TRANSLUCENCY_SHIFT:
            mutated, description = await self._mutate_translucency_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SUBSURFACE_SCATTER_TWEAK:
            mutated, description = await self._mutate_subsurface_scatter_tweak(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ANISOTROPY_SHIFT:
            mutated, description = await self._mutate_anisotropy_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.REFLECTIVITY_SHIFT:
            mutated, description = await self._mutate_reflectivity_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === TONAL MUTATIONS ===
        elif strategy == MutationStrategy.MIDTONE_SHIFT:
            mutated, description = await self._mutate_midtone_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.TONAL_COMPRESSION:
            mutated, description = await self._mutate_tonal_compression(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.TONAL_EXPANSION:
            mutated, description = await self._mutate_tonal_expansion(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MICROCONTRAST_TUNING:
            mutated, description = await self._mutate_microcontrast_tuning(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.CONTRAST_CHANNEL_SWAP:
            mutated, description = await self._mutate_contrast_channel_swap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === BLUR/FOCUS MUTATIONS ===
        elif strategy == MutationStrategy.DIRECTIONAL_BLUR:
            mutated, description = await self._mutate_directional_blur(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.FOCAL_PLANE_SHIFT:
            mutated, description = await self._mutate_focal_plane_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MASK_BOUNDARY_MUTATION:
            mutated, description = await self._mutate_mask_boundary_mutation(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === SILHOUETTE MUTATIONS (EXTENDED) ===
        elif strategy == MutationStrategy.SILHOUETTE_MERGE:
            mutated, description = await self._mutate_silhouette_merge(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SILHOUETTE_SUBTRACT:
            mutated, description = await self._mutate_silhouette_subtract(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SILHOUETTE_DISTORTION:
            mutated, description = await self._mutate_silhouette_distortion(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.INTERNAL_GEOMETRY_TWIST:
            mutated, description = await self._mutate_internal_geometry_twist(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === DEPTH MUTATIONS ===
        elif strategy == MutationStrategy.BACKGROUND_DEPTH_COLLAPSE:
            mutated, description = await self._mutate_background_depth_collapse(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DEPTH_FLATTENING:
            mutated, description = await self._mutate_depth_flattening(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DEPTH_EXPANSION:
            mutated, description = await self._mutate_depth_expansion(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === COMPOSITION MUTATIONS (NEW) ===
        elif strategy == MutationStrategy.QUADRANT_MUTATION:
            mutated, description = await self._mutate_quadrant_mutation(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.OBJECT_ALIGNMENT_SHIFT:
            mutated, description = await self._mutate_object_alignment_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SPATIAL_HIERARCHY_FLIP:
            mutated, description = await self._mutate_spatial_hierarchy_flip(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.BALANCE_SHIFT:
            mutated, description = await self._mutate_balance_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.INTERPLAY_SWAP:
            mutated, description = await self._mutate_interplay_swap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.VIGNETTE_MODIFICATION:
            mutated, description = await self._mutate_vignette_modification(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === MOTIF MUTATIONS (NEW) ===
        elif strategy == MutationStrategy.MOTIF_MIRRORING:
            mutated, description = await self._mutate_motif_mirroring(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MOTIF_SCALING:
            mutated, description = await self._mutate_motif_scaling(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.MOTIF_REPETITION:
            mutated, description = await self._mutate_motif_repetition(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === COLOR ROLE MUTATIONS ===
        elif strategy == MutationStrategy.COLOR_ROLE_REASSIGNMENT:
            mutated, description = await self._mutate_color_role_reassignment(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.SATURATION_SCALPEL:
            mutated, description = await self._mutate_saturation_scalpel(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.NEGATIVE_COLOR_INJECTION:
            mutated, description = await self._mutate_negative_color_injection(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.AMBIENT_COLOR_SUCTION:
            mutated, description = await self._mutate_ambient_color_suction(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.LOCAL_COLOR_MUTATION:
            mutated, description = await self._mutate_local_color_mutation(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === DETAIL/FORM MUTATIONS ===
        elif strategy == MutationStrategy.DETAIL_DENSITY_SHIFT:
            mutated, description = await self._mutate_detail_density_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.FORM_SIMPLIFICATION:
            mutated, description = await self._mutate_form_simplification(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.FORM_COMPLICATION:
            mutated, description = await self._mutate_form_complication(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.PROPORTION_SHIFT:
            mutated, description = await self._mutate_proportion_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === FLOW/RHYTHM MUTATIONS ===
        elif strategy == MutationStrategy.PATH_FLOW_SHIFT:
            mutated, description = await self._mutate_path_flow_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.RHYTHM_DISRUPTION:
            mutated, description = await self._mutate_rhythm_disruption(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.RHYTHM_REBALANCE:
            mutated, description = await self._mutate_rhythm_rebalance(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.DIRECTIONAL_ENERGY_SHIFT:
            mutated, description = await self._mutate_directional_energy_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === PERSPECTIVE MUTATIONS ===
        elif strategy == MutationStrategy.LOCAL_PERSPECTIVE_BEND:
            mutated, description = await self._mutate_local_perspective_bend(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.ATMOSPHERIC_SCATTER_SHIFT:
            mutated, description = await self._mutate_atmospheric_scatter_shift(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.OCCLUSION_PATTERN:
            mutated, description = await self._mutate_occlusion_pattern(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.OPACITY_FOG:
            mutated, description = await self._mutate_opacity_fog(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        # === OVERLAY/PATTERN MUTATIONS ===
        elif strategy == MutationStrategy.PATTERN_OVERLAY:
            mutated, description = await self._mutate_pattern_overlay(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.GRADIENT_REMAP:
            mutated, description = await self._mutate_gradient_remap(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        elif strategy == MutationStrategy.FRAME_REINTERPRETATION:
            mutated, description = await self._mutate_frame_reinterpretation(profile, image_b64, session_id)
            await log(f"Mutation: {description}")
            return mutated, description

        else:
            raise ValueError(f"Unknown mutation strategy: {strategy}")

    def _build_exploration_prompt(
        self,
        profile: StyleProfile,
        subject: str,
    ) -> str:
        """
        Build a prompt from the mutated style profile.
        Uses mechanical assembly for predictability.
        """
        # Build style descriptors
        style_parts = []

        # Core invariants (mutation markers)
        if profile.core_invariants:
            style_parts.extend(profile.core_invariants[:3])

        # Palette
        if profile.palette.color_descriptions:
            colors = ", ".join(profile.palette.color_descriptions[:4])
            style_parts.append(f"color palette of {colors}")
        if profile.palette.saturation:
            style_parts.append(f"{profile.palette.saturation} saturation")

        # Texture
        if profile.texture.surface:
            style_parts.append(profile.texture.surface)
        if profile.texture.noise_level and profile.texture.noise_level != "medium":
            style_parts.append(f"{profile.texture.noise_level} noise/grain")

        # Lighting
        if profile.lighting.lighting_type:
            style_parts.append(profile.lighting.lighting_type)
        if profile.lighting.shadows:
            style_parts.append(profile.lighting.shadows)

        # Line and shape
        if profile.line_and_shape.line_quality:
            style_parts.append(profile.line_and_shape.line_quality)
        if profile.line_and_shape.shape_language:
            style_parts.append(profile.line_and_shape.shape_language)

        # Composition
        if profile.composition.framing:
            style_parts.append(profile.composition.framing)

        # Combine with subject
        style_desc = ", ".join(style_parts)
        return f"{subject}. {style_desc}"

    async def generate_exploration_image(
        self,
        profile: StyleProfile,
        subject: str,
        parent_image_b64: str | None = None,
        session_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Generate an image from a mutated style profile.

        Args:
            profile: The mutated style profile
            subject: What to generate (fallback if no image)
            parent_image_b64: The parent image to analyze for prompt generation
            session_id: Optional session ID for logging

        Returns:
            (image_b64, prompt_used)
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        # Generate prompt by combining detailed image description with mutated style
        if parent_image_b64:
            await log("Analyzing parent image...")

            # Step 1: Get rich description of the image
            analysis_prompt = """Analyze this image comprehensively in 400-500 words as flowing prose.

Describe the main subjects, characters, and objects with their appearance, position, and distinctive details. Cover the composition including layout, framing, and spatial arrangement. Note the artistic style, technique, and medium. Detail the color palette with dominant colors, relationships, and temperature. Describe the lighting including sources, shadows, highlights, and mood it creates. Mention visible textures and surface qualities. Convey the emotional tone and atmosphere.

Write as one continuous flowing description - do NOT use bullet points, numbered lists, or section headers. Be specific and detailed."""

            base_description = await vlm_service.analyze(
                prompt=analysis_prompt,
                images=[parent_image_b64],
                system="You are an expert at describing images for AI image generation. Write detailed, evocative descriptions.",
                force_json=False,
            )
            base_description = base_description.strip()
            await log(f"Base description: {base_description[:150]}...")

            # Step 2: Build style modifiers from the MUTATED profile
            style_modifiers = []

            if profile.palette:
                p = profile.palette
                if p.dominant_colors:
                    style_modifiers.append(f"color palette of {p.dominant_colors}")
                if p.color_mood:
                    style_modifiers.append(f"{p.color_mood} color mood")
                if p.saturation_level:
                    style_modifiers.append(f"{p.saturation_level} saturation")

            if profile.texture:
                t = profile.texture
                if t.surface_quality:
                    style_modifiers.append(f"{t.surface_quality} surfaces")
                if t.noise_characteristics:
                    style_modifiers.append(f"{t.noise_characteristics} texture")

            if profile.lighting:
                l = profile.lighting
                if l.light_source:
                    style_modifiers.append(f"{l.light_source} lighting")
                if l.shadow_style:
                    style_modifiers.append(f"{l.shadow_style} shadows")
                if l.contrast_level:
                    style_modifiers.append(f"{l.contrast_level} contrast")

            if profile.line_and_shape:
                ls = profile.line_and_shape
                if ls.edge_treatment:
                    style_modifiers.append(f"{ls.edge_treatment} edges")
                if ls.shape_language:
                    style_modifiers.append(f"{ls.shape_language} shapes")

            # Step 3: Append style modifiers to the base description
            if style_modifiers:
                style_suffix = ", ".join(style_modifiers)
                prompt = f"{base_description} Style emphasis: {style_suffix}."
                await log(f"Added style modifiers: {style_suffix[:100]}...")
            else:
                prompt = base_description
        else:
            # Fallback to mechanical prompt building
            await log("No parent image, using fallback prompt building")
            prompt = self._build_exploration_prompt(profile, subject)

        await log(f"FULL PROMPT: {prompt[:200]}...", "warning")

        # Generate image
        image_b64 = await comfyui_service.generate(
            prompt=prompt,
            session_id=session_id,
        )

        await log("Exploration image generated", "success")
        return image_b64, prompt

    async def score_exploration(
        self,
        parent_image_b64: str | None,
        child_image_b64: str,
        mutation_description: str,
        session_id: str | None = None,
    ) -> ExplorationScores:
        """
        Score an exploration snapshot on novelty, coherence, and interest.

        Args:
            parent_image_b64: The parent image (None if this is root/first)
            child_image_b64: The newly generated image
            mutation_description: Description of the mutation applied
            session_id: Optional session ID for logging

        Returns:
            ExplorationScores with all three dimensions and combined score
        """
        import re

        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        await log("Scoring exploration (novelty, coherence, interest)...")

        # Default scores
        novelty = 50.0
        coherence = 70.0
        interest = 60.0

        # === NOVELTY SCORING ===
        # How different is this from the parent?
        if parent_image_b64:
            novelty_prompt = """Compare these two images and score from 0-100 how DIFFERENT the second image's visual style is from the first.

0 = Identical style (same colors, lighting, texture, composition)
25 = Minor variations (slightly different but clearly same style)
50 = Noticeably different (some shared elements but distinct feel)
75 = Very different (few similarities, transformed appearance)
100 = Completely transformed (unrecognizable as related)

Focus on STYLE differences, not subject matter. Look at:
- Color palette and saturation
- Lighting quality and direction
- Texture and surface treatment
- Composition and framing
- Overall mood and atmosphere

Output ONLY a JSON object: {"novelty_score": <number>}"""

            try:
                response = await vlm_service.analyze(
                    prompt=novelty_prompt,
                    images=[parent_image_b64, child_image_b64],
                    max_retries=2,
                )

                response = response.strip()
                if response.startswith("{"):
                    data = json.loads(response)
                    novelty = float(data.get("novelty_score", 50))
                else:
                    match = re.search(r'(\d+)', response)
                    if match:
                        novelty = float(match.group(1))

                novelty = max(0, min(100, novelty))
                await log(f"Novelty score: {novelty:.1f}", "success")

            except Exception as e:
                await log(f"Novelty scoring failed: {e}", "warning")
                novelty = random.uniform(45, 75)
        else:
            await log("First snapshot - baseline novelty = 0", "info")
            novelty = 0

        # === COHERENCE SCORING ===
        # Is this a valid, consistent style (not random noise)?
        coherence_prompt = """Analyze this image and score from 0-100 how COHERENT its visual style is.

A coherent style means:
- Consistent color palette throughout
- Unified lighting approach
- Consistent texture/surface treatment
- Elements work together harmoniously
- Intentional artistic choices are evident

0 = Random noise, no consistent style, chaotic mess
25 = Some style elements but very inconsistent
50 = Moderately coherent, some unity but rough edges
75 = Strong coherence, clear intentional style
100 = Perfect coherence, masterfully unified style

Output ONLY a JSON object: {"coherence_score": <number>}"""

        try:
            response = await vlm_service.analyze(
                prompt=coherence_prompt,
                images=[child_image_b64],
                max_retries=2,
            )

            response = response.strip()
            if response.startswith("{"):
                data = json.loads(response)
                coherence = float(data.get("coherence_score", 70))
            else:
                match = re.search(r'(\d+)', response)
                if match:
                    coherence = float(match.group(1))

            coherence = max(0, min(100, coherence))
            await log(f"Coherence score: {coherence:.1f}", "success")

        except Exception as e:
            await log(f"Coherence scoring failed: {e}", "warning")
            coherence = random.uniform(60, 80)

        # === INTEREST SCORING ===
        # Is this visually striking and compelling?
        interest_prompt = """Score this image from 0-100 on visual INTEREST and aesthetic appeal.

Consider:
- Is it visually striking or memorable?
- Does it evoke an emotional response?
- Is there something unique or surprising about it?
- Would someone stop scrolling to look at this?
- Does it have artistic merit?

0 = Boring, generic, forgettable, no appeal
25 = Mildly interesting, some visual merit
50 = Moderately interesting, decent aesthetic
75 = Very interesting, visually compelling
100 = Stunning, unforgettable, would stop anyone in their tracks

Output ONLY a JSON object: {"interest_score": <number>}"""

        try:
            response = await vlm_service.analyze(
                prompt=interest_prompt,
                images=[child_image_b64],
                max_retries=2,
            )

            response = response.strip()
            if response.startswith("{"):
                data = json.loads(response)
                interest = float(data.get("interest_score", 60))
            else:
                match = re.search(r'(\d+)', response)
                if match:
                    interest = float(match.group(1))

            interest = max(0, min(100, interest))
            await log(f"Interest score: {interest:.1f}", "success")

        except Exception as e:
            await log(f"Interest scoring failed: {e}", "warning")
            interest = random.uniform(50, 70)

        # === COMBINED SCORE ===
        # Weighted combination: novelty and interest matter most, coherence is sanity check
        combined = (novelty * 0.4) + (interest * 0.4) + (coherence * 0.2)

        await log(f"Final scores - Novelty: {novelty:.1f}, Coherence: {coherence:.1f}, Interest: {interest:.1f}, Combined: {combined:.1f}")

        return ExplorationScores(
            novelty=novelty,
            coherence=coherence,
            interest=interest,
            combined=combined,
        )

    async def explore_step(
        self,
        current_profile: StyleProfile,
        parent_image_b64: str | None,
        subject: str,
        strategy: MutationStrategy | None = None,
        preferred_strategies: list[MutationStrategy] | None = None,
        session_id: str | None = None,
    ) -> tuple[StyleProfile, str, str, str, ExplorationScores, MutationStrategy]:
        """
        Run one complete exploration step.

        This is the main entry point that:
        1. Applies a mutation to the profile
        2. Generates an image from the mutated profile
        3. Scores the exploration

        Args:
            current_profile: The style profile to mutate from
            parent_image_b64: Parent image for comparison (None if first)
            subject: What to generate
            strategy: Specific strategy to use, or None for random
            preferred_strategies: List of strategies to choose from
            session_id: Optional session ID for logging

        Returns:
            (mutated_profile, mutation_description, image_b64, prompt_used, scores, strategy_used)
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[explorer] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "explore")

        await log("Starting exploration step...")

        # Select strategy
        if strategy is None:
            if preferred_strategies:
                strategy = random.choice(preferred_strategies)
            else:
                strategy = MutationStrategy.RANDOM_DIMENSION

        await log(f"Selected strategy: {strategy.value}")

        # Step 1: Mutate the profile (pass image so VLM can analyze it)
        mutated_profile, mutation_description = await self.mutate(
            profile=current_profile,
            strategy=strategy,
            image_b64=parent_image_b64,
            session_id=session_id,
        )

        # Step 2: Generate image (pass parent image for VLM analysis)
        image_b64, prompt_used = await self.generate_exploration_image(
            profile=mutated_profile,
            subject=subject,
            parent_image_b64=parent_image_b64,
            session_id=session_id,
        )

        # Step 3: Score the exploration
        scores = await self.score_exploration(
            parent_image_b64=parent_image_b64,
            child_image_b64=image_b64,
            mutation_description=mutation_description,
            session_id=session_id,
        )

        await log(f"Exploration step complete. Novelty: {scores.novelty:.1f}", "success")

        return mutated_profile, mutation_description, image_b64, prompt_used, scores, strategy


# Singleton instance
style_explorer = StyleExplorer()
