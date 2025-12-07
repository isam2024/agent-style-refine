"""
Data models for hypothesis-based style extraction.

Hypothesis mode generates multiple competing interpretations of a style,
tests each one, and selects the best based on evidence.
"""
from datetime import datetime
from pydantic import BaseModel, Field
from backend.models.schemas import StyleProfile


class HypothesisTest(BaseModel):
    """Result from testing a hypothesis with a specific subject."""
    test_subject: str = Field(description="Subject used for testing (e.g., 'abstract pattern')")
    generated_image_path: str = Field(description="Path to generated test image")
    scores: dict[str, float] = Field(
        description="Test scores: visual_consistency, subject_independence, etc."
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StyleHypothesis(BaseModel):
    """
    A single interpretation of what the style might be.

    Contains a complete StyleProfile plus metadata about this interpretation.
    """
    id: str = Field(description="Unique identifier for this hypothesis")
    interpretation: str = Field(
        description="Human-readable label (e.g., 'Grid-based geometric abstraction')"
    )
    profile: StyleProfile = Field(description="Complete style profile for this interpretation")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) based on test results"
    )
    supporting_evidence: list[str] = Field(
        default_factory=list,
        description="Visual aspects that support this interpretation"
    )
    uncertain_aspects: list[str] = Field(
        default_factory=list,
        description="Aspects the VLM is uncertain about"
    )
    test_results: list[HypothesisTest] = Field(
        default_factory=list,
        description="Results from testing this hypothesis"
    )


class HypothesisSet(BaseModel):
    """
    Collection of competing hypotheses for a single image.

    Represents the full hypothesis exploration for a session.
    """
    session_id: str = Field(description="Session this hypothesis set belongs to")
    hypotheses: list[StyleHypothesis] = Field(
        description="List of competing interpretations"
    )
    selected_hypothesis_id: str | None = Field(
        default=None,
        description="ID of selected hypothesis (if chosen)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def get_hypothesis(self, hypothesis_id: str) -> StyleHypothesis | None:
        """Get hypothesis by ID."""
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                return h
        return None

    def get_selected(self) -> StyleHypothesis | None:
        """Get the selected hypothesis, if any."""
        if self.selected_hypothesis_id:
            return self.get_hypothesis(self.selected_hypothesis_id)
        return None

    def rank_by_confidence(self) -> list[StyleHypothesis]:
        """Return hypotheses sorted by confidence (highest first)."""
        return sorted(self.hypotheses, key=lambda h: h.confidence, reverse=True)


# Request/Response Models for API

class HypothesisExtractionRequest(BaseModel):
    """Request to extract multiple hypotheses from a session."""
    session_id: str
    num_hypotheses: int = Field(
        default=3,
        ge=2,
        le=5,
        description="Number of hypotheses to generate (2-5)"
    )


class HypothesisTestRequest(BaseModel):
    """Request to test a specific hypothesis."""
    session_id: str
    hypothesis_id: str
    test_subjects: list[str] = Field(
        default=["abstract pattern", "landscape", "portrait"],
        description="Subjects to test with"
    )


class HypothesisExploreRequest(BaseModel):
    """Request to run full hypothesis exploration (extract + test + rank)."""
    session_id: str
    num_hypotheses: int = Field(default=3, ge=2, le=5)
    test_subjects: list[str] = Field(
        default=["abstract pattern", "landscape", "portrait"]
    )
    auto_select: bool = Field(
        default=False,
        description="Auto-select best hypothesis if confidence > threshold"
    )
    auto_select_threshold: float = Field(
        default=0.7,
        ge=0.5,
        le=1.0,
        description="Confidence threshold for auto-selection"
    )


class HypothesisSelectRequest(BaseModel):
    """Request to manually select a hypothesis."""
    session_id: str
    hypothesis_id: str


class HypothesisExploreResponse(BaseModel):
    """Response from hypothesis exploration."""
    session_id: str
    hypotheses: list[StyleHypothesis]
    selected_hypothesis: StyleHypothesis | None
    auto_selected: bool
    test_images_generated: int
