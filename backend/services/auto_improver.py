"""
Auto Improver Service

Intelligently iterates on style generation, analyzing weaknesses and focusing
on improving the lowest-scoring dimensions until target quality is reached.
"""
import logging
from typing import Callable, Awaitable

from backend.models.schemas import StyleProfile, CritiqueResult
from backend.services.agent import style_agent
from backend.services.comfyui import comfyui_service
from backend.services.critic import style_critic

logger = logging.getLogger(__name__)


class AutoImprover:
    """Intelligent auto-iteration that focuses on weak dimensions."""

    def __init__(self):
        self.weak_dimension_threshold = 65  # Dimensions below this need focus
        self.improvement_boost = 1.5  # How much to emphasize weak areas

        # Pass/Fail criteria
        self.overall_weight = 0.6  # Overall score gets 60% weight
        self.dimensions_weight = 0.4  # Dimension scores get 40% weight
        self.catastrophic_regression_threshold = 20  # Dimension drop > this = catastrophic
        self.min_improvement = 0.5  # Minimum weighted score improvement to pass

    async def run_focused_iteration(
        self,
        session_id: str,
        subject: str,
        style_profile: StyleProfile,
        original_image_b64: str,
        feedback_history: list[dict],
        previous_scores: dict[str, int] | None = None,
        creativity_level: int = 50,
        log_fn: Callable[[str, str, str], Awaitable[None]] = None,
    ) -> dict:
        """
        Run one iteration with focus on weak dimensions.

        Returns: {
            "image_b64": str,
            "prompt_used": str,
            "critique": CritiqueResult,
            "weak_dimensions": list[str],
            "focused_areas": list[str],
        }
        """
        async def log(msg: str, level: str = "info", step: str = "auto"):
            if log_fn:
                await log_fn(msg, level, step)
            logger.info(f"[{step}] {msg}")

        # Identify weak dimensions from previous iteration
        weak_dimensions = []
        focused_areas = []

        if previous_scores:
            for dimension, score in previous_scores.items():
                if dimension != "overall" and score < self.weak_dimension_threshold:
                    weak_dimensions.append(dimension)

            if weak_dimensions:
                await log(f"Identified weak dimensions: {', '.join(weak_dimensions)}", "warning", "analysis")
            else:
                await log("All dimensions above threshold, maintaining current approach", "info", "analysis")

        # Build focused feedback emphasizing weak areas
        focused_feedback = self._build_focused_feedback(
            weak_dimensions,
            style_profile,
            feedback_history
        )

        if focused_feedback:
            focused_areas = [f["area"] for f in focused_feedback]
            await log(f"Focusing on: {', '.join(focused_areas)}", "info", "strategy")
            feedback_history = feedback_history + focused_feedback

        # Generate image with focused guidance
        await log("Generating prompt with weakness focus...", "info", "generate")
        image_prompt = await style_agent.generate_image_prompt(
            style_profile=style_profile,
            subject=subject,
            feedback_history=feedback_history,
            session_id=session_id,
        )

        await log(f"Prompt generated ({len(image_prompt)} chars)", "success", "generate")

        # Generate image
        await log("Generating image...", "info", "generate")
        image_b64 = await comfyui_service.generate(
            prompt=image_prompt,
            session_id=session_id
        )
        await log("Image generated", "success", "generate")

        # Critique with focus on previously weak areas
        await log("Critiquing with focus on weak areas...", "info", "critique")
        critique_result = await style_critic.critique(
            original_image_b64=original_image_b64,
            generated_image_b64=image_b64,
            style_profile=style_profile,
            creativity_level=creativity_level,
            session_id=session_id,
        )

        # Analyze improvement
        if previous_scores and weak_dimensions:
            improvements = []
            for dim in weak_dimensions:
                old_score = previous_scores.get(dim, 0)
                new_score = critique_result.match_scores.get(dim, 0)
                delta = new_score - old_score
                if delta > 0:
                    improvements.append(f"{dim}(+{delta})")
                    await log(f"✓ {dim}: {old_score} → {new_score} (+{delta})", "success", "improvement")
                elif delta < 0:
                    await log(f"✗ {dim}: {old_score} → {new_score} ({delta})", "warning", "regression")
                else:
                    await log(f"= {dim}: {new_score} (no change)", "info", "stable")

        overall_score = critique_result.match_scores.get("overall", 0)
        await log(f"Overall score: {overall_score}/100", "success", "critique")

        return {
            "image_b64": image_b64,
            "prompt_used": image_prompt,
            "critique": critique_result,
            "weak_dimensions": weak_dimensions,
            "focused_areas": focused_areas,
        }

    def calculate_weighted_score(self, scores: dict[str, int]) -> float:
        """
        Calculate weighted composite score.

        Overall score gets 60% weight, dimension average gets 40% weight.
        This makes the overall score more important in decision-making.
        """
        overall = scores.get("overall", 0)

        # Calculate average of dimension scores (excluding 'overall')
        dimension_scores = [v for k, v in scores.items() if k != "overall"]
        dimension_avg = sum(dimension_scores) / len(dimension_scores) if dimension_scores else 0

        # Weighted composite
        weighted = (overall * self.overall_weight) + (dimension_avg * self.dimensions_weight)
        return weighted

    def evaluate_iteration(
        self,
        new_scores: dict[str, int],
        baseline_scores: dict[str, int] | None,
    ) -> tuple[bool, str, dict]:
        """
        Determine if iteration should be approved (pass) or rejected (fail).

        Returns: (should_approve, reason, analysis)

        Pass criteria:
        - Weighted score improves by at least min_improvement
        - No catastrophic regression (dimension drop > 20 points)
        - Overall score doesn't regress

        Fail criteria:
        - Weighted score regresses or doesn't improve enough
        - Catastrophic regression in any dimension
        - Overall score regresses
        """
        # If no baseline, first iteration always passes
        if not baseline_scores:
            return True, "First iteration - establishing baseline", {
                "weighted_score": self.calculate_weighted_score(new_scores),
                "overall_score": new_scores.get("overall", 0),
            }

        # Calculate weighted scores
        new_weighted = self.calculate_weighted_score(new_scores)
        baseline_weighted = self.calculate_weighted_score(baseline_scores)
        weighted_delta = new_weighted - baseline_weighted

        # Check overall score
        new_overall = new_scores.get("overall", 0)
        baseline_overall = baseline_scores.get("overall", 0)
        overall_delta = new_overall - baseline_overall

        # Check for catastrophic regressions
        catastrophic_regressions = []
        dimension_deltas = {}

        for dimension, new_score in new_scores.items():
            if dimension == "overall":
                continue
            baseline_score = baseline_scores.get(dimension, 0)
            delta = new_score - baseline_score
            dimension_deltas[dimension] = delta

            if delta < -self.catastrophic_regression_threshold:
                catastrophic_regressions.append(f"{dimension} ({baseline_score} → {new_score}, Δ{delta})")

        # Build analysis
        analysis = {
            "weighted_score": new_weighted,
            "weighted_delta": weighted_delta,
            "overall_score": new_overall,
            "overall_delta": overall_delta,
            "dimension_deltas": dimension_deltas,
            "catastrophic_regressions": catastrophic_regressions,
        }

        # Fail conditions
        if catastrophic_regressions:
            return False, f"FAIL: Catastrophic regression in {', '.join(catastrophic_regressions)}", analysis

        if overall_delta < -2:  # Allow small fluctuation
            return False, f"FAIL: Overall score regressed ({baseline_overall} → {new_overall}, Δ{overall_delta:.1f})", analysis

        if weighted_delta < self.min_improvement:
            return False, f"FAIL: Insufficient improvement (weighted Δ{weighted_delta:.1f} < {self.min_improvement})", analysis

        # Pass!
        return True, f"PASS: Weighted score improved by {weighted_delta:.1f} (overall Δ{overall_delta:.1f})", analysis

    def _build_focused_feedback(
        self,
        weak_dimensions: list[str],
        style_profile: StyleProfile,
        existing_feedback: list[dict],
    ) -> list[dict]:
        """Build synthetic feedback to emphasize weak dimensions."""
        focused_feedback = []

        for dimension in weak_dimensions:
            if dimension == "palette":
                colors = style_profile.palette.color_descriptions[:3]
                focused_feedback.append({
                    "iteration": -1,  # Synthetic
                    "approved": False,
                    "notes": f"Pay closer attention to the color palette: {', '.join(colors)}. "
                            f"The colors must match exactly. Saturation level: {style_profile.palette.saturation}.",
                    "area": "color palette",
                })
            elif dimension == "lighting":
                focused_feedback.append({
                    "iteration": -1,
                    "approved": False,
                    "notes": f"Focus on lighting: {style_profile.lighting.lighting_type}. "
                            f"Shadows should be {style_profile.lighting.shadows}. "
                            f"Highlights: {style_profile.lighting.highlights}.",
                    "area": "lighting",
                })
            elif dimension == "texture":
                focused_feedback.append({
                    "iteration": -1,
                    "approved": False,
                    "notes": f"Texture needs work: {style_profile.texture.surface}. "
                            f"Noise level: {style_profile.texture.noise_level}. "
                            f"Special effects: {', '.join(style_profile.texture.special_effects[:2]) if style_profile.texture.special_effects else 'none'}.",
                    "area": "texture",
                })
            elif dimension == "composition":
                focused_feedback.append({
                    "iteration": -1,
                    "approved": False,
                    "notes": f"Composition must follow: {style_profile.composition.camera}, "
                            f"{style_profile.composition.framing}.",
                    "area": "composition",
                })
            elif dimension == "line_quality":
                focused_feedback.append({
                    "iteration": -1,
                    "approved": False,
                    "notes": f"Line quality: {style_profile.line_and_shape.line_quality}. "
                            f"Shape language: {style_profile.line_and_shape.shape_language}.",
                    "area": "line quality",
                })

        return focused_feedback

    def should_continue(
        self,
        current_score: int,
        target_score: int,
        iteration: int,
        max_iterations: int,
    ) -> tuple[bool, str]:
        """
        Determine if auto-iteration should continue.

        Returns: (should_continue, reason)
        """
        if current_score >= target_score:
            return False, f"Target score reached: {current_score}/{target_score}"

        if iteration >= max_iterations:
            return False, f"Max iterations reached: {iteration}/{max_iterations}"

        return True, f"Continuing: {current_score} < {target_score} (iteration {iteration}/{max_iterations})"


auto_improver = AutoImprover()
