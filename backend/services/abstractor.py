import json
import logging
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.models.schemas import StyleProfile

logger = logging.getLogger(__name__)


class StyleAbstractor:
    def __init__(self):
        self.prompt_path = Path(__file__).parent.parent / "prompts" / "abstractor.md"

    def _load_prompt(self) -> str:
        """Load the abstractor prompt template."""
        if self.prompt_path.exists():
            return self.prompt_path.read_text()
        raise FileNotFoundError(f"Abstractor prompt not found at {self.prompt_path}")

    async def abstract_style_profile(self, profile: StyleProfile) -> StyleProfile:
        """
        Remove subject-specific references from a style profile using VLM.

        This converts subject-specific descriptions like:
        - "Bright highlights on its mane" → "Bright highlights on elevated features"
        - "The lion's pose is framed" → "The central subject is framed"

        Args:
            profile: StyleProfile with subject-specific descriptions

        Returns:
            StyleProfile with abstracted, subject-agnostic descriptions
        """
        system_prompt = self._load_prompt()
        profile_json = json.dumps(profile.model_dump(), indent=2)

        user_prompt = f"""Abstract this style profile to remove ALL subject-specific references:

```json
{profile_json}
```

Return the abstracted JSON with the same structure."""

        logger.info("[abstractor] Sending profile to VLM for abstraction...")

        try:
            response = await vlm_service.generate_text(
                prompt=user_prompt,
                system=system_prompt,
                force_json=True,  # We need valid JSON output
            )

            # Clean response
            response = response.strip()

            # Remove markdown code blocks if present
            if response.startswith("```"):
                lines = response.split("\n")
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            # Parse JSON
            abstracted_dict = json.loads(response)

            # Validate by reconstructing StyleProfile
            abstracted_profile = StyleProfile(**abstracted_dict)

            logger.info("[abstractor] Successfully abstracted style profile")
            return abstracted_profile

        except json.JSONDecodeError as e:
            logger.error(f"[abstractor] Failed to parse VLM response as JSON: {e}")
            logger.error(f"[abstractor] Response was: {response[:500]}")
            # Fall back to original profile
            logger.warning("[abstractor] Falling back to original profile")
            return profile

        except Exception as e:
            logger.error(f"[abstractor] Abstraction failed: {e}")
            # Fall back to original profile
            logger.warning("[abstractor] Falling back to original profile")
            return profile


style_abstractor = StyleAbstractor()
