import json
import logging
from pathlib import Path

from backend.services.vlm import vlm_service
from backend.models.schemas import StyleProfile
from backend.websocket import manager

logger = logging.getLogger(__name__)


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

## TRAINING FEEDBACK (CRITICAL - LEARN FROM THIS):
{{FEEDBACK_HISTORY}}

## TRAITS TO EMPHASIZE (frequently lost in past iterations):
{{EMPHASIZE_TRAITS}}

## TRAITS THAT WORK WELL (preserved in approved iterations):
{{PRESERVE_TRAITS}}

## YOUR RULES:
1. Every prompt you write MUST express the core invariants
2. PRIORITIZE traits that were frequently lost - be MORE EXPLICIT about them
3. Avoid approaches that led to rejections (see feedback notes)
4. Use explicit color language based on the palette (mention specific tones, not just "colorful")
5. Describe lighting setup explicitly (direction, quality, color temperature)
6. Include texture and surface quality descriptions
7. Respect forbidden_elements - NEVER include them
8. You may naturally incorporate recurring_elements where appropriate
9. Write prompts suitable for Stable Diffusion / Flux style models
10. Be detailed but not verbose - aim for 50-150 words

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
            feedback_history: List of past feedback items with approval status and critique data

        Returns:
            Complete system prompt string
        """
        from collections import Counter

        template = self._load_prompt()

        # Format core invariants
        invariants_text = "\n".join(
            f"- {inv}" for inv in style_profile.core_invariants
        )

        # Process feedback history to extract learnings
        feedback_lines = []
        all_lost_traits = []
        all_preserved_traits = []
        rejected_notes = []

        if feedback_history:
            for f in feedback_history[-10:]:  # Last 10 entries
                iteration = f.get('iteration', '?')
                approved = f.get('approved')
                notes = f.get('notes', '')

                # Build feedback line
                status = "✓ APPROVED" if approved else "✗ REJECTED" if approved == False else "pending"
                line = f"- Iteration {iteration} [{status}]"
                if notes:
                    line += f": {notes}"
                feedback_lines.append(line)

                # Collect traits
                if f.get('lost_traits'):
                    all_lost_traits.extend(f['lost_traits'])
                if f.get('preserved_traits'):
                    if approved:  # Only count preserved from approved iterations
                        all_preserved_traits.extend(f['preserved_traits'])

                # Collect rejection notes for learning
                if approved == False and notes:
                    rejected_notes.append(notes)

            feedback_text = "\n".join(feedback_lines)

            # Find frequently lost traits (need emphasis)
            lost_counts = Counter(all_lost_traits)
            emphasize_traits = [
                f"- {trait} (lost {count}x)"
                for trait, count in lost_counts.most_common(8)
            ]

            # Find consistently preserved traits (what works)
            preserved_counts = Counter(all_preserved_traits)
            preserve_traits = [
                f"- {trait}"
                for trait, count in preserved_counts.most_common(5)
            ]

            # Add rejection learnings to feedback
            if rejected_notes:
                feedback_text += "\n\n### Rejected iteration notes (AVOID these issues):\n"
                feedback_text += "\n".join(f"- {note}" for note in rejected_notes[-3:])

        else:
            feedback_text = "No feedback yet - this is the first iteration."
            emphasize_traits = []
            preserve_traits = []

        emphasize_text = "\n".join(emphasize_traits) if emphasize_traits else "None identified yet."
        preserve_text = "\n".join(preserve_traits) if preserve_traits else "None identified yet."

        return template.replace(
            "{{STYLE_NAME}}", style_profile.style_name
        ).replace(
            "{{CORE_INVARIANTS}}", invariants_text
        ).replace(
            "{{STYLE_PROFILE}}", json.dumps(style_profile.model_dump(), indent=2)
        ).replace(
            "{{FEEDBACK_HISTORY}}", feedback_text
        ).replace(
            "{{EMPHASIZE_TRAITS}}", emphasize_text
        ).replace(
            "{{PRESERVE_TRAITS}}", preserve_text
        )

    async def generate_image_prompt(
        self,
        style_profile: StyleProfile,
        subject: str,
        feedback_history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> str:
        """
        Generate an image prompt for the given subject in the style.

        Args:
            style_profile: The style to embody
            subject: What to generate (e.g., "a fox sleeping under a tree")
            feedback_history: Past feedback to inform generation
            session_id: Optional session ID for WebSocket logging

        Returns:
            Image generation prompt string
        """
        async def log(msg: str, level: str = "info"):
            logger.info(f"[agent] {msg}")
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "prompt")

        await log(f"Building style agent prompt for: {style_profile.style_name}")
        system_prompt = self.build_system_prompt(style_profile, feedback_history)
        await log(f"System prompt ready ({len(system_prompt)} chars)")

        user_prompt = f"""Generate an image prompt for this subject:

Subject: {subject}

Remember:
- Embody the style profile completely
- Be specific about colors, lighting, and texture
- Write a single, detailed prompt ready for image generation"""

        await log("Sending to VLM for prompt generation...")
        try:
            response = await vlm_service.generate_text(
                prompt=user_prompt,
                system=system_prompt,
                request_id=session_id,  # Use session_id as request_id for cancellation
            )
            await log(f"VLM response received ({len(response)} chars)", "success")
        except Exception as e:
            await log(f"VLM prompt generation failed: {e}", "error")
            raise

        # Clean up response - remove any markdown or extra formatting
        response = response.strip()
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        cleaned = response.strip()
        await log(f"Cleaned prompt: {cleaned[:100]}...")
        return cleaned


style_agent = StyleAgent()
