import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="training")
    status: Mapped[str] = mapped_column(String(20), default="created")
    original_image_path: Mapped[str] = mapped_column(String(500), nullable=True)
    style_hints: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # Relationships
    style_profiles: Mapped[list["StyleProfileDB"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    iterations: Mapped[list["Iteration"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    hypothesis_sets: Mapped[list["HypothesisSetDB"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    @property
    def current_style_version(self) -> int | None:
        if self.style_profiles:
            return max(sp.version for sp in self.style_profiles)
        return None

    @property
    def iteration_count(self) -> int:
        return len(self.iterations)


class StyleProfileDB(Base):
    __tablename__ = "style_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="style_profiles")


class Iteration(Base):
    __tablename__ = "iterations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False
    )
    iteration_num: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    scores_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    # Full critique data for training
    critique_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="iterations")

    @property
    def scores(self) -> dict[str, int] | None:
        return self.scores_json

    @property
    def critique(self) -> dict | None:
        return self.critique_json


class TrainedStyle(Base):
    """A finalized style extracted from training, ready for prompt writing.

    Each TrainedStyle is its own 'agent' with:
    - Unique style profile (visual characteristics)
    - Learned rules from training (what to include/avoid)
    - Training summary (what was learned during iteration)
    """
    __tablename__ = "trained_styles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The finalized style profile (visual characteristics)
    style_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Style rules learned from training (positive/negative descriptors)
    style_rules_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Training summary - what the agent learned during training
    training_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Reference image thumbnail (base64, small)
    thumbnail_b64: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source training session (optional link)
    source_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )

    # Training stats
    iterations_trained: Mapped[int] = mapped_column(Integer, default=0)
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Tags for organization
    tags_json: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def training_summary(self) -> dict | None:
        return self.training_summary_json


class HypothesisSetDB(Base):
    """Collection of competing style interpretations for hypothesis mode.

    Stores all hypotheses generated for a session, their test results,
    and which hypothesis was selected.
    """
    __tablename__ = "hypothesis_sets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False
    )

    # Full hypothesis data stored as JSON (HypothesisSet model)
    hypotheses_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # ID of selected hypothesis (if chosen)
    selected_hypothesis_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="hypothesis_sets")


class GenerationHistory(Base):
    """History of images generated using prompt writer.

    Tracks all generations for auditing and exploration.
    """
    __tablename__ = "generation_history"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    style_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trained_styles.id", ondelete="CASCADE"), nullable=False
    )
    style_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Generation inputs
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    additional_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generated prompts
    positive_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generated image (stored as base64 or path)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
