from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class SessionMode(str, Enum):
    TRAINING = "training"
    AUTO = "auto"


class SessionStatus(str, Enum):
    CREATED = "created"
    EXTRACTING = "extracting"
    READY = "ready"
    GENERATING = "generating"
    CRITIQUING = "critiquing"
    AUTO_IMPROVING = "auto_improving"
    COMPLETED = "completed"
    ERROR = "error"


# Style Profile Sub-Schemas
class PaletteSchema(BaseModel):
    dominant_colors: list[str] = Field(default=[], description="Hex color codes for dominant colors")
    accents: list[str] = Field(default=[], description="Hex color codes for accent colors")
    color_descriptions: list[str] = Field(default=[], description="Named descriptions of colors, e.g., 'dusty rose', 'steel blue'")
    saturation: str = Field(default="medium", description="e.g., 'low', 'medium', 'high', 'medium-high'")
    value_range: str = Field(default="mid-tones", description="e.g., 'dark mids / bright highlights'")


class LineShapeSchema(BaseModel):
    line_quality: str = Field(default="", description="e.g., 'soft edges, minimal hard outlines'")
    shape_language: str = Field(default="", description="e.g., 'rounded, flowing, organic'")
    geometry_notes: str = Field(default="", description="Additional notes on geometric patterns")


class TextureSchema(BaseModel):
    surface: str = Field(default="", description="e.g., 'brushy, painterly, subtle canvas grain'")
    noise_level: str = Field(default="medium", description="e.g., 'low', 'medium', 'high'")
    special_effects: list[str] = Field(default=[], description="e.g., ['light bloom', 'glow halos']")


class LightingSchema(BaseModel):
    lighting_type: str = Field(default="", description="e.g., 'backlit / rim-lit, twilight'")
    shadows: str = Field(default="", description="e.g., 'soft, diffuse, slightly cool-toned'")
    highlights: str = Field(default="", description="e.g., 'warm, halo-like around primary subject'")


class CompositionSchema(BaseModel):
    model_config = {"extra": "allow"}  # Allow extra fields from old profiles

    camera: str = Field(default="", description="e.g., 'mid shot, slight low angle'")
    framing: str = Field(default="", description="e.g., 'subject centered or slightly off-center'")
    depth: str = Field(default="", description="Spatial layers and their relationships")
    negative_space_behavior: str = Field(default="", description="How negative space is treated")
    structural_notes: str = Field(default="", description="Key spatial relationships and layout")


class MotifsSchema(BaseModel):
    recurring_elements: list[str] = Field(default=[], description="Elements that should appear")
    forbidden_elements: list[str] = Field(default=[], description="Elements to avoid")


# Main Style Profile
class StyleProfile(BaseModel):
    style_name: str = Field(default="Extracted Style", description="A descriptive name for this style")
    core_invariants: list[str] = Field(
        default=[],
        description="Key style traits that must NEVER change"
    )
    palette: PaletteSchema = Field(default_factory=PaletteSchema)
    line_and_shape: LineShapeSchema = Field(default_factory=LineShapeSchema)
    texture: TextureSchema = Field(default_factory=TextureSchema)
    lighting: LightingSchema = Field(default_factory=LightingSchema)
    composition: CompositionSchema = Field(default_factory=CompositionSchema)
    motifs: MotifsSchema = Field(default_factory=MotifsSchema)
    original_subject: str | None = Field(
        default=None,
        description="What is depicted in the original image (subject matter)"
    )
    suggested_test_prompt: str | None = Field(
        default=None,
        description="A suggested prompt featuring similar subject matter for style comparison"
    )
    image_description: str | None = Field(
        default=None,
        description="Natural language description of the original image (reverse-engineered prompt)"
    )


# Critique Result
class CritiqueResult(BaseModel):
    match_scores: dict[str, int] = Field(
        description="Scores 0-100 for each style dimension"
    )
    preserved_traits: list[str] = Field(description="Traits that were captured well")
    lost_traits: list[str] = Field(description="Traits that drifted or are missing")
    interesting_mutations: list[str] = Field(
        description="New characteristics that could be incorporated"
    )
    updated_style_profile: StyleProfile


# API Request/Response Schemas
class SessionCreate(BaseModel):
    name: str = Field(description="Name for this session")
    mode: SessionMode = Field(default=SessionMode.TRAINING)
    image_b64: str = Field(description="Base64 encoded original image")


class SessionResponse(BaseModel):
    id: str
    name: str
    mode: SessionMode
    status: SessionStatus
    created_at: datetime
    current_style_version: int | None = None
    iteration_count: int = 0

    class Config:
        from_attributes = True


class IterationResponse(BaseModel):
    id: str
    session_id: str
    iteration_num: int
    image_path: str
    prompt_used: str | None = None
    scores: dict[str, int] | None = None
    feedback: str | None = None
    approved: bool | None = None
    created_at: datetime
    # Critique data for training insights
    critique_data: dict | None = Field(
        default=None,
        description="Critique data including preserved_traits, lost_traits, etc."
    )

    class Config:
        from_attributes = True


class ExtractionRequest(BaseModel):
    session_id: str


class GenerationRequest(BaseModel):
    session_id: str
    subject: str = Field(description="What to generate in the style")


class GenerationResponse(BaseModel):
    iteration_id: str
    image_b64: str
    prompt_used: str


