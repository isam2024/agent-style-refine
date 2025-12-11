from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class SessionMode(str, Enum):
    TRAINING = "training"
    AUTO = "auto"
    HYPOTHESIS = "hypothesis"  # Multi-hypothesis extraction and testing


class SessionStatus(str, Enum):
    CREATED = "created"
    EXTRACTING = "extracting"
    READY = "ready"
    GENERATING = "generating"
    CRITIQUING = "critiquing"
    AUTO_IMPROVING = "auto_improving"
    HYPOTHESIS_EXPLORING = "hypothesis_exploring"  # Generating/testing hypotheses
    HYPOTHESIS_READY = "hypothesis_ready"  # Hypotheses ready for selection
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
    style_hints: str | None = Field(
        default=None,
        description="Optional user guidance: what the style IS and what it ISN'T (e.g., 'grid-like geometric pattern, NOT mandala')"
    )


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
    use_creative_rewrite: bool = Field(
        default=False,
        description="Use VLM creative rewriting (natural but may embellish) vs mechanical assembly (precise to style)"
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


# ============================================================
# Style Explorer Schemas (Divergent Exploration)
# ============================================================

class MutationStrategy(str, Enum):
    """Available mutation strategies for style exploration."""
    # === Core mutations ===
    RANDOM_DIMENSION = "random_dimension"  # Push a random dimension to extreme
    WHAT_IF = "what_if"                    # VLM-guided creative mutation
    CROSSOVER = "crossover"                # Blend with a donor style
    INVERSION = "inversion"                # Flip a characteristic
    AMPLIFY = "amplify"                    # Exaggerate existing traits
    DIVERGE = "diverge"                    # Extract-and-deviate using critique loop
    REFINE = "refine"                      # Reduce extremes toward balance

    # === Style transformations ===
    TIME_SHIFT = "time_shift"              # Apply different era/decade aesthetic
    MEDIUM_SWAP = "medium_swap"            # Change apparent artistic medium
    MOOD_SHIFT = "mood_shift"              # Transform emotional tone
    CULTURE_SHIFT = "culture_shift"        # Apply different cultural aesthetics

    # === Composition mutations ===
    SCALE_WARP = "scale_warp"              # Change apparent scale/perspective
    REMIX = "remix"                        # Shuffle elements between style sections
    CONSTRAIN = "constrain"                # Limit to single color or simple shapes
    CHAOS = "chaos"                        # Multiple random small mutations at once
    DECAY = "decay"                        # Add entropy/age/weathering

    # === Spatial mutations ===
    TOPOLOGY_FOLD = "topology_fold"        # Non-Euclidean/impossible geometry
    SILHOUETTE_SHIFT = "silhouette_shift"  # Modify contour/profile shape
    PERSPECTIVE_DRIFT = "perspective_drift"  # Surreal camera angles, sliding vanishing points
    AXIS_SWAP = "axis_swap"                # Rotate conceptual axes (vertical↔horizontal)

    # === Physics mutations ===
    PHYSICS_BEND = "physics_bend"          # Alter physical laws (gravity, light behavior)
    CHROMATIC_GRAVITY = "chromatic_gravity"  # Colors cluster or repel in new ways
    MATERIAL_TRANSMUTE = "material_transmute"  # Swap material properties (glass→fur)
    TEMPORAL_EXPOSURE = "temporal_exposure"  # Long exposure, freeze frames, ghost trails

    # === Pattern mutations ===
    MOTIF_SPLICE = "motif_splice"          # Inject recurring foreign motif
    RHYTHM_OVERLAY = "rhythm_overlay"      # Apply tempo-based visual patterns
    HARMONIC_BALANCE = "harmonic_balance"  # Musical composition logic for visuals
    SYMMETRY_BREAK = "symmetry_break"      # Break or force symmetry

    # === Density mutations ===
    DENSITY_SHIFT = "density_shift"        # Vary visual information density
    DIMENSIONAL_SHIFT = "dimensional_shift"  # Flatten or deepen (2D↔2.5D↔3D)
    MICRO_MACRO_SWAP = "micro_macro_swap"  # Swap scales (tiny↔big patterns)
    ESSENCE_STRIP = "essence_strip"        # Remove secondary features, reveal core

    # === Narrative mutations ===
    NARRATIVE_RESONANCE = "narrative_resonance"  # Add implied story fragments
    ARCHETYPE_MASK = "archetype_mask"      # Map onto mythological archetypes
    ANOMALY_INJECT = "anomaly_inject"      # Single deliberate rule violation
    SPECTRAL_ECHO = "spectral_echo"        # Ghost-layers of earlier generations

    # === Environment mutations ===
    CLIMATE_MORPH = "climate_morph"        # Apply environmental system changes
    BIOME_SHIFT = "biome_shift"            # Reframe as new ecosystem

    # === Technical mutations ===
    ALGORITHMIC_WRINKLE = "algorithmic_wrinkle"  # Deterministic computational artifacts
    SYMBOLIC_REDUCTION = "symbolic_reduction"    # Turn features into metaphoric shapes

    # === Chromatic mutations ===
    CHROMA_BAND_SHIFT = "chroma_band_shift"      # Shift colors only within specific hue band
    CHROMATIC_NOISE = "chromatic_noise"          # Color-channel-separated noise like film grain
    CHROMATIC_TEMPERATURE_SPLIT = "chromatic_temperature_split"  # Warm highlights, cool shadows
    CHROMATIC_FUSE = "chromatic_fuse"            # Merge several hues into one unified mega-hue
    CHROMATIC_SPLIT = "chromatic_split"          # Separate one hue into sub-hues

    # === Lighting/Shadow mutations ===
    AMBIENT_OCCLUSION_VARIANCE = "ambient_occlusion_variance"  # Alter AO softness/darkness
    SPECULAR_FLIP = "specular_flip"              # Matte→glossy, glossy→matte
    BLOOM_VARIANCE = "bloom_variance"            # Adjust bloom amount/radius/aura
    DESYNC_LIGHTING_CHANNELS = "desync_lighting_channels"  # Randomize lighting independently
    HIGHLIGHT_SHIFT = "highlight_shift"          # Modify highlight behavior
    SHADOW_RECODE = "shadow_recode"              # Rewrite shadow behavior/color
    LIGHTING_ANGLE_SHIFT = "lighting_angle_shift"  # Move light source direction
    HIGHLIGHT_BLOOM_COLORIZE = "highlight_bloom_colorize"  # Change highlight bloom color
    MICRO_SHADOWING = "micro_shadowing"          # Create small crisp micro-shadows
    MACRO_SHADOW_PIVOT = "macro_shadow_pivot"    # Reposition large shadow masses

    # === Contour/Edge mutations ===
    CONTOUR_SIMPLIFY = "contour_simplify"        # Reduce contour lines for poster-like shapes
    CONTOUR_COMPLEXIFY = "contour_complexify"    # Add secondary/tertiary contour lines
    LINE_WEIGHT_MODULATION = "line_weight_modulation"  # Change outline weight/tapering
    EDGE_BEHAVIOR_SWAP = "edge_behavior_swap"    # Soft/hard/broken/feathered edges
    BOUNDARY_ECHO = "boundary_echo"              # Add thin duplicated outlines
    HALO_GENERATION = "halo_generation"          # Create outline glow around shapes

    # === Texture mutations ===
    TEXTURE_DIRECTION_SHIFT = "texture_direction_shift"  # Rotate texture direction
    NOISE_INJECTION = "noise_injection"          # Add controlled micro-noise
    MICROFRACTURE_PATTERN = "microfracture_pattern"  # Add cracking/crazing lines
    CROSSHATCH_DENSITY_SHIFT = "crosshatch_density_shift"  # Alter crosshatching density

    # === Material/Surface mutations ===
    BACKGROUND_MATERIAL_SWAP = "background_material_swap"  # Change backdrop material
    SURFACE_MATERIAL_SHIFT = "surface_material_shift"  # Transform surface feel
    TRANSLUCENCY_SHIFT = "translucency_shift"    # Alter transparency levels
    SUBSURFACE_SCATTER_TWEAK = "subsurface_scatter_tweak"  # Adjust internal glow
    ANISOTROPY_SHIFT = "anisotropy_shift"        # Change directional light reflection
    REFLECTIVITY_SHIFT = "reflectivity_shift"    # Change reflectivity without color change

    # === Tonal mutations ===
    MIDTONE_SHIFT = "midtone_shift"              # Mutate midtones only
    TONAL_COMPRESSION = "tonal_compression"      # Flatten tonal range
    TONAL_EXPANSION = "tonal_expansion"          # Expand tonal range
    MICROCONTRAST_TUNING = "microcontrast_tuning"  # Adjust small-scale contrast
    CONTRAST_CHANNEL_SWAP = "contrast_channel_swap"  # Selective channel contrast

    # === Blur/Focus mutations ===
    DIRECTIONAL_BLUR = "directional_blur"        # Motion-like blur along vector
    FOCAL_PLANE_SHIFT = "focal_plane_shift"      # Move focus point
    MASK_BOUNDARY_MUTATION = "mask_boundary_mutation"  # Modify mask borders

    # === Silhouette mutations ===
    SILHOUETTE_MERGE = "silhouette_merge"        # Fuse two silhouettes
    SILHOUETTE_SUBTRACT = "silhouette_subtract"  # Remove chunks for negative-space
    SILHOUETTE_DISTORTION = "silhouette_distortion"  # Stretch/bend/fracture silhouette
    INTERNAL_GEOMETRY_TWIST = "internal_geometry_twist"  # Twist inside, keep silhouette

    # === Depth mutations ===
    BACKGROUND_DEPTH_COLLAPSE = "background_depth_collapse"  # Compress background depth
    DEPTH_FLATTENING = "depth_flattening"        # Reduce depth cues
    DEPTH_EXPANSION = "depth_expansion"          # Exaggerate depth/perspective

    # === Composition mutations (new) ===
    QUADRANT_MUTATION = "quadrant_mutation"      # Mutate only one quadrant
    OBJECT_ALIGNMENT_SHIFT = "object_alignment_shift"  # Rotate/offset/misalign objects
    SPATIAL_HIERARCHY_FLIP = "spatial_hierarchy_flip"  # Reorder visual priority
    BALANCE_SHIFT = "balance_shift"              # Shift overall visual weight
    INTERPLAY_SWAP = "interplay_swap"            # Swap dominance between elements
    VIGNETTE_MODIFICATION = "vignette_modification"  # Add/modify vignette

    # === Motif mutations (new) ===
    MOTIF_MIRRORING = "motif_mirroring"          # Mirror motif H/V/diagonal
    MOTIF_SCALING = "motif_scaling"              # Scale repeated motifs
    MOTIF_REPETITION = "motif_repetition"        # Duplicate and scatter motif

    # === Color role mutations ===
    COLOR_ROLE_REASSIGNMENT = "color_role_reassignment"  # Swap color roles
    SATURATION_SCALPEL = "saturation_scalpel"    # Selective saturation (edges/inside)
    NEGATIVE_COLOR_INJECTION = "negative_color_injection"  # Inverted color accents
    AMBIENT_COLOR_SUCTION = "ambient_color_suction"  # Pull ambient into shadows
    LOCAL_COLOR_MUTATION = "local_color_mutation"  # Zone-specific palette changes

    # === Detail/Form mutations ===
    DETAIL_DENSITY_SHIFT = "detail_density_shift"  # Where detail clusters
    FORM_SIMPLIFICATION = "form_simplification"  # Reduce to simpler geometry
    FORM_COMPLICATION = "form_complication"      # Add micro-folds/greebles
    PROPORTION_SHIFT = "proportion_shift"        # Change element proportions

    # === Flow/Rhythm mutations ===
    PATH_FLOW_SHIFT = "path_flow_shift"          # Alter dominant directional flow
    RHYTHM_DISRUPTION = "rhythm_disruption"      # Break/introduce repetition intervals
    RHYTHM_REBALANCE = "rhythm_rebalance"        # Adjust motif spacing
    DIRECTIONAL_ENERGY_SHIFT = "directional_energy_shift"  # Alter implied flow

    # === Perspective mutations ===
    LOCAL_PERSPECTIVE_BEND = "local_perspective_bend"  # Bend localized perspective
    ATMOSPHERIC_SCATTER_SHIFT = "atmospheric_scatter_shift"  # Change light scatter
    OCCLUSION_PATTERN = "occlusion_pattern"      # Parts hidden behind imagined layers
    OPACITY_FOG = "opacity_fog"                  # Translucent fog/haze layer

    # === Overlay/Pattern mutations ===
    PATTERN_OVERLAY = "pattern_overlay"          # Apply repeating pattern overlay
    GRADIENT_REMAP = "gradient_remap"            # Reassign gradient behavior
    FRAME_REINTERPRETATION = "frame_reinterpretation"  # Alter conceptual border


class ExplorationStatus(str, Enum):
    """Status of an exploration session."""
    CREATED = "created"
    EXPLORING = "exploring"
    PAUSED = "paused"
    COMPLETED = "completed"


class ExplorationSessionCreate(BaseModel):
    """Request to create a new exploration session."""
    name: str = Field(description="Name for this exploration")
    image_b64: str = Field(description="Base64 encoded reference image")
    preferred_strategies: list[MutationStrategy] = Field(
        default=[MutationStrategy.RANDOM_DIMENSION, MutationStrategy.WHAT_IF, MutationStrategy.AMPLIFY],
        description="Which mutation strategies to use"
    )


class ExplorationSessionResponse(BaseModel):
    """Response for an exploration session."""
    id: str
    name: str
    reference_image_path: str
    base_style_profile: StyleProfile
    status: ExplorationStatus
    total_snapshots: int
    current_snapshot_id: str | None
    preferred_strategies: list[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExplorationSessionSummary(BaseModel):
    """Summary view of an exploration session for listing."""
    id: str
    name: str
    status: ExplorationStatus
    total_snapshots: int
    created_at: datetime

    class Config:
        from_attributes = True


class ExplorationScores(BaseModel):
    """Scores for an exploration snapshot."""
    novelty: float = Field(ge=0, le=100, description="How different from parent (0-100)")
    coherence: float = Field(ge=0, le=100, description="Is it still a valid style (0-100)")
    interest: float = Field(ge=0, le=100, description="Is it visually striking (0-100)")
    combined: float = Field(ge=0, le=100, description="Weighted combination")


class ExplorationSnapshotResponse(BaseModel):
    """Response for an exploration snapshot."""
    id: str
    session_id: str
    parent_id: str | None
    style_profile: StyleProfile
    generated_image_path: str
    prompt_used: str | None
    mutation_strategy: str
    mutation_description: str
    scores: ExplorationScores | None
    depth: int
    branch_name: str | None
    is_favorite: bool
    user_notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ExploreRequest(BaseModel):
    """Request to run one exploration step."""
    session_id: str
    strategy: MutationStrategy | None = Field(
        default=None,
        description="Specific strategy to use, or None for random from preferences"
    )
    parent_snapshot_id: str | None = Field(
        default=None,
        description="Snapshot to branch from, or None for current"
    )


class ExploreResponse(BaseModel):
    """Response from an exploration step."""
    snapshot: ExplorationSnapshotResponse
    image_b64: str = Field(description="Base64 encoded generated image")


class AutoExploreRequest(BaseModel):
    """Request to auto-run multiple exploration steps."""
    session_id: str
    num_steps: int = Field(default=5, ge=1, le=20, description="Number of steps to run")
    branch_threshold: float = Field(
        default=85.0,
        ge=0,
        le=100,
        description="Auto-branch if combined score exceeds this"
    )


class AutoExploreResponse(BaseModel):
    """Response from auto-exploration."""
    snapshots_created: int
    best_snapshot_id: str | None
    best_score: float | None
    stopped_reason: str  # "completed", "threshold_reached", "user_stopped"


class SnapshotUpdateRequest(BaseModel):
    """Request to update a snapshot (favorite, notes)."""
    is_favorite: bool | None = None
    user_notes: str | None = None
    branch_name: str | None = None


class ExplorationTreeNode(BaseModel):
    """A node in the exploration tree for visualization."""
    id: str
    parent_id: str | None
    depth: int
    mutation_strategy: str
    mutation_description: str
    combined_score: float | None
    is_favorite: bool
    children_count: int
    thumbnail_path: str  # For tree visualization


class ExplorationTreeResponse(BaseModel):
    """Full tree structure for visualization."""
    session_id: str
    root_nodes: list[ExplorationTreeNode]  # Entry points (depth=0)
    total_nodes: int
    max_depth: int


class SnapshotToStyleRequest(BaseModel):
    """Request to convert a snapshot to a trained style."""
    snapshot_id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default=[])
