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

        # Absolute threshold criteria (ideal quality bars)
        self.target_overall_score = 70  # Target overall score (ideal)
        self.target_dimension_score = 55  # Target for dimensions (ideal)
        self.catastrophic_threshold = 40  # Any dimension below this = catastrophic fail

        # Incremental improvement criteria (for climbing from low scores)
        self.min_improvement = 3  # Must improve by at least this much to approve
        self.allow_incremental = True  # Allow gradual improvement from bad starting points

    async def run_focused_iteration(
        self,
        session_id: str,
        subject: str,
        style_profile: StyleProfile,
        original_image_b64: str,
        feedback_history: list[dict],
        previous_scores: dict[str, int] | None = None,
        creativity_level: int = 50,
        training_insights: dict | None = None,
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

        # Identify weak dimensions using two-phase approach
        weak_dimensions = []
        broad_stroke_threshold = 60  # Major issues below this
        refinement_threshold = self.weak_dimension_threshold  # 65
        focused_areas = []

        broad_stroke_issues = []
        refinement_issues = []

        if previous_scores:
            for dimension, score in previous_scores.items():
                if dimension != "overall":
                    if score < broad_stroke_threshold:
                        broad_stroke_issues.append((dimension, score))
                    elif score < refinement_threshold:
                        refinement_issues.append((dimension, score))

            # Phase 1: Broad strokes - fix ALL major issues simultaneously
            if broad_stroke_issues:
                weak_dimensions = [dim for dim, _ in broad_stroke_issues]
                await log(f"Phase 1 (Broad Strokes): Fixing major issues in {', '.join(weak_dimensions)}", "warning", "analysis")
                for dim, score in broad_stroke_issues:
                    await log(f"  - {dim}: {score} (< {broad_stroke_threshold})", "warning", "detail")

            # Phase 2: Refinement - polish one dimension at a time
            elif refinement_issues:
                # Sort by score, focus on worst dimension
                refinement_issues.sort(key=lambda x: x[1])
                weakest_dim, weakest_score = refinement_issues[0]
                weak_dimensions = [weakest_dim]
                await log(f"Phase 2 (Refinement): Polishing {weakest_dim} (score: {weakest_score})", "info", "analysis")

            else:
                await log("All dimensions above threshold, maintaining current approach", "info", "analysis")

        # Build focused feedback emphasizing weak areas
        focused_feedback = self._build_focused_feedback(
            weak_dimensions,
            style_profile,
            feedback_history,
            training_insights
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

    def compute_training_insights(self, iterations: list) -> dict:
        """Analyze training history to extract insights."""
        if not iterations:
            return {
                "dimension_averages": {},
                "frequently_lost_traits": [],
                "historical_best": None,
            }

        # Calculate dimension averages from all iterations
        dimension_scores = {}
        for it in iterations:
            if it.scores_json:
                for dim, score in it.scores_json.items():
                    if dim not in dimension_scores:
                        dimension_scores[dim] = []
                    dimension_scores[dim].append(score)

        dimension_averages = {
            dim: sum(scores) / len(scores) for dim, scores in dimension_scores.items()
        }

        # Find frequently lost traits
        lost_traits_count = {}
        for it in iterations:
            if it.critique_json and it.critique_json.get("lost_traits"):
                for trait in it.critique_json["lost_traits"]:
                    lost_traits_count[trait] = lost_traits_count.get(trait, 0) + 1

        # Sort by frequency, take top 5
        frequently_lost_traits = sorted(
            lost_traits_count.items(), key=lambda x: x[1], reverse=True
        )[:5]
        frequently_lost_traits = [trait for trait, _ in frequently_lost_traits]

        # Find historical best overall score
        historical_best = None
        if "overall" in dimension_averages:
            historical_best = dimension_averages["overall"]

        return {
            "dimension_averages": dimension_averages,
            "frequently_lost_traits": frequently_lost_traits,
            "historical_best": historical_best,
        }

    def evaluate_iteration(
        self,
        new_scores: dict[str, int],
        critique_result,  # CritiqueResult with preserved_traits, lost_traits
        best_approved_score: int | None = None,
        training_insights: dict | None = None,
    ) -> tuple[bool, str, dict]:
        """
        Determine if iteration should be approved (pass) or rejected (fail).

        Two-tier approval system:
        1. IDEAL: Meets absolute quality targets (70 overall, 55 dimensions)
        2. INCREMENTAL: Improves on best approved score by min_improvement (allows climbing from bad starts)

        Returns: (should_approve, reason, analysis)

        Pass criteria (EITHER):
        - Tier 1: Overall >= target_overall AND all dimensions >= target_dimension
        - Tier 2: Overall improves by >= min_improvement over best_approved
        - Always: No catastrophic failures (dimension < 40)

        Fail criteria:
        - Catastrophic failure in any dimension
        - Doesn't meet Tier 1 AND doesn't improve in Tier 2
        """
        overall_score = new_scores.get("overall", 0)

        # Check for subject/content preservation failures FIRST (highest priority)
        # These indicate the generated image doesn't match the requested subject
        lost_traits = critique_result.lost_traits if critique_result else []

        # Keywords that indicate critical subject changes (not style)
        subject_critical_keywords = [
            # Demographics/identity (highest priority - these should NEVER change)
            "african", "asian", "caucasian", "latino", "hispanic", "indigenous",
            "black", "white", "brown", "dark skin", "light skin", "skin tone",
            # Gender/age (should not change)
            "male", "female", "man", "woman", "boy", "girl", "child", "person",
            "young", "old", "elderly", "adult", "teenager",
            # Main objects/subjects (critical content)
            "car", "vehicle", "automobile", "truck", "suv",
            "building", "house", "structure", "architecture",
            "animal", "dog", "cat", "horse", "bird", "pet",
            "motorcycle", "bicycle", "bike", "boat", "plane", "aircraft",
            # Human features that shouldn't change
            "face", "facial features", "eyes", "hair color", "beard", "mustache",
            # Clothing/accessories that define the subject
            "uniform", "suit", "dress", "hat", "glasses",
            # Subject identifiers
            "subject", "main figure", "primary subject", "protagonist", "character",
        ]

        # Also check for "drift" patterns - phrases indicating deviation from original
        drift_indicators = [
            "different", "changed to", "became", "replaced with", "instead of",
            "now shows", "switched to", "transformed into", "altered to",
        ]

        subject_preservation_failures = []
        drift_detected = []

        for trait in lost_traits:
            trait_lower = trait.lower()

            # Check for explicit drift language
            for indicator in drift_indicators:
                if indicator in trait_lower:
                    drift_detected.append(trait)
                    break

            # Check for critical subject keywords
            for keyword in subject_critical_keywords:
                if keyword in trait_lower:
                    # Extra check: is this about the subject or just a style descriptor?
                    # Reject if it includes identity/demographic terms or main objects
                    critical_terms = ["african", "asian", "caucasian", "black", "white", "brown",
                                    "male", "female", "man", "woman", "car", "vehicle",
                                    "face", "subject", "figure"]
                    is_critical = any(term in trait_lower for term in critical_terms)
                    if is_critical:
                        subject_preservation_failures.append(trait)
                    break

        all_failures = subject_preservation_failures + drift_detected
        if all_failures:
            analysis = {
                "overall_score": overall_score,
                "subject_preservation_failures": subject_preservation_failures,
                "drift_detected": drift_detected,
                "lost_traits": lost_traits,
            }
            failure_summary = all_failures[:2]  # Show first 2
            return False, f"FAIL (Subject Drift): Critical subject changed - {', '.join(failure_summary)}", analysis

        # Check catastrophic failures (always reject)
        catastrophic_failures = []
        for dimension, score in new_scores.items():
            if dimension == "overall":
                continue
            if score < self.catastrophic_threshold:
                catastrophic_failures.append(f"{dimension}={score}")

        if catastrophic_failures:
            analysis = {
                "overall_score": overall_score,
                "catastrophic_failures": catastrophic_failures,
            }
            return False, f"FAIL: Catastrophic failure in {', '.join(catastrophic_failures)}", analysis

        # Tier 1: Check if meets absolute targets (ideal case)
        target_overall = self.target_overall_score
        target_dimension = self.target_dimension_score

        dimension_below_target = []
        for dimension, score in new_scores.items():
            if dimension == "overall":
                continue
            if score < target_dimension:
                dimension_below_target.append(f"{dimension}={score}")

        meets_targets = (overall_score >= target_overall) and (not dimension_below_target)

        # Tier 2: Check if improves on best approved (incremental case)
        improvement = None
        improves_incrementally = False

        if best_approved_score is not None and self.allow_incremental:
            improvement = overall_score - best_approved_score
            improves_incrementally = improvement >= self.min_improvement

        # Build analysis
        analysis = {
            "overall_score": overall_score,
            "target_overall": target_overall,
            "target_dimension": target_dimension,
            "meets_targets": meets_targets,
            "best_approved_score": best_approved_score,
            "improvement": improvement,
            "improves_incrementally": improves_incrementally,
            "dimension_below_target": dimension_below_target,
        }

        # Decision logic
        if meets_targets:
            # Tier 1: Meets quality targets
            return True, f"PASS (Tier 1): Overall {overall_score}/{target_overall}, all dimensions meet target", analysis

        if improves_incrementally:
            # Tier 2: Incremental improvement
            return True, f"PASS (Tier 2 - Incremental): Overall {overall_score} (+{improvement} from {best_approved_score})", analysis

        if best_approved_score is None:
            # First iteration - be more lenient with score threshold
            # But we already checked subject preservation above, so this is safe
            if overall_score >= 50:  # Very lenient baseline threshold
                return True, f"PASS (Baseline): First iteration with overall {overall_score}", analysis
            else:
                return False, f"FAIL: First iteration score too low ({overall_score} < 50 baseline threshold)", analysis

        # Fail - neither meets targets nor improves incrementally
        if improvement is not None:
            return False, f"FAIL: Overall {overall_score} doesn't meet target ({target_overall}) and improvement (+{improvement}) < threshold ({self.min_improvement})", analysis
        else:
            return False, f"FAIL: Overall {overall_score} < target {target_overall}, dimensions: {', '.join(dimension_below_target[:3]) if dimension_below_target else 'OK'}", analysis

    def _build_focused_feedback(
        self,
        weak_dimensions: list[str],
        style_profile: StyleProfile,
        existing_feedback: list[dict],
        training_insights: dict | None = None,
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

        # Add feedback for frequently lost traits from training insights
        if training_insights and training_insights.get("frequently_lost_traits"):
            lost_traits = training_insights["frequently_lost_traits"][:3]  # Top 3
            if lost_traits:
                focused_feedback.append({
                    "iteration": -1,
                    "approved": False,
                    "notes": f"CRITICAL: These traits are frequently lost in training: {', '.join(lost_traits)}. "
                            f"Pay special attention to preserving these elements.",
                    "area": "frequently lost traits",
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