class CritiqueRequest(BaseModel):
    session_id: str
    iteration_id: str
    creativity_level: int = Field(default=50, ge=0, le=100)


class IterationRequest(BaseModel):
    session_id: str
    subject: str
    creativity_level: int = Field(default=50, ge=0, le=100)


class FeedbackRequest(BaseModel):
    iteration_id: str
    approved: bool
    notes: str | None = None


class AutoModeRequest(BaseModel):
    session_id: str
    subject: str
    max_iterations: int = Field(default=5, ge=1, le=20)
    target_score: int = Field(default=80, ge=0, le=100)
    creativity_level: int = Field(default=50, ge=0, le=100)


class AutoImproveRequest(BaseModel):
    """Request for intelligent auto-iteration that focuses on weak dimensions."""
    session_id: str
    subject: str
    target_score: int = Field(default=85, ge=0, le=100, description="Stop when overall score reaches this")
    max_iterations: int = Field(default=10, ge=1, le=30, description="Maximum iterations to run")
    creativity_level: int = Field(default=50, ge=0, le=100, description="Creativity level for generation")


# WebSocket Messages
class WSMessage(BaseModel):
    event: str
    data: dict | None = None
    error: str | None = None


# ============================================================
# Trained Style & Prompt Writer Schemas
# ============================================================

class StyleRules(BaseModel):
    """Rules extracted from training for prompt writing."""
    # Positive style descriptors - always include these
    always_include: list[str] = Field(
        default=[],
        description="Style descriptors that should always be in the prompt"
    )
    # Negative style descriptors - always exclude these
    always_avoid: list[str] = Field(
        default=[],
        description="Elements that break the style, use as negative prompt"
    )
    # Quality/technique keywords
    technique_keywords: list[str] = Field(
        default=[],
        description="Technical style terms (e.g., 'oil painting', 'soft lighting')"
    )
    # Mood/atmosphere keywords
    mood_keywords: list[str] = Field(
        default=[],
        description="Mood and atmosphere descriptors"
    )
    # Learned from feedback
    emphasize: list[str] = Field(
        default=[],
        description="Aspects to emphasize based on training feedback"
    )
    de_emphasize: list[str] = Field(
        default=[],
        description="Aspects to tone down based on training feedback"
    )


class TrainedStyleCreate(BaseModel):
    """Request to create a trained style from a session."""
    session_id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default=[])


class TrainedStyleResponse(BaseModel):
    """Response for a trained style (style agent)."""
    id: str
    name: str
    description: str | None
    style_profile: StyleProfile
    style_rules: StyleRules
    training_summary: dict | None = Field(
        default=None,
        description="Summary of what the agent learned during training"
    )
    thumbnail_b64: str | None
    source_session_id: str | None
    iterations_trained: int
    final_score: int | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrainedStyleSummary(BaseModel):
    """Summary view of a trained style for listing."""
    id: str
    name: str
    description: str | None
    thumbnail_b64: str | None
    iterations_trained: int
    final_score: int | None
    tags: list[str]
    created_at: datetime

    class Config:
        from_attributes = True


# Prompt Writer Schemas
class PromptWriteRequest(BaseModel):
    """Request to write/rewrite a prompt in a style."""
    style_id: str = Field(description="ID of the trained style to use")
    subject: str = Field(description="The subject/scene to generate")
    additional_context: str | None = Field(
        default=None,
        description="Optional additional context or requirements"
    )
    include_negative: bool = Field(
        default=True,
        description="Whether to include negative prompt"
    )
    variation_level: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Prompt variation: 0=deterministic, 50=moderate, 100=maximum"
    )
    use_creative_rewrite: bool = Field(
        default=False,
        description="Use VLM creative rewriting (natural but may embellish) vs mechanical assembly (precise to style)"
    )


class PromptWriteResponse(BaseModel):
    """Response with styled prompt."""
    subject: str = Field(description="The subject (returned separately)")
    style_prompt: str = Field(description="ONLY style information (no subject)")
    positive_prompt: str = Field(description="Combined subject + style for convenience")
    negative_prompt: str | None = Field(description="Negative prompt if requested")
    style_name: str = Field(description="Name of the style used")
    # Optional: breakdown of how the prompt was constructed
    prompt_breakdown: dict | None = Field(
        default=None,
        description="Breakdown showing subject + style components"
    )


class PromptGenerateRequest(BaseModel):
    """Request to write a prompt AND generate an image."""
    style_id: str
    subject: str
    additional_context: str | None = None
    variation_level: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Prompt variation: 0=deterministic, 50=moderate, 100=maximum"
    )


class PromptGenerateResponse(BaseModel):
    """Response with styled prompt and generated image."""
    positive_prompt: str
    negative_prompt: str | None
    image_b64: str
    style_name: str


class GenerationHistoryResponse(BaseModel):
    """Response for a generation history entry."""
    id: str
    style_id: str
    style_name: str
    subject: str
    additional_context: str | None
    positive_prompt: str
    negative_prompt: str | None
    image_b64: str | None = Field(
        default=None,
        description="Base64 encoded image if available"
    )
    created_at: datetime

    class Config:
        from_attributes = True


class IterationStepResult(BaseModel):
    """Result from running one iteration step."""
    iteration_id: str
    iteration_num: int
    image_b64: str
    prompt_used: str
    critique: CritiqueResult
    updated_profile: StyleProfile
