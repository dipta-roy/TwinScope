"""
Three-way merge engine for text files.

Implements a proper three-way merge algorithm that:
1. Finds common ancestor (base)
2. Computes diffs from base to left and base to right
3. Identifies conflicts where both sides modified the same region
4. Automatically merges non-conflicting changes
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator, Optional, Sequence

from app.core.models import (
    MergeConflict,
    MergeRegion,
    MergeRegionType,
    MergeResult,
    ConflictResolution,
    ThreeWayLine,
    ThreeWayLineOrigin,
)


class MergeStrategy(Enum):
    """Strategy for automatic conflict resolution."""
    MANUAL = auto()          # All conflicts require manual resolution
    FAVOR_LEFT = auto()      # Automatically choose left in conflicts
    FAVOR_RIGHT = auto()     # Automatically choose right in conflicts
    FAVOR_SHORTER = auto()   # Choose the shorter version
    FAVOR_LONGER = auto()    # Choose the longer version


@dataclass
class DiffRegion:
    """Represents a region of difference from base."""
    base_start: int
    base_end: int
    other_start: int
    other_end: int
    base_lines: list[str]
    other_lines: list[str]
    
    @property
    def is_addition(self) -> bool:
        """True if lines were added (no base lines)."""
        return len(self.base_lines) == 0
    
    @property
    def is_deletion(self) -> bool:
        """True if lines were deleted (no other lines)."""
        return len(self.other_lines) == 0
    
    @property
    def is_modification(self) -> bool:
        """True if lines were modified."""
        return len(self.base_lines) > 0 and len(self.other_lines) > 0


class ThreeWayMergeEngine:
    """
    Three-way merge engine.
    
    Uses the diff3 algorithm to merge changes from two branches
    that diverged from a common base.
    """
    
    def __init__(
        self,
        strategy: MergeStrategy = MergeStrategy.MANUAL,
        conflict_marker_left: str = "<<<<<<< LEFT",
        conflict_marker_base: str = "||||||| BASE",
        conflict_marker_sep: str = "=======",
        conflict_marker_right: str = ">>>>>>> RIGHT"
    ):
        self.strategy = strategy
        self.conflict_marker_left = conflict_marker_left
        self.conflict_marker_base = conflict_marker_base
        self.conflict_marker_sep = conflict_marker_sep
        self.conflict_marker_right = conflict_marker_right
    
    def merge(
        self,
        base_lines: Sequence[str],
        left_lines: Sequence[str],
        right_lines: Sequence[str],
        left_label: str = "LEFT",
        right_label: str = "RIGHT",
        base_label: str = "BASE"
    ) -> MergeResult:
        """
        Perform three-way merge.
        
        Args:
            base_lines: Common ancestor lines
            left_lines: Left/ours version lines
            right_lines: Right/theirs version lines
            left_label: Label for left version in conflict markers
            right_label: Label for right version in conflict markers
            base_label: Label for base version in conflict markers
            
        Returns:
            MergeResult with merged content and conflict information
        """
        # Convert to lists for indexing
        base = list(base_lines)
        left = list(left_lines)
        right = list(right_lines)
        
        # Get diff regions
        left_diffs = self._compute_diff_regions(base, left)
        right_diffs = self._compute_diff_regions(base, right)
        
        # Merge the diff regions
        regions = self._merge_diff_regions(base, left, right, left_diffs, right_diffs)
        
        # Build result
        conflicts: list[MergeConflict] = []
        merged_lines: list[str] = []
        three_way_lines: list[ThreeWayLine] = []
        
        for region in regions:
            if region.region_type == MergeRegionType.CONFLICT:
                conflict = self._create_conflict(
                    region, len(conflicts), left_label, right_label, base_label
                )
                conflicts.append(conflict)
                
                # Apply strategy or mark as conflict
                resolved_lines = self._resolve_conflict(region, conflict)
                
                for line in resolved_lines:
                    merged_lines.append(line)
                    three_way_lines.append(ThreeWayLine(
                        content=line,
                        origin=ThreeWayLineOrigin.CONFLICT,
                        conflict_id=conflict.conflict_id
                    ))
            else:
                for line in region.lines:
                    merged_lines.append(line)
                    origin = self._region_type_to_origin(region.region_type)
                    three_way_lines.append(ThreeWayLine(
                        content=line,
                        origin=origin
                    ))
        
        return MergeResult(
            merged_lines=merged_lines,
            conflicts=conflicts,
            regions=regions,
            three_way_lines=three_way_lines,
            has_conflicts=len(conflicts) > 0,
            auto_resolved_count=sum(1 for c in conflicts if c.auto_resolved)
        )
    
    def _compute_diff_regions(
        self,
        base: list[str],
        other: list[str]
    ) -> list[DiffRegion]:
        """Compute diff regions between base and other."""
        regions: list[DiffRegion] = []
        
        matcher = difflib.SequenceMatcher(None, base, other, autojunk=False)
        
        base_idx = 0
        other_idx = 0
        
        for tag, b_start, b_end, o_start, o_end in matcher.get_opcodes():
            if tag == 'equal':
                base_idx = b_end
                other_idx = o_end
            else:
                # replace, insert, or delete
                regions.append(DiffRegion(
                    base_start=b_start,
                    base_end=b_end,
                    other_start=o_start,
                    other_end=o_end,
                    base_lines=base[b_start:b_end],
                    other_lines=other[o_start:o_end]
                ))
                base_idx = b_end
                other_idx = o_end
        
        return regions
    
    def _merge_diff_regions(
        self,
        base: list[str],
        left: list[str],
        right: list[str],
        left_diffs: list[DiffRegion],
        right_diffs: list[DiffRegion]
    ) -> list[MergeRegion]:
        """
        Merge diff regions from both sides.
        
        Uses a robust chunk-based algorithm to group overlapping or adjacent changes
        into single merge regions, handling arbitrary overlaps correctly.
        """
        regions: list[MergeRegion] = []
        
        # Create events for sweep line
        # Event: (position, type, side, diff)
        # Type: 0=start, 1=end (start before end at same position)
        # Side: 0=left, 1=right
        events: list[tuple[int, int, int, DiffRegion | None]] = []
        
        START = 0
        END = 1
        
        for diff in left_diffs:
            events.append((diff.base_start, START, 0, diff))
            events.append((diff.base_end, END, 0, diff))
        
        for diff in right_diffs:
            events.append((diff.base_start, START, 1, diff))
            events.append((diff.base_end, END, 1, diff))
            
        # Add sentinel for end of file
        events.append((len(base), 0, 2, None))
        
        # Sort events by position then type (start before end)
        events.sort()
        
        base_pos = 0
        active_left: set[DiffRegion] = set()
        active_right: set[DiffRegion] = set()
        
        # Track active hunk
        hunk_start = 0
        in_hunk = False
        involved_left: set[DiffRegion] = set()
        involved_right: set[DiffRegion] = set()
        
        i = 0
        while i < len(events):
            # Process all events at current position
            curr_pos = events[i][0]
            
            # If we advanced position and we are NOT in a hunk, emit UNCHANGED
            if curr_pos > base_pos and not in_hunk:
                regions.append(MergeRegion(
                    region_type=MergeRegionType.UNCHANGED,
                    base_start=base_pos,
                    base_end=curr_pos,
                    left_start=self._map_base_to_other(base_pos, left_diffs, left, bias='left'),
                    left_end=self._map_base_to_other(curr_pos, left_diffs, left, bias='left'),
                    right_start=self._map_base_to_other(base_pos, right_diffs, right, bias='left'),
                    right_end=self._map_base_to_other(curr_pos, right_diffs, right, bias='left'),
                    lines=base[base_pos:curr_pos]
                ))
            
            # If we moved and we ARE in a hunk, we just extend the hunk implicitly.
            
            base_pos = curr_pos
            
            # Process batch of events at this position to update state
            while i < len(events) and events[i][0] == curr_pos:
                _, type_, side, diff = events[i]
                
                if type_ == START: # Start
                    if side == 0:
                        active_left.add(diff)
                        involved_left.add(diff)
                    elif side == 1:
                        active_right.add(diff)
                        involved_right.add(diff)
                        
                    if not in_hunk and side != 2:
                        in_hunk = True
                        hunk_start = curr_pos
                        # already added to involved sets above
                    
                elif type_ == END: # End
                    if side == 0:
                        active_left.discard(diff)
                    elif side == 1:
                        active_right.discard(diff)
                
                i += 1
                
            # After processing events at this pos, check if hunk is closed
            if in_hunk and not active_left and not active_right:
                # Hunk finished
                hunk_end = base_pos
                in_hunk = False
                
                # Determine hunk type
                has_left = len(involved_left) > 0
                has_right = len(involved_right) > 0
                
                # Get mapped ranges
                # Use bias='right' for end to include insertions happening at boundaries
                l_start = self._map_base_to_other(hunk_start, left_diffs, left, bias='left')
                l_end = self._map_base_to_other(hunk_end, left_diffs, left, bias='right')
                r_start = self._map_base_to_other(hunk_start, right_diffs, right, bias='left')
                r_end = self._map_base_to_other(hunk_end, right_diffs, right, bias='right')
                
                l_lines = left[l_start:l_end]
                r_lines = right[r_start:r_end]
                b_lines = base[hunk_start:hunk_end]
                
                if has_left and not has_right:
                    regions.append(MergeRegion(
                        region_type=MergeRegionType.LEFT_CHANGED,
                        base_start=hunk_start,
                        base_end=hunk_end,
                        left_start=l_start,
                        left_end=l_end,
                        right_start=r_start,
                        right_end=r_end,
                        lines=l_lines,
                        base_lines=b_lines,
                        left_lines=l_lines,
                        right_lines=r_lines
                    ))
                elif not has_left and has_right:
                    regions.append(MergeRegion(
                        region_type=MergeRegionType.RIGHT_CHANGED,
                        base_start=hunk_start,
                        base_end=hunk_end,
                        left_start=l_start,
                        left_end=l_end,
                        right_start=r_start,
                        right_end=r_end,
                        lines=r_lines,
                        base_lines=b_lines,
                        left_lines=l_lines,
                        right_lines=r_lines
                    ))
                else:
                    # Both changed - check equality
                    if l_lines == r_lines:
                        regions.append(MergeRegion(
                            region_type=MergeRegionType.BOTH_CHANGED_SAME,
                            base_start=hunk_start,
                            base_end=hunk_end,
                            left_start=l_start,
                            left_end=l_end,
                            right_start=r_start,
                            right_end=r_end,
                            lines=l_lines,
                            base_lines=b_lines,
                            left_lines=l_lines,
                            right_lines=r_lines
                        ))
                    else:
                        regions.append(MergeRegion(
                            region_type=MergeRegionType.CONFLICT,
                            base_start=hunk_start,
                            base_end=hunk_end,
                            left_start=l_start,
                            left_end=l_end,
                            right_start=r_start,
                            right_end=r_end,
                            lines=[],
                            base_lines=b_lines,
                            left_lines=l_lines,
                            right_lines=r_lines
                        ))
                
                # Reset
                involved_left.clear()
                involved_right.clear()
        
        # Handle trailing base content
        if base_pos < len(base):
             regions.append(MergeRegion(
                region_type=MergeRegionType.UNCHANGED,
                base_start=base_pos,
                base_end=len(base),
                left_start=self._map_base_to_other(base_pos, left_diffs, left, bias='left'),
                left_end=len(left), # Safe assumption for end
                right_start=self._map_base_to_other(base_pos, right_diffs, right, bias='left'),
                right_end=len(right), 
                lines=base[base_pos:]
            ))
            
        return self._consolidate_regions(regions)
    
    def _consolidate_regions(self, regions: list[MergeRegion]) -> list[MergeRegion]:
        """Consolidate adjacent regions of the same type."""
        if not regions:
            return regions
        
        consolidated: list[MergeRegion] = []
        current = regions[0]
        
        for region in regions[1:]:
            if (current.region_type == region.region_type and 
                current.region_type == MergeRegionType.UNCHANGED):
                # Merge unchanged regions
                current = MergeRegion(
                    region_type=MergeRegionType.UNCHANGED,
                    base_start=current.base_start,
                    base_end=region.base_end,
                    left_start=current.left_start,
                    left_end=region.left_end,
                    right_start=current.right_start,
                    right_end=region.right_end,
                    lines=current.lines + region.lines
                )
            else:
                consolidated.append(current)
                current = region
        
        consolidated.append(current)
        return consolidated

    def _map_base_to_other(
        self,
        base_pos: int,
        diffs: list[DiffRegion],
        other: list[str],
        bias: str = 'left'
    ) -> int:
        """
        Map a position in base to the corresponding position in other.
        
        Args:
            base_pos: Position in base file
            diffs: List of diff regions
            other: The other file content (used for length checks)
            bias: 'left' (start of range) or 'right' (end of range).
                  Matters for zero-width regions (insertions).
        """
        offset = 0
        
        for diff in diffs:
            # If diff is strictly before, add full offset
            if diff.base_end < base_pos:
                offset += len(diff.other_lines) - len(diff.base_lines)
            
            # If diff starts exactly at pos
            elif diff.base_start == base_pos:
                if bias == 'right':
                    # If we want the Right side of the boundary, we include the insertion/change
                    offset += len(diff.other_lines) - len(diff.base_lines)
                # Diffs are sorted and non-overlapping from single side
                break
                
            # If diff ends exactly at pos (non-zero width diff)
            elif diff.base_end == base_pos:
                offset += len(diff.other_lines) - len(diff.base_lines)
                # Not breaking yet, there could be an insertion exactly at base_pos
                
            # If diff straddles pos (base_start < base_pos < base_end)
            elif diff.base_start < base_pos:
                # We are strictly inside a diff. 
                # To handle complex partial overlaps correctly, we map to the 
                # boundary of the modified region depending on bias.
                if bias == 'right':
                    # End of range: snap to the end of this modification
                    base_pos = diff.base_end
                    offset += len(diff.other_lines) - len(diff.base_lines)
                else:
                    # Start of range: snap to the start of this modification
                    base_pos = diff.base_start
                break
                
            else:
                # diff.base_start > base_pos
                break
            
        return base_pos + offset
    
    def _create_conflict(
        self,
        region: MergeRegion,
        index: int,
        left_label: str,
        right_label: str,
        base_label: str
    ) -> MergeConflict:
        """Create a MergeConflict from a conflict region."""
        return MergeConflict(
            conflict_id=index,
            base_start=region.base_start,
            base_end=region.base_end,
            left_start=region.left_start,
            left_end=region.left_end,
            right_start=region.right_start,
            right_end=region.right_end,
            base_lines=region.base_lines or [],
            left_lines=region.left_lines or [],
            right_lines=region.right_lines or [],
            resolution=None,
            auto_resolved=self.strategy != MergeStrategy.MANUAL
        )
    
    def _resolve_conflict(
        self,
        region: MergeRegion,
        conflict: MergeConflict
    ) -> list[str]:
        """Resolve a conflict based on the merge strategy."""
        if self.strategy == MergeStrategy.FAVOR_LEFT:
            conflict.resolution = ConflictResolution.USE_LEFT
            return list(region.left_lines or [])
        
        elif self.strategy == MergeStrategy.FAVOR_RIGHT:
            conflict.resolution = ConflictResolution.USE_RIGHT
            return list(region.right_lines or [])
        
        elif self.strategy == MergeStrategy.FAVOR_SHORTER:
            left_len = len(region.left_lines or [])
            right_len = len(region.right_lines or [])
            if left_len <= right_len:
                conflict.resolution = ConflictResolution.USE_LEFT
                return list(region.left_lines or [])
            else:
                conflict.resolution = ConflictResolution.USE_RIGHT
                return list(region.right_lines or [])
        
        elif self.strategy == MergeStrategy.FAVOR_LONGER:
            left_len = len(region.left_lines or [])
            right_len = len(region.right_lines or [])
            if left_len >= right_len:
                conflict.resolution = ConflictResolution.USE_LEFT
                return list(region.left_lines or [])
            else:
                conflict.resolution = ConflictResolution.USE_RIGHT
                return list(region.right_lines or [])
        
        else:  # MANUAL
            # Return conflict markers
            conflict.auto_resolved = False
            lines = []
            lines.append(f"{self.conflict_marker_left}\n")
            lines.extend(region.left_lines or [])
            lines.append(f"{self.conflict_marker_base}\n")
            lines.extend(region.base_lines or [])
            lines.append(f"{self.conflict_marker_sep}\n")
            lines.extend(region.right_lines or [])
            lines.append(f"{self.conflict_marker_right}\n")
            return lines
    
    def _region_type_to_origin(self, region_type: MergeRegionType) -> ThreeWayLineOrigin:
        """Convert region type to line origin."""
        mapping = {
            MergeRegionType.UNCHANGED: ThreeWayLineOrigin.BASE,
            MergeRegionType.LEFT_CHANGED: ThreeWayLineOrigin.LEFT,
            MergeRegionType.RIGHT_CHANGED: ThreeWayLineOrigin.RIGHT,
            MergeRegionType.BOTH_CHANGED_SAME: ThreeWayLineOrigin.BOTH,
            MergeRegionType.CONFLICT: ThreeWayLineOrigin.CONFLICT,
        }
        return mapping.get(region_type, ThreeWayLineOrigin.BASE)
    
    def apply_resolution(
        self,
        result: MergeResult,
        conflict_id: int,
        resolution: ConflictResolution,
        custom_lines: list[str] | None = None
    ) -> MergeResult:
        """
        Apply a resolution to a specific conflict.
        
        Args:
            result: Original merge result
            conflict_id: ID of conflict to resolve
            resolution: Resolution type
            custom_lines: Custom merged lines (for CUSTOM resolution)
            
        Returns:
            New MergeResult with the conflict resolved
        """
        if conflict_id >= len(result.conflicts):
            raise ValueError(f"Invalid conflict ID: {conflict_id}")
        
        conflict = result.conflicts[conflict_id]
        
        # Find the corresponding region
        region_idx = None
        for idx, region in enumerate(result.regions):
            if region.region_type == MergeRegionType.CONFLICT:
                if region.base_start == conflict.base_start:
                    region_idx = idx
                    break
        
        if region_idx is None:
            raise ValueError(f"Could not find region for conflict {conflict_id}")
        
        region = result.regions[region_idx]
        
        # Determine resolved lines
        if resolution == ConflictResolution.USE_LEFT:
            resolved_lines = list(region.left_lines or [])
        elif resolution == ConflictResolution.USE_RIGHT:
            resolved_lines = list(region.right_lines or [])
        elif resolution == ConflictResolution.USE_BASE:
            resolved_lines = list(region.base_lines or [])
        elif resolution == ConflictResolution.USE_BOTH_LEFT_FIRST:
            resolved_lines = list(region.left_lines or []) + list(region.right_lines or [])
        elif resolution == ConflictResolution.USE_BOTH_RIGHT_FIRST:
            resolved_lines = list(region.right_lines or []) + list(region.left_lines or [])
        elif resolution == ConflictResolution.CUSTOM:
            if custom_lines is None:
                raise ValueError("Custom resolution requires custom_lines")
            resolved_lines = custom_lines
        else:
            raise ValueError(f"Unknown resolution: {resolution}")
        
        # Update conflict
        new_conflicts = list(result.conflicts)
        new_conflicts[conflict_id] = MergeConflict(
            conflict_id=conflict.conflict_id,
            base_start=conflict.base_start,
            base_end=conflict.base_end,
            left_start=conflict.left_start,
            left_end=conflict.left_end,
            right_start=conflict.right_start,
            right_end=conflict.right_end,
            base_lines=conflict.base_lines,
            left_lines=conflict.left_lines,
            right_lines=conflict.right_lines,
            resolution=resolution,
            resolved_lines=resolved_lines,
            auto_resolved=False
        )
        
        # Rebuild merged lines
        new_merged_lines = self._rebuild_merged_lines(result.regions, new_conflicts)
        
        # Check if all conflicts resolved
        has_conflicts = any(c.resolution is None for c in new_conflicts)
        
        return MergeResult(
            merged_lines=new_merged_lines,
            conflicts=new_conflicts,
            regions=result.regions,
            three_way_lines=result.three_way_lines,  # Would need rebuild for accuracy
            has_conflicts=has_conflicts,
            auto_resolved_count=result.auto_resolved_count
        )
    
    def _rebuild_merged_lines(
        self,
        regions: list[MergeRegion],
        conflicts: list[MergeConflict]
    ) -> list[str]:
        """Rebuild merged lines after conflict resolution."""
        merged: list[str] = []
        conflict_idx = 0
        
        for region in regions:
            if region.region_type == MergeRegionType.CONFLICT:
                if conflict_idx < len(conflicts):
                    conflict = conflicts[conflict_idx]
                    if conflict.resolution is not None and conflict.resolved_lines:
                        merged.extend(conflict.resolved_lines)
                    else:
                        # Still unresolved - add conflict markers
                        merged.append(f"{self.conflict_marker_left}\n")
                        merged.extend(region.left_lines or [])
                        merged.append(f"{self.conflict_marker_sep}\n")
                        merged.extend(region.right_lines or [])
                        merged.append(f"{self.conflict_marker_right}\n")
                    conflict_idx += 1
            else:
                merged.extend(region.lines)
        
        return merged
    
    def get_conflict_preview(
        self,
        conflict: MergeConflict,
        resolution: ConflictResolution
    ) -> list[str]:
        """Get preview of what a resolution would produce."""
        if resolution == ConflictResolution.USE_LEFT:
            return list(conflict.left_lines)
        elif resolution == ConflictResolution.USE_RIGHT:
            return list(conflict.right_lines)
        elif resolution == ConflictResolution.USE_BASE:
            return list(conflict.base_lines)
        elif resolution == ConflictResolution.USE_BOTH_LEFT_FIRST:
            return list(conflict.left_lines) + list(conflict.right_lines)
        elif resolution == ConflictResolution.USE_BOTH_RIGHT_FIRST:
            return list(conflict.right_lines) + list(conflict.left_lines)
        else:
            return []


class Diff3Merge:
    """
    Alternative diff3-style merge implementation.
    
    This provides a more traditional diff3 output format.
    """
    
    @staticmethod
    def diff3(
        base: Sequence[str],
        left: Sequence[str],
        right: Sequence[str]
    ) -> Iterator[tuple[str, list[str], list[str], list[str]]]:
        """
        Generate diff3-style output.
        
        Yields tuples of (tag, base_lines, left_lines, right_lines)
        where tag is one of: 'ok', 'left', 'right', 'conflict'
        """
        base_list = list(base)
        left_list = list(left)
        right_list = list(right)
        
        # Get LCS with base for both sides
        left_matcher = difflib.SequenceMatcher(None, base_list, left_list)
        right_matcher = difflib.SequenceMatcher(None, base_list, right_list)
        
        left_ops = left_matcher.get_opcodes()
        right_ops = right_matcher.get_opcodes()
        
        # Convert to change ranges
        left_changes = Diff3Merge._ops_to_changes(left_ops)
        right_changes = Diff3Merge._ops_to_changes(right_ops)
        
        # Merge change ranges
        base_pos = 0
        left_pos = 0
        right_pos = 0
        
        while base_pos < len(base_list) or left_pos < len(left_list) or right_pos < len(right_list):
            # Find next change
            left_change = Diff3Merge._find_change_at(left_changes, base_pos)
            right_change = Diff3Merge._find_change_at(right_changes, base_pos)
            
            if left_change is None and right_change is None:
                # No changes - emit unchanged
                if base_pos < len(base_list):
                    next_left = Diff3Merge._next_change_start(left_changes, base_pos)
                    next_right = Diff3Merge._next_change_start(right_changes, base_pos)
                    next_change = min(
                        next_left if next_left is not None else len(base_list),
                        next_right if next_right is not None else len(base_list)
                    )
                    
                    unchanged = base_list[base_pos:next_change]
                    yield ('ok', unchanged, unchanged, unchanged)
                    base_pos = next_change
                    left_pos += len(unchanged)
                    right_pos += len(unchanged)
                else:
                    break
            elif left_change is not None and right_change is None:
                # Left-only change
                b_start, b_end, l_start, l_end = left_change
                yield ('left', base_list[b_start:b_end], left_list[l_start:l_end], base_list[b_start:b_end])
                base_pos = b_end
                left_pos = l_end
                right_pos += (b_end - b_start)
            elif left_change is None and right_change is not None:
                # Right-only change
                b_start, b_end, r_start, r_end = right_change
                yield ('right', base_list[b_start:b_end], base_list[b_start:b_end], right_list[r_start:r_end])
                base_pos = b_end
                left_pos += (b_end - b_start)
                right_pos = r_end
            else:
                # Both changed - check for conflict
                lb_start, lb_end, ll_start, ll_end = left_change
                rb_start, rb_end, rl_start, rl_end = right_change
                
                left_content = left_list[ll_start:ll_end]
                right_content = right_list[rl_start:rl_end]
                
                if left_content == right_content:
                    # Same change on both sides
                    yield ('ok', base_list[lb_start:lb_end], left_content, right_content)
                else:
                    # Conflict
                    yield ('conflict', base_list[lb_start:lb_end], left_content, right_content)
                
                base_pos = max(lb_end, rb_end)
                left_pos = ll_end
                right_pos = rl_end
    
    @staticmethod
    def _ops_to_changes(ops: list) -> list[tuple[int, int, int, int]]:
        """Convert opcodes to change ranges."""
        changes = []
        for tag, b_start, b_end, o_start, o_end in ops:
            if tag != 'equal':
                changes.append((b_start, b_end, o_start, o_end))
        return changes
    
    @staticmethod
    def _find_change_at(changes: list[tuple[int, int, int, int]], base_pos: int) -> tuple[int, int, int, int] | None:
        """Find a change that starts at or contains base_pos."""
        for change in changes:
            if change[0] <= base_pos < change[1] or change[0] == base_pos:
                return change
        return None
    
    @staticmethod
    def _next_change_start(changes: list[tuple[int, int, int, int]], base_pos: int) -> int | None:
        """Find the start of the next change after base_pos."""
        for change in changes:
            if change[0] > base_pos:
                return change[0]
        return None