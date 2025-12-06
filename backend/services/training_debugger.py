"""
Training Debugger - Detailed logging of style profile evolution

Creates human-readable debug logs showing:
- What traits are being added/removed/changed
- How motifs evolve across iterations
- Score progression and approval decisions
- Profile diffs between versions
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

from backend.models.schemas import StyleProfile, CritiqueResult
from backend.config import settings

logger = logging.getLogger(__name__)


class TrainingDebugger:
    def __init__(self):
        self.debug_dir = Path(settings.outputs_dir) / "debug_logs"
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self, session_id: str) -> Path:
        """Get the debug log file path for a session."""
        return self.debug_dir / f"{session_id}_training.log"

    def _write_section(self, file, title: str, content: str = ""):
        """Write a formatted section to the log file."""
        file.write(f"\n{'='*80}\n")
        file.write(f"{title}\n")
        file.write(f"{'='*80}\n")
        if content:
            file.write(f"{content}\n")

    def _write_subsection(self, file, title: str, content: str = ""):
        """Write a formatted subsection to the log file."""
        file.write(f"\n{'-'*80}\n")
        file.write(f"{title}\n")
        file.write(f"{'-'*80}\n")
        if content:
            file.write(f"{content}\n")

    def log_session_start(self, session_id: str, session_name: str, original_subject: str):
        """Log the start of a training session."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'w') as f:
            self._write_section(f, "TRAINING SESSION STARTED")
            f.write(f"Session ID: {session_id}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Original Subject: {original_subject}\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    def log_extraction(self, session_id: str, profile: StyleProfile):
        """Log initial style extraction."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'a') as f:
            self._write_section(f, "INITIAL STYLE EXTRACTION (v1)")

            self._write_subsection(f, "Style Name")
            f.write(f"{profile.style_name}\n")

            self._write_subsection(f, "Core Invariants (Identity Locks)")
            for i, inv in enumerate(profile.core_invariants, 1):
                f.write(f"  {i}. {inv}\n")

            self._write_subsection(f, "Color Palette")
            f.write(f"Saturation: {profile.palette.saturation}\n")
            f.write(f"Value Range: {profile.palette.value_range}\n")
            f.write("Colors:\n")
            for color in profile.palette.color_descriptions:
                f.write(f"  - {color}\n")

            self._write_subsection(f, "Lighting")
            f.write(f"Type: {profile.lighting.lighting_type}\n")
            f.write(f"Shadows: {profile.lighting.shadows}\n")
            f.write(f"Highlights: {profile.lighting.highlights}\n")

            self._write_subsection(f, "Texture")
            f.write(f"Surface: {profile.texture.surface}\n")
            f.write(f"Noise Level: {profile.texture.noise_level}\n")
            if profile.texture.special_effects:
                f.write("Special Effects:\n")
                for effect in profile.texture.special_effects:
                    f.write(f"  - {effect}\n")

            self._write_subsection(f, "Line & Shape")
            f.write(f"Line Quality: {profile.line_and_shape.line_quality}\n")
            f.write(f"Shape Language: {profile.line_and_shape.shape_language}\n")
            f.write(f"Geometry Notes: {profile.line_and_shape.geometry_notes}\n")

            self._write_subsection(f, "Composition")
            f.write(f"Camera: {profile.composition.camera}\n")
            f.write(f"Framing: {profile.composition.framing}\n")
            f.write(f"Depth: {profile.composition.depth}\n")
            f.write(f"Negative Space: {profile.composition.negative_space_behavior}\n")

            self._write_subsection(f, "Motifs (Initially Empty)")
            f.write(f"Recurring Elements: {len(profile.motifs.recurring_elements)}\n")
            f.write(f"Forbidden Elements: {len(profile.motifs.forbidden_elements)}\n")

    def log_iteration_start(self, session_id: str, iteration_num: int, profile_version: int):
        """Log the start of an iteration."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'a') as f:
            self._write_section(f, f"ITERATION {iteration_num} (Using Profile v{profile_version})")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    def log_prompt_generation(self, session_id: str, iteration_num: int, prompt: str):
        """Log the generated image prompt."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'a') as f:
            self._write_subsection(f, "Generated Image Prompt")
            f.write(f"{prompt}\n")

    def log_critique(
        self,
        session_id: str,
        iteration_num: int,
        critique: CritiqueResult,
        approved: bool,
        approval_reason: str
    ):
        """Log the critique results and what changed."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'a') as f:
            self._write_subsection(f, "Critique Scores")
            for dim, score in critique.match_scores.items():
                f.write(f"  {dim}: {score}/100\n")

            self._write_subsection(f, f"Decision: {'✓ APPROVED' if approved else '✗ REJECTED'}")
            f.write(f"Reason: {approval_reason}\n")

            if critique.preserved_traits:
                self._write_subsection(f, "Preserved Traits (Working Well)")
                for trait in critique.preserved_traits:
                    f.write(f"  ✓ {trait}\n")

            if critique.lost_traits:
                self._write_subsection(f, "Lost Traits (Need Emphasis)")
                for trait in critique.lost_traits:
                    f.write(f"  ✗ {trait}\n")

            if critique.interesting_mutations:
                self._write_subsection(f, "Interesting Mutations")
                for mutation in critique.interesting_mutations:
                    f.write(f"  → {mutation}\n")

    def log_profile_diff(
        self,
        session_id: str,
        iteration_num: int,
        old_profile: StyleProfile,
        new_profile: StyleProfile,
        new_version: int
    ):
        """Log the differences between profile versions."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'a') as f:
            self._write_subsection(f, f"Profile Update: v{new_version-1} → v{new_version}")

            # Check core_invariants changes
            old_inv = set(old_profile.core_invariants)
            new_inv = set(new_profile.core_invariants)
            added_inv = new_inv - old_inv
            removed_inv = old_inv - new_inv

            if added_inv or removed_inv:
                f.write("\nCore Invariants:\n")
                if added_inv:
                    for inv in added_inv:
                        f.write(f"  + {inv}\n")
                if removed_inv:
                    for inv in removed_inv:
                        f.write(f"  - {inv}\n")

            # Check color changes
            old_colors = set(old_profile.palette.color_descriptions)
            new_colors = set(new_profile.palette.color_descriptions)
            added_colors = new_colors - old_colors
            removed_colors = old_colors - new_colors

            if added_colors or removed_colors:
                f.write("\nColor Palette:\n")
                if added_colors:
                    for color in added_colors:
                        f.write(f"  + {color}\n")
                if removed_colors:
                    for color in removed_colors:
                        f.write(f"  - {color}\n")

            # Check saturation changes
            if old_profile.palette.saturation != new_profile.palette.saturation:
                f.write(f"\nSaturation: {old_profile.palette.saturation} → {new_profile.palette.saturation}\n")

            # Check lighting changes
            if old_profile.lighting.lighting_type != new_profile.lighting.lighting_type:
                f.write(f"\nLighting Type:\n")
                f.write(f"  OLD: {old_profile.lighting.lighting_type}\n")
                f.write(f"  NEW: {new_profile.lighting.lighting_type}\n")

            if old_profile.lighting.highlights != new_profile.lighting.highlights:
                f.write(f"\nHighlights:\n")
                f.write(f"  OLD: {old_profile.lighting.highlights}\n")
                f.write(f"  NEW: {new_profile.lighting.highlights}\n")

            if old_profile.lighting.shadows != new_profile.lighting.shadows:
                f.write(f"\nShadows:\n")
                f.write(f"  OLD: {old_profile.lighting.shadows}\n")
                f.write(f"  NEW: {new_profile.lighting.shadows}\n")

            # Check texture changes
            if old_profile.texture.surface != new_profile.texture.surface:
                f.write(f"\nTexture Surface:\n")
                f.write(f"  OLD: {old_profile.texture.surface}\n")
                f.write(f"  NEW: {new_profile.texture.surface}\n")

            # Check special effects
            old_effects = set(old_profile.texture.special_effects)
            new_effects = set(new_profile.texture.special_effects)
            added_effects = new_effects - old_effects
            removed_effects = old_effects - new_effects

            if added_effects or removed_effects:
                f.write("\nSpecial Effects:\n")
                if added_effects:
                    for effect in added_effects:
                        f.write(f"  + {effect}\n")
                if removed_effects:
                    for effect in removed_effects:
                        f.write(f"  - {effect}\n")

            # Check line & shape changes
            if old_profile.line_and_shape.line_quality != new_profile.line_and_shape.line_quality:
                f.write(f"\nLine Quality:\n")
                f.write(f"  OLD: {old_profile.line_and_shape.line_quality}\n")
                f.write(f"  NEW: {new_profile.line_and_shape.line_quality}\n")

            if old_profile.line_and_shape.shape_language != new_profile.line_and_shape.shape_language:
                f.write(f"\nShape Language:\n")
                f.write(f"  OLD: {old_profile.line_and_shape.shape_language}\n")
                f.write(f"  NEW: {new_profile.line_and_shape.shape_language}\n")

            # Check composition changes
            if old_profile.composition.framing != new_profile.composition.framing:
                f.write(f"\nFraming:\n")
                f.write(f"  OLD: {old_profile.composition.framing}\n")
                f.write(f"  NEW: {new_profile.composition.framing}\n")

            # Check motifs (IMPORTANT!)
            old_recurring = set(old_profile.motifs.recurring_elements)
            new_recurring = set(new_profile.motifs.recurring_elements)
            added_recurring = new_recurring - old_recurring
            removed_recurring = old_recurring - new_recurring

            if added_recurring or removed_recurring:
                f.write("\nRecurring Motifs:\n")
                if added_recurring:
                    for motif in added_recurring:
                        f.write(f"  + DISCOVERED: {motif}\n")
                if removed_recurring:
                    for motif in removed_recurring:
                        f.write(f"  - REMOVED: {motif}\n")

            old_forbidden = set(old_profile.motifs.forbidden_elements)
            new_forbidden = set(new_profile.motifs.forbidden_elements)
            added_forbidden = new_forbidden - old_forbidden
            removed_forbidden = old_forbidden - new_forbidden

            if added_forbidden or removed_forbidden:
                f.write("\nForbidden Elements:\n")
                if added_forbidden:
                    for elem in added_forbidden:
                        f.write(f"  + BANNED: {elem}\n")
                if removed_forbidden:
                    for elem in removed_forbidden:
                        f.write(f"  - UNBANNED: {elem}\n")

            # If no changes detected
            if not any([
                added_inv, removed_inv, added_colors, removed_colors,
                old_profile.palette.saturation != new_profile.palette.saturation,
                old_profile.lighting.lighting_type != new_profile.lighting.lighting_type,
                added_effects, removed_effects, added_recurring, removed_recurring,
                added_forbidden, removed_forbidden
            ]):
                f.write("\nNo significant changes detected in this update.\n")

    def log_iteration_rejected(self, session_id: str, iteration_num: int, reason: str):
        """Log when an iteration is rejected and profile is NOT updated."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'a') as f:
            self._write_subsection(f, "Profile NOT Updated")
            f.write(f"Reason: {reason}\n")
            f.write("Previous profile version retained.\n")

    def log_session_complete(
        self,
        session_id: str,
        total_iterations: int,
        approved_count: int,
        final_version: int,
        final_scores: dict[str, int]
    ):
        """Log the completion of a training session."""
        log_path = self._get_log_path(session_id)

        with open(log_path, 'a') as f:
            self._write_section(f, "TRAINING SESSION COMPLETE")
            f.write(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"\nTotal Iterations: {total_iterations}\n")
            f.write(f"Approved: {approved_count}/{total_iterations} ({approved_count/total_iterations*100:.1f}%)\n")
            f.write(f"Final Profile Version: v{final_version}\n")

            f.write(f"\nFinal Scores:\n")
            for dim, score in final_scores.items():
                f.write(f"  {dim}: {score}/100\n")

            f.write(f"\n{'='*80}\n")
            f.write(f"Debug log saved to: {log_path}\n")
            f.write(f"{'='*80}\n")


training_debugger = TrainingDebugger()
