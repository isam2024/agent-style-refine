import json
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.models.schemas import StyleProfile


class StyleAgent:
    def __init__(self):
        self.prompt_path = Path(__file__).parent.parent / "prompts" / "generator.md"

    def _load_prompt(self) -> str:
        """Load the generator prompt template."""
        if self.prompt_path.exists():
            return self.prompt_path.read_text()
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        return """You are the STYLE AGENT "{{STYLE_NAME}}".

Your role is to write detailed image generation prompts that perfectly embody a specific visual style. You must NEVER deviate from the core style characteristics.

## CORE INVARIANTS (MUST PRESERVE):
{{CORE_INVARIANTS}}

## FULL STYLE PROFILE:
```json
{{STYLE_PROFILE}}
```

## FEEDBACK HISTORY:
{{FEEDBACK_HISTORY}}

## YOUR RULES:
1. Every prompt you write MUST express the core invariants
2. Use explicit color language based on the palette (mention specific tones, not just "colorful")
3. Describe lighting setup explicitly (direction, quality, color temperature)
4. Include texture and surface quality descriptions
5. Respect forbidden_elements - NEVER include them
6. You may naturally incorporate recurring_elements where appropriate
7. Write prompts suitable for Stable Diffusion / Flux style models
8. Be detailed but not verbose - aim for 50-150 words

## OUTPUT FORMAT:
When given a subject, respond with ONLY the image generation prompt. No explanation, no markdown, just the prompt text."""

    def build_system_prompt(
        self,
        style_profile: StyleProfile,
        feedback_history: list[dict] | None = None,
    ) -> str:
        """
        Build the system prompt for the style agent.

        Args:
            style_profile: The current style profile
            feedback_history: List of past feedback items

        Returns:
            Complete system prompt string
        """
        template = self._load_prompt()

        # Format core invariants
        invariants_text = "\n".join(
            f"- {inv}" for inv in style_profile.core_invariants
        )

        # Format feedback history
        if feedback_history:
            feedback_text = "\n".join(
                f"- Iteration {f.get('iteration', '?')}: {f.get('notes', 'No notes')}"
                for f in feedback_history[-5:]  # Last 5 feedback items
            )
        else:
            feedback_text = "No feedback yet."

        return template.replace(
            "{{STYLE_NAME}}", style_profile.style_name
        ).replace(
            "{{CORE_INVARIANTS}}", invariants_text
        ).replace(
            "{{STYLE_PROFILE}}", json.dumps(style_profile.model_dump(), indent=2)
        ).replace(
            "{{FEEDBACK_HISTORY}}", feedback_text
        )

    async def generate_image_prompt(
        self,
        style_profile: StyleProfile,
        subject: str,
        feedback_history: list[dict] | None = None,
    ) -> str:
        """
        Generate an image prompt for the given subject in the style.

        Args:
            style_profile: The style to embody
            subject: What to generate (e.g., "a fox sleeping under a tree")
            feedback_history: Past feedback to inform generation

        Returns:
            Image generation prompt string
        """
        system_prompt = self.build_system_prompt(style_profile, feedback_history)

        user_prompt = f"""Generate an image prompt for this subject:

Subject: {subject}

Remember:
- Embody the style profile completely
- Be specific about colors, lighting, and texture
- Write a single, detailed prompt ready for image generation"""

        response = await vlm_service.generate_text(
            prompt=user_prompt,
            system=system_prompt,
        )

        # Clean up response - remove any markdown or extra formatting
        response = response.strip()
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        return response.strip()


style_agent = StyleAgent()
