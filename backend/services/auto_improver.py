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
        self.catastrophic_threshold = 25  # Any dimension below this = truly catastrophic (lowered from 40)

        # Incremental improvement criteria (for climbing from low scores)
        self.min_improvement = 3  # Must improve by at least this much to approve
        self.allow_incremental = True  # Allow gradual improvement from bad starting points

        # DIMENSION CATEGORIZATION - Not all dimensions are equally critical
        # Structural dimensions affect subject/composition identity - catastrophic = instant reject
        self.structural_dimensions = ["composition", "line_and_shape"]

        # Technique dimensions affect rendering quality - catastrophic = check net progress
        self.technique_dimensions = ["texture", "lighting"]

        # Stylistic dimensions affect aesthetics - catastrophic = gated by net progress
        self.stylistic_dimensions = ["palette", "motifs"]

        # WEIGHTED NET PROGRESS - Dimensions have different importance
        # Why: Composition improvement > Motif improvement in terms of overall direction
        # Fixing composition is harder and more valuable than adjusting colors
        self.dimension_weights = {
            "composition": 2.0,      # Critical - affects subject identity
            "line_and_shape": 2.0,   # Critical - affects subject structure
            "texture": 1.5,          # Important - affects rendering quality
            "lighting": 1.5,         # Important - affects rendering quality
            "palette": 1.0,          # Moderate - affects aesthetics
            "motifs": 0.8,           # Lower - can be adjusted easily
        }

        # Weighted net progress thresholds
        self.strong_net_progress_threshold = 3.0  # Clear improvement across weighted dimensions
        self.weak_net_progress_threshold = 1.0    # Minimal positive movement

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
        style_profile: StyleProfile | None = None,  # For checking original_subject
        best_approved_score: int | None = None,
        training_insights: dict | None = None,
        previous_scores: dict[str, int] | None = None,  # NEW: For weighted delta calculation
    ) -> tuple[bool, str, dict]:
        """
        Determine if iteration should be approved (pass) or rejected (fail).

        WEIGHTED MULTI-DIMENSIONAL EVALUATION:
        Not all dimensions are equally important. We optimize a 6D gradient vector, not a scalar.

        Dimension Categories:
        - Structural (composition, line_and_shape): Catastrophic = instant reject
        - Technique (texture, lighting): Catastrophic = check net progress
        - Stylistic (palette, motifs): Catastrophic = gated by net progress

        Weighted Net Progress:
        Structural dimensions have 2.0x weight (composition fixes are harder/more valuable)
        Stylistic dimensions have 0.8-1.0x weight (easier to adjust)

        Pass criteria:
        - Tier 1: Meets absolute quality targets (70 overall, 55 dimensions)
        - Tier 2: Strong weighted net progress (>= 3.0)
        - Tier 3: Positive weighted net progress despite stylistic catastrophic

        Fail criteria:
        - Structural catastrophic failure
        - Negative weighted net progress

        Returns: (should_approve, reason, analysis)
        """
        overall_score = new_scores.get("overall", 0)

        # Check for subject/content drift - VERY CONSERVATIVE
        # Only reject if VLM explicitly says the SUBJECT (what) changed, not STYLE (how)
        lost_traits = critique_result.lost_traits if critique_result else []

        # ONLY look for explicit VLM statements that the subject/content changed
        # Do NOT check keywords - those catch style elements incorrectly
        explicit_drift_patterns = [
            "subject changed", "subject is different", "subject became",
            "wrong subject", "different subject", "subject replaced",
            "main content changed", "depicts different", "shows different",
        ]

        subject_drift_failures = []
        for trait in lost_traits:
            trait_lower = trait.lower()
            for pattern in explicit_drift_patterns:
                if pattern in trait_lower:
                    subject_drift_failures.append(trait)
                    break

        if subject_drift_failures:
            analysis = {
                "overall_score": overall_score,
                "subject_drift_failures": subject_drift_failures,
                "lost_traits": lost_traits,
            }
            return False, f"FAIL (Subject Drift): {', '.join(subject_drift_failures[:1])}", analysis

        # Categorize catastrophic failures by dimension type (skip on first iteration)
        structural_catastrophic = []
        technique_catastrophic = []
        stylistic_catastrophic = []

        if best_approved_score is not None:  # Not the first iteration
            for dimension, score in new_scores.items():
                if dimension == "overall":
                    continue
                if score < self.catastrophic_threshold:
                    failure_str = f"{dimension}={score}"
                    if dimension in self.structural_dimensions:
                        structural_catastrophic.append(failure_str)
                    elif dimension in self.technique_dimensions:
                        technique_catastrophic.append(failure_str)
                    elif dimension in self.stylistic_dimensions:
                        stylistic_catastrophic.append(failure_str)

            # STRUCTURAL catastrophic = INSTANT REJECT (subject/composition identity lost)
            if structural_catastrophic:
                analysis = {
                    "overall_score": overall_score,
                    "catastrophic_failures": structural_catastrophic,
                    "catastrophic_type": "structural",
                }
                return False, f"FAIL (Structural Catastrophic): {', '.join(structural_catastrophic)} - subject identity lost", analysis

        # Combine all catastrophic failures for analysis
        all_catastrophic = structural_catastrophic + technique_catastrophic + stylistic_catastrophic

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

        # WEIGHTED NET PROGRESS CALCULATION
        # Calculate weighted delta from previous iteration (if available)
        weighted_net_progress = 0.0
        dimension_deltas = {}
        weighted_deltas = {}
        improvement = None  # Scalar overall improvement (legacy)

        if previous_scores is not None:
            # Calculate per-dimension deltas
            for dimension in self.dimension_weights.keys():
                if dimension in new_scores and dimension in previous_scores:
                    delta = new_scores[dimension] - previous_scores[dimension]
                    dimension_deltas[dimension] = delta
                    # Weight the delta by dimension importance
                    weighted_delta = delta * self.dimension_weights[dimension]
                    weighted_deltas[dimension] = weighted_delta
                    weighted_net_progress += weighted_delta

        # Legacy scalar improvement (for backward compatibility)
        if best_approved_score is not None:
            improvement = overall_score - best_approved_score

        # Classify progress strength
        strong_weighted_progress = weighted_net_progress >= self.strong_net_progress_threshold
        weak_positive_progress = weighted_net_progress >= self.weak_net_progress_threshold
        negative_progress = weighted_net_progress < 0

        # Build analysis
        analysis = {
            "overall_score": overall_score,
            "target_overall": target_overall,
            "target_dimension": target_dimension,
            "meets_targets": meets_targets,
            "best_approved_score": best_approved_score,
            "improvement": improvement,  # Legacy scalar
            "dimension_deltas": dimension_deltas,
            "weighted_deltas": weighted_deltas,
            "weighted_net_progress": weighted_net_progress,
            "strong_weighted_progress": strong_weighted_progress,
            "weak_positive_progress": weak_positive_progress,
            "dimension_below_target": dimension_below_target,
            "catastrophic_failures": all_catastrophic,
            "structural_catastrophic": structural_catastrophic,
            "technique_catastrophic": technique_catastrophic,
            "stylistic_catastrophic": stylistic_catastrophic,
        }

        # DECISION LOGIC - Multi-tier weighted evaluation

        # Tier 1: Meets absolute quality targets
        if meets_targets:
            return True, f"PASS (Tier 1 - Quality Targets): Overall {overall_score}/{target_overall}, all dimensions ≥ {target_dimension}", analysis

        # Tier 2: Strong weighted net progress (clear multi-dimensional improvement)
        if strong_weighted_progress:
            improved_dims = [f"{d}({delta:+.0f})" for d, delta in dimension_deltas.items() if delta > 2]
            return True, f"PASS (Tier 2 - Strong Progress): Weighted Δ={weighted_net_progress:+.1f} | Improved: {', '.join(improved_dims[:3])}", analysis

        # Tier 3: Weak positive progress despite catastrophic failures
        # Allow if: stylistic/technique catastrophic BUT net progress is positive
        if weak_positive_progress and (technique_catastrophic or stylistic_catastrophic):
            cat_type = "technique" if technique_catastrophic else "stylistic"
            cat_dims = technique_catastrophic if technique_catastrophic else stylistic_catastrophic
            return True, f"PASS (Tier 3 - Recovery Mode): Weighted Δ={weighted_net_progress:+.1f} despite {cat_type} regression in {', '.join(cat_dims)}", analysis

        # First iteration baseline (always approve)
        if best_approved_score is None:
            return True, f"PASS (Baseline): First iteration with overall {overall_score}", analysis

        # FAIL: Negative weighted progress or no progress despite catastrophic
        if negative_progress:
            regressed_dims = [f"{d}({delta:.0f})" for d, delta in dimension_deltas.items() if delta < -2]
            return False, f"FAIL: Weighted Δ={weighted_net_progress:.1f} (negative) | Regressed: {', '.join(regressed_dims[:3])}", analysis

        # FAIL: Catastrophic failures with insufficient progress
        if all_catastrophic:
            return False, f"FAIL: Catastrophic in {', '.join(all_catastrophic)} with Weighted Δ={weighted_net_progress:.1f} (below threshold)", analysis

        # FAIL: No progress
        return False, f"FAIL: Weighted Δ={weighted_net_progress:.1f} below threshold ({self.weak_net_progress_threshold})", analysis

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
