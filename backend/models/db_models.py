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

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="iterations")

    @property
    def scores(self) -> dict[str, int] | None:
        return self.scores_json
