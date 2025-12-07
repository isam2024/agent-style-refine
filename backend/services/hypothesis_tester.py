"""
Hypothesis testing service.

Tests style hypotheses by generating images and scoring consistency.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from backend.services.vlm import vlm_service
from backend.services.comfyui import comfyui_service
from backend.services.agent import build_style_agent_prompt
from backend.services.storage import storage_service
from backend.models.hypothesis_models import (
    StyleHypothesis,
    HypothesisTest,
)
from backend.websocket import manager

logger = logging.getLogger(__name__)


class HypothesisTester:
    """Tests hypotheses by generating samples and scoring consistency."""

    def __init__(self):
        self.prompt_path = (
            Path(__file__).parent.parent / "prompts" / "hypothesis_tester.md"
        )

    def _load_prompt(self) -> str:
        """Load the hypothesis testing prompt template."""
        if self.prompt_path.exists():
            return self.prompt_path.read_text()
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Fallback prompt if file doesn't exist."""
        return """Compare the test image to the original reference.

Score visual_consistency (0-100) and subject_independence (0-100).

Output JSON:
{
  "scores": {"visual_consistency": 85, "subject_independence": 78},
  "preserved_well": ["aspect 1", "aspect 2"],
  "drifted_aspects": ["aspect 1", "aspect 2"],
  "evaluation_notes": "explanation"
}
"""

    async def test_hypothesis(
        self,
        hypothesis: StyleHypothesis,
        original_image_b64: str,
        test_subjects: list[str],
        session_id: str,
    ) -> StyleHypothesis:
        """
        Test a hypothesis by generating images and scoring consistency.

        Args:
            hypothesis: The hypothesis to test
            original_image_b64: Base64 original reference image
            test_subjects: List of subjects to test with
            session_id: Session ID for logging and file storage

        Returns:
            Updated hypothesis with test results and new confidence score
        """

        async def log(msg: str, level: str = "info"):
            logger.info(msg)
            await manager.broadcast_log(session_id, msg, level, "hypothesis_test")

        await log(f"Testing hypothesis: {hypothesis.interpretation}")
        await log(f"Running {len(test_subjects)} test generations...")

        test_results = []
        total_consistency = 0.0
        total_independence = 0.0

        for idx, test_subject in enumerate(test_subjects):
            await log(f"Test {idx + 1}/{len(test_subjects)}: {test_subject}")

            try:
                # Generate test image using this hypothesis's style profile
                await log(f"  Generating image...")

                # Build style agent prompt from hypothesis profile
                system_prompt = build_style_agent_prompt(
                    style_profile=hypothesis.profile,
                    feedback_history=[],  # No feedback for hypothesis testing
                )

                # Get image generation prompt from VLM
                generation_prompt = f"""You are a style agent. Generate an image prompt for: {test_subject}

Apply the style profile while depicting this subject.

Output ONLY the image generation prompt (one paragraph, 40-80 words).
"""

                image_prompt = await vlm_service.analyze(
                    prompt=f"{system_prompt}\n\n{generation_prompt}",
                    images=None,
                    max_retries=1,
                )

                await log(f"  Prompt: {image_prompt[:80]}...")

                # Generate image
                generated_b64 = await comfyui_service.generate(
                    prompt=image_prompt.strip(),
                    session_id=session_id,
                )

                # Save test image
                session_dir = storage_service.get_session_dir(session_id)
                test_dir = session_dir / "hypothesis_tests"
                test_dir.mkdir(exist_ok=True)

                test_filename = f"{hypothesis.id[:8]}_{idx + 1}_{test_subject.replace(' ', '_')}.png"
                test_path = await storage_service.save_image(
                    session_id=session_id,
                    image_b64=generated_b64,
                    filename=f"hypothesis_tests/{test_filename}",
                )

                await log(f"  Test image saved: {test_path.name}", "success")

                # Score consistency using VLM
                await log(f"  Scoring consistency...")

                scoring_prompt = self._load_prompt()
                scoring_prompt += f"\n\n**Test Subject:** {test_subject}\n"

                score_response = await vlm_service.analyze(
                    prompt=scoring_prompt,
                    images=[original_image_b64, generated_b64],
                    max_retries=2,
                )

                # Parse scores
                try:
                    scores_data = self._parse_json_response(score_response)

                    visual_consistency = scores_data.get("scores", {}).get(
                        "visual_consistency", 50
                    )
                    subject_independence = scores_data.get("scores", {}).get(
                        "subject_independence", 50
                    )

                    await log(
                        f"  Scores: consistency={visual_consistency}, "
                        f"independence={subject_independence}",
                        "success",
                    )

                    # Create test result
                    test_result = HypothesisTest(
                        test_subject=test_subject,
                        generated_image_path=str(test_path),
                        scores={
                            "visual_consistency": float(visual_consistency),
                            "subject_independence": float(subject_independence),
                        },
                        timestamp=datetime.utcnow(),
                    )

                    test_results.append(test_result)
                    total_consistency += visual_consistency
                    total_independence += subject_independence

                except Exception as e:
                    await log(f"  Failed to parse scores: {e}", "error")
                    # Create test result with default scores
                    test_result = HypothesisTest(
                        test_subject=test_subject,
                        generated_image_path=str(test_path),
                        scores={
                            "visual_consistency": 50.0,
                            "subject_independence": 50.0,
                        },
                        timestamp=datetime.utcnow(),
                    )
                    test_results.append(test_result)
                    total_consistency += 50
                    total_independence += 50

            except Exception as e:
                await log(f"  Test failed: {e}", "error")
                # Continue with other tests even if one fails

        if not test_results:
            await log("All tests failed", "error")
            raise RuntimeError(f"All tests failed for hypothesis: {hypothesis.interpretation}")

        # Calculate new confidence based on test results
        avg_consistency = total_consistency / len(test_results)
        avg_independence = total_independence / len(test_results)

        # Confidence = weighted average of scores, normalized to 0.0-1.0
        # Weight consistency higher (0.6) than independence (0.4)
        confidence = (avg_consistency * 0.6 + avg_independence * 0.4) / 100.0

        await log(
            f"Testing complete: {len(test_results)} tests, confidence={confidence:.2f}",
            "success",
        )

        # Update hypothesis with results
        hypothesis.test_results = test_results
        hypothesis.confidence = confidence

        return hypothesis

    def _parse_json_response(self, response: str) -> dict:
        """Extract JSON from VLM response."""
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

        raise ValueError(f"Cannot parse JSON from response: {response[:300]}")


hypothesis_tester = HypothesisTester()
