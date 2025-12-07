"""
Hypothesis selection service.

Ranks hypotheses based on test results and selects the best interpretation.
"""

import logging
from backend.models.hypothesis_models import (
    StyleHypothesis,
    HypothesisSet,
)
from backend.websocket import manager

logger = logging.getLogger(__name__)


class HypothesisSelector:
    """Selects the best hypothesis from a tested set."""

    async def select_best(
        self,
        hypothesis_set: HypothesisSet,
        auto_select_threshold: float = 0.7,
        session_id: str | None = None,
    ) -> tuple[StyleHypothesis | None, bool]:
        """
        Select the best hypothesis from a tested set.

        Args:
            hypothesis_set: The set of tested hypotheses
            auto_select_threshold: Minimum confidence for auto-selection
            session_id: Optional session ID for logging

        Returns:
            Tuple of (selected_hypothesis, was_auto_selected)
            - If auto-selected: returns (hypothesis, True)
            - If no clear winner: returns (None, False) - user should choose
        """

        async def log(msg: str, level: str = "info"):
            logger.info(msg)
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "hypothesis_select")

        # Rank hypotheses by confidence
        ranked = hypothesis_set.rank_by_confidence()

        if not ranked:
            await log("No hypotheses to select from", "error")
            return None, False

        await log("Ranking hypotheses by confidence:")
        for idx, hyp in enumerate(ranked, 1):
            await log(
                f"  {idx}. {hyp.interpretation}: "
                f"confidence={hyp.confidence:.2f}, "
                f"tests={len(hyp.test_results)}"
            )

        best = ranked[0]

        # Check if best hypothesis meets auto-selection threshold
        if best.confidence >= auto_select_threshold:
            await log(
                f"Auto-selecting '{best.interpretation}' "
                f"(confidence {best.confidence:.2f} >= threshold {auto_select_threshold})",
                "success",
            )
            return best, True

        # Check if there's a clear winner (gap between #1 and #2)
        if len(ranked) > 1:
            second_best = ranked[1]
            confidence_gap = best.confidence - second_best.confidence

            await log(
                f"Best hypothesis: {best.interpretation} ({best.confidence:.2f})"
            )
            await log(
                f"Second best: {second_best.interpretation} ({second_best.confidence:.2f})"
            )
            await log(f"Confidence gap: {confidence_gap:.2f}")

            # If gap is significant (>0.15), auto-select
            if confidence_gap > 0.15:
                await log(
                    f"Auto-selecting '{best.interpretation}' due to significant gap",
                    "success",
                )
                return best, True

        # No clear winner - return best but don't auto-select
        await log(
            f"No clear winner - user should review options. "
            f"Best: '{best.interpretation}' ({best.confidence:.2f})",
            "info",
        )
        return None, False

    async def manual_select(
        self,
        hypothesis_set: HypothesisSet,
        hypothesis_id: str,
        session_id: str | None = None,
    ) -> StyleHypothesis:
        """
        Manually select a specific hypothesis.

        Args:
            hypothesis_set: The hypothesis set
            hypothesis_id: ID of hypothesis to select
            session_id: Optional session ID for logging

        Returns:
            Selected hypothesis

        Raises:
            ValueError if hypothesis not found
        """

        async def log(msg: str, level: str = "info"):
            logger.info(msg)
            if session_id:
                await manager.broadcast_log(session_id, msg, level, "hypothesis_select")

        hypothesis = hypothesis_set.get_hypothesis(hypothesis_id)

        if not hypothesis:
            await log(f"Hypothesis {hypothesis_id} not found", "error")
            raise ValueError(f"Hypothesis {hypothesis_id} not found in set")

        await log(
            f"Manually selected: {hypothesis.interpretation} "
            f"(confidence={hypothesis.confidence:.2f})",
            "success",
        )

        return hypothesis


hypothesis_selector = HypothesisSelector()
