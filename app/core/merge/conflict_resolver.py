"""
Conflict resolution utilities and strategies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from app.core.models import (
    MergeConflict,
    ConflictResolution,
    MergeResult,
)


@dataclass
class ResolutionSuggestion:
    """A suggested resolution for a conflict."""
    resolution: ConflictResolution
    confidence: float  # 0.0 to 1.0
    reason: str
    preview_lines: list[str]


class ConflictAnalyzer:
    """Analyzes conflicts to suggest resolutions."""
    
    @staticmethod
    def analyze(conflict: MergeConflict) -> list[ResolutionSuggestion]:
        """
        Analyze a conflict and return suggested resolutions.
        
        Returns suggestions sorted by confidence (highest first).
        """
        suggestions: list[ResolutionSuggestion] = []
        
        # Check for empty sides
        if not conflict.left_lines and conflict.right_lines:
            suggestions.append(ResolutionSuggestion(
                resolution=ConflictResolution.USE_RIGHT,
                confidence=0.8,
                reason="Left side is empty (deletion vs modification)",
                preview_lines=list(conflict.right_lines)
            ))
        
        if not conflict.right_lines and conflict.left_lines:
            suggestions.append(ResolutionSuggestion(
                resolution=ConflictResolution.USE_LEFT,
                confidence=0.8,
                reason="Right side is empty (modification vs deletion)",
                preview_lines=list(conflict.left_lines)
            ))
        
        # Check for whitespace-only differences
        left_stripped = [l.strip() for l in conflict.left_lines]
        right_stripped = [l.strip() for l in conflict.right_lines]
        
        if left_stripped == right_stripped:
            suggestions.append(ResolutionSuggestion(
                resolution=ConflictResolution.USE_LEFT,
                confidence=0.9,
                reason="Difference is whitespace only",
                preview_lines=list(conflict.left_lines)
            ))
        
        # Check if one side is a subset of the other
        left_set = set(conflict.left_lines)
        right_set = set(conflict.right_lines)
        
        if left_set < right_set:
            suggestions.append(ResolutionSuggestion(
                resolution=ConflictResolution.USE_RIGHT,
                confidence=0.6,
                reason="Right side contains all of left plus additions",
                preview_lines=list(conflict.right_lines)
            ))
        elif right_set < left_set:
            suggestions.append(ResolutionSuggestion(
                resolution=ConflictResolution.USE_LEFT,
                confidence=0.6,
                reason="Left side contains all of right plus additions",
                preview_lines=list(conflict.left_lines)
            ))
        
        # Check for reordering
        if sorted(conflict.left_lines) == sorted(conflict.right_lines):
            suggestions.append(ResolutionSuggestion(
                resolution=ConflictResolution.USE_LEFT,
                confidence=0.5,
                reason="Same lines in different order",
                preview_lines=list(conflict.left_lines)
            ))
        
        # Sort by confidence
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        
        return suggestions
    
    @staticmethod
    def similarity_score(left: list[str], right: list[str]) -> float:
        """
        Calculate similarity between two line sequences.
        
        Returns a value between 0.0 (completely different) and 1.0 (identical).
        """
        if not left and not right:
            return 1.0
        if not left or not right:
            return 0.0
        
        # Use Jaccard similarity
        left_set = set(left)
        right_set = set(right)
        
        intersection = len(left_set & right_set)
        union = len(left_set | right_set)
        
        return intersection / union if union > 0 else 0.0


class ConflictMarkerParser:
    """Parse conflict markers in files."""
    
    # Standard Git conflict markers
    MARKER_START = re.compile(r'^<{7}\s*(.*)$')
    MARKER_BASE = re.compile(r'^\|{7}\s*(.*)$')
    MARKER_SEP = re.compile(r'^={7}\s*$')
    MARKER_END = re.compile(r'^>{7}\s*(.*)$')
    
    @classmethod
    def has_conflict_markers(cls, content: str) -> bool:
        """Check if content contains conflict markers."""
        return bool(cls.MARKER_START.search(content, re.MULTILINE))
    
    @classmethod
    def parse_conflicts(cls, lines: list[str]) -> list[dict]:
        """
        Parse conflict markers from lines.
        
        Returns list of conflict dictionaries with:
        - start_line: Line number where conflict starts
        - end_line: Line number where conflict ends
        - left_lines: Lines from left/ours side
        - base_lines: Lines from base (if diff3 style)
        - right_lines: Lines from right/theirs side
        - left_label: Label for left side
        - right_label: Label for right side
        """
        conflicts = []
        i = 0
        
        while i < len(lines):
            match = cls.MARKER_START.match(lines[i])
            if match:
                conflict = {
                    'start_line': i,
                    'left_label': match.group(1).strip() or 'LEFT',
                    'left_lines': [],
                    'base_lines': [],
                    'right_lines': [],
                    'right_label': '',
                    'end_line': i
                }
                
                i += 1
                section = 'left'
                
                while i < len(lines):
                    if cls.MARKER_BASE.match(lines[i]):
                        section = 'base'
                    elif cls.MARKER_SEP.match(lines[i]):
                        section = 'right'
                    elif cls.MARKER_END.match(lines[i]):
                        match_end = cls.MARKER_END.match(lines[i])
                        conflict['right_label'] = match_end.group(1).strip() or 'RIGHT'
                        conflict['end_line'] = i
                        conflicts.append(conflict)
                        break
                    else:
                        if section == 'left':
                            conflict['left_lines'].append(lines[i])
                        elif section == 'base':
                            conflict['base_lines'].append(lines[i])
                        else:
                            conflict['right_lines'].append(lines[i])
                    i += 1
            i += 1
        
        return conflicts
    
    @classmethod
    def remove_conflict_markers(
        cls,
        lines: list[str],
        resolution: ConflictResolution = ConflictResolution.USE_LEFT
    ) -> list[str]:
        """
        Remove conflict markers from lines, applying the given resolution.
        
        Returns cleaned lines with conflicts resolved.
        """
        result = []
        i = 0
        
        while i < len(lines):
            match = cls.MARKER_START.match(lines[i])
            if match:
                left_lines = []
                base_lines = []
                right_lines = []
                section = 'left'
                i += 1
                
                while i < len(lines):
                    if cls.MARKER_BASE.match(lines[i]):
                        section = 'base'
                    elif cls.MARKER_SEP.match(lines[i]):
                        section = 'right'
                    elif cls.MARKER_END.match(lines[i]):
                        # Apply resolution
                        if resolution == ConflictResolution.USE_LEFT:
                            result.extend(left_lines)
                        elif resolution == ConflictResolution.USE_RIGHT:
                            result.extend(right_lines)
                        elif resolution == ConflictResolution.USE_BASE:
                            result.extend(base_lines)
                        elif resolution == ConflictResolution.USE_BOTH_LEFT_FIRST:
                            result.extend(left_lines)
                            result.extend(right_lines)
                        elif resolution == ConflictResolution.USE_BOTH_RIGHT_FIRST:
                            result.extend(right_lines)
                            result.extend(left_lines)
                        break
                    else:
                        if section == 'left':
                            left_lines.append(lines[i])
                        elif section == 'base':
                            base_lines.append(lines[i])
                        else:
                            right_lines.append(lines[i])
                    i += 1
            else:
                result.append(lines[i])
            i += 1
        
        return result


class AutoMerger:
    """
    Automatic merge helper for common scenarios.
    """
    
    def __init__(
        self,
        auto_resolve_whitespace: bool = True,
        auto_resolve_identical: bool = True,
        custom_resolvers: list[Callable[[MergeConflict], Optional[list[str]]]] | None = None
    ):
        self.auto_resolve_whitespace = auto_resolve_whitespace
        self.auto_resolve_identical = auto_resolve_identical
        self.custom_resolvers = custom_resolvers or []
    
    def try_auto_resolve(
        self,
        result: MergeResult
    ) -> tuple[MergeResult, int]:
        """
        Try to automatically resolve conflicts.
        
        Returns:
            Tuple of (updated result, number of conflicts resolved)
        """
        from app.core.merge.three_way import ThreeWayMergeEngine
        
        engine = ThreeWayMergeEngine()
        resolved_count = 0
        current_result = result
        
        for conflict in result.conflicts:
            if conflict.resolution is not None:
                continue
            
            resolution = self._try_resolve_conflict(conflict)
            if resolution is not None:
                resolution_type, resolved_lines = resolution
                current_result = engine.apply_resolution(
                    current_result,
                    conflict.conflict_id,
                    resolution_type,
                    resolved_lines if resolution_type == ConflictResolution.CUSTOM else None
                )
                resolved_count += 1
        
        return current_result, resolved_count
    
    def _try_resolve_conflict(
        self,
        conflict: MergeConflict
    ) -> tuple[ConflictResolution, list[str]] | None:
        """Try to automatically resolve a single conflict."""
        # Try whitespace resolution
        if self.auto_resolve_whitespace:
            left_stripped = [l.rstrip() for l in conflict.left_lines]
            right_stripped = [l.rstrip() for l in conflict.right_lines]
            
            if left_stripped == right_stripped:
                return (ConflictResolution.USE_LEFT, [])
        
        # Try identical resolution
        if self.auto_resolve_identical:
            if conflict.left_lines == conflict.right_lines:
                return (ConflictResolution.USE_LEFT, [])
        
        # Try custom resolvers
        for resolver in self.custom_resolvers:
            resolved_lines = resolver(conflict)
            if resolved_lines is not None:
                return (ConflictResolution.CUSTOM, resolved_lines)
        
        return None