"""
Text file diff engine.

Provides line-by-line comparison with support for:
- Multiple diff algorithms
- Whitespace handling options
- Case sensitivity
- Line ending normalization
- Intraline (word/character) highlighting
- Unified and side-by-side output formats
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator, Optional, Sequence, Callable

from app.core.models import (
    DiffLine,
    DiffLineType,
    DiffResult,
    DiffHunk,
    IntralineDiff,
    LinePair,
)


class DiffAlgorithm(Enum):
    """Available diff algorithms."""
    MYERS = auto()          # Standard Myers algorithm (difflib default)
    PATIENCE = auto()       # Patience diff - better for code
    HISTOGRAM = auto()      # Histogram diff - good for large files
    MINIMAL = auto()        # Minimal diff - smallest possible diff


class WhitespaceMode(Enum):
    """Whitespace handling modes."""
    EXACT = auto()          # Compare whitespace exactly
    IGNORE_TRAILING = auto()  # Ignore trailing whitespace
    IGNORE_LEADING = auto()   # Ignore leading whitespace
    IGNORE_ALL = auto()       # Ignore all whitespace
    NORMALIZE = auto()        # Normalize whitespace (collapse multiple to single)


@dataclass
class TextCompareOptions:
    """Options for text comparison."""
    algorithm: DiffAlgorithm = DiffAlgorithm.MYERS
    ignore_case: bool = False
    whitespace_mode: WhitespaceMode = WhitespaceMode.EXACT
    ignore_blank_lines: bool = False
    ignore_line_endings: bool = True
    context_lines: int = 3
    compute_intraline: bool = True
    intraline_char_threshold: int = 200  # Max line length for char-level diff
    junk_filter: Optional[Callable[[str], bool]] = None
    
    def normalize_line(self, line: str) -> str:
        """Normalize a line according to options."""
        result = line
        
        # Handle line endings
        if self.ignore_line_endings:
            result = result.rstrip('\r\n')
        
        # Handle whitespace
        if self.whitespace_mode == WhitespaceMode.IGNORE_TRAILING:
            result = result.rstrip()
        elif self.whitespace_mode == WhitespaceMode.IGNORE_LEADING:
            result = result.lstrip()
        elif self.whitespace_mode == WhitespaceMode.IGNORE_ALL:
            result = ''.join(result.split())
        elif self.whitespace_mode == WhitespaceMode.NORMALIZE:
            result = ' '.join(result.split())
        
        # Handle case
        if self.ignore_case:
            result = result.lower()
        
        return result


@dataclass
class DiffStatistics:
    """Statistics about a diff result."""
    total_lines_left: int = 0
    total_lines_right: int = 0
    added_lines: int = 0
    removed_lines: int = 0
    modified_lines: int = 0
    unchanged_lines: int = 0
    
    @property
    def total_changes(self) -> int:
        return self.added_lines + self.removed_lines + self.modified_lines
    
    @property
    def similarity_ratio(self) -> float:
        """Calculate similarity ratio (0.0 to 1.0)."""
        total = max(self.total_lines_left, self.total_lines_right)
        if total == 0:
            return 1.0
        return self.unchanged_lines / total


class TextDiffEngine:
    """
    Engine for comparing text files.
    
    Supports multiple algorithms and extensive options for
    controlling comparison behavior.
    """
    
    def __init__(self, options: Optional[TextCompareOptions] = None):
        self.options = options or TextCompareOptions()
    
    def compare(
        self,
        left_lines: Sequence[str],
        right_lines: Sequence[str],
        left_label: str = "left",
        right_label: str = "right"
    ) -> DiffResult:
        """
        Compare two sequences of lines.
        
        Args:
            left_lines: Lines from the left/original file
            right_lines: Lines from the right/modified file
            left_label: Label for left file (used in unified diff)
            right_label: Label for right file
            
        Returns:
            DiffResult containing all diff information
        """
        # Convert to lists and optionally filter blank lines
        left = list(left_lines)
        right = list(right_lines)
        
        if self.options.ignore_blank_lines:
            left, left_map = self._filter_blank_lines(left)
            right, right_map = self._filter_blank_lines(right)
        else:
            left_map = {i: i for i in range(len(left))}
            right_map = {i: i for i in range(len(right))}
        
        # Create normalized versions for comparison
        left_normalized = [self.options.normalize_line(l) for l in left]
        right_normalized = [self.options.normalize_line(r) for r in right]
        
        # Get diff opcodes
        opcodes = self._get_opcodes(left_normalized, right_normalized)
        
        # Build diff lines and hunks
        diff_lines: list[DiffLine] = []
        line_pairs: list[LinePair] = []
        hunks: list[DiffHunk] = []
        
        current_hunk_lines: list[DiffLine] = []
        hunk_start_left = 0
        hunk_start_right = 0
        in_hunk = False
        context_buffer: list[DiffLine] = []
        
        for tag, i1, i2, j1, j2 in opcodes:
            if tag == 'equal':
                equal_lines = self._create_equal_lines(left, i1, i2, j1)
                
                # Handle context for hunks
                if in_hunk:
                    # Add leading context to current hunk
                    context_to_add = equal_lines[:self.options.context_lines]
                    current_hunk_lines.extend(context_to_add)
                    
                    # Check if we should close the hunk
                    if len(equal_lines) > self.options.context_lines * 2:
                        # Close current hunk
                        hunks.append(self._create_hunk(
                            current_hunk_lines, hunk_start_left, hunk_start_right
                        ))
                        current_hunk_lines = []
                        in_hunk = False
                        
                        # Buffer trailing context for next hunk
                        context_buffer = equal_lines[-self.options.context_lines:]
                    else:
                        # Gap is small, keep in same hunk
                        current_hunk_lines.extend(equal_lines[self.options.context_lines:])
                else:
                    # Buffer context for potential next hunk
                    context_buffer = equal_lines[-self.options.context_lines:] if equal_lines else []
                
                diff_lines.extend(equal_lines)
                for line in equal_lines:
                    line_pairs.append(LinePair(
                        left_line=line,
                        right_line=line,
                        pair_type=DiffLineType.UNCHANGED
                    ))
                    
            elif tag == 'replace':
                # Modified lines - pair them up
                if not in_hunk:
                    in_hunk = True
                    hunk_start_left = i1
                    hunk_start_right = j1
                    current_hunk_lines.extend(context_buffer)
                    context_buffer = []
                
                modified_pairs = self._create_modified_lines(
                    left, right, i1, i2, j1, j2
                )
                
                for left_line, right_line in modified_pairs:
                    if left_line:
                        diff_lines.append(left_line)
                        current_hunk_lines.append(left_line)
                    if right_line:
                        diff_lines.append(right_line)
                        current_hunk_lines.append(right_line)
                    
                    line_pairs.append(LinePair(
                        left_line=left_line,
                        right_line=right_line,
                        pair_type=DiffLineType.MODIFIED
                    ))
                    
            elif tag == 'delete':
                if not in_hunk:
                    in_hunk = True
                    hunk_start_left = i1
                    hunk_start_right = j1
                    current_hunk_lines.extend(context_buffer)
                    context_buffer = []
                
                removed_lines = self._create_removed_lines(left, i1, i2)
                diff_lines.extend(removed_lines)
                current_hunk_lines.extend(removed_lines)
                
                for line in removed_lines:
                    line_pairs.append(LinePair(
                        left_line=line,
                        right_line=None,
                        pair_type=DiffLineType.REMOVED
                    ))
                    
            elif tag == 'insert':
                if not in_hunk:
                    in_hunk = True
                    hunk_start_left = i1
                    hunk_start_right = j1
                    current_hunk_lines.extend(context_buffer)
                    context_buffer = []
                
                added_lines = self._create_added_lines(right, j1, j2, i1)
                diff_lines.extend(added_lines)
                current_hunk_lines.extend(added_lines)
                
                for line in added_lines:
                    line_pairs.append(LinePair(
                        left_line=None,
                        right_line=line,
                        pair_type=DiffLineType.ADDED
                    ))
        
        # Close final hunk
        if in_hunk and current_hunk_lines:
            hunks.append(self._create_hunk(
                current_hunk_lines, hunk_start_left, hunk_start_right
            ))
        
        # Calculate statistics
        stats = self._calculate_statistics(diff_lines, len(left_lines), len(right_lines))
        
        # Calculate similarity
        matcher = difflib.SequenceMatcher(None, left_normalized, right_normalized)
        similarity = matcher.ratio()
        
        return DiffResult(
            left_path=left_label,
            right_path=right_label,
            lines=diff_lines,
            hunks=hunks,
            line_pairs=line_pairs,
            is_identical=(len(hunks) == 0),
            is_binary=False,
            similarity_ratio=similarity,
            statistics=stats
        )
    
    def compare_files(
        self,
        left_path: str,
        right_path: str,
        encoding: str = 'utf-8'
    ) -> DiffResult:
        """
        Compare two files by path.
        
        Args:
            left_path: Path to left file
            right_path: Path to right file
            encoding: File encoding
            
        Returns:
            DiffResult for the files
        """
        try:
            with open(left_path, 'r', encoding=encoding, errors='replace') as f:
                left_lines = f.readlines()
            
            with open(right_path, 'r', encoding=encoding, errors='replace') as f:
                right_lines = f.readlines()
            
            return self.compare(left_lines, right_lines, left_path, right_path)
        except (PermissionError, OSError) as e:
            # Create an error result
            return DiffResult(
                left_label=left_path,
                right_label=right_path,
                hunks=[],
                stats=DiffStatistics(),
                error=f"Error reading files: {str(e)}"
            )
    
    def unified_diff(
        self,
        left_lines: Sequence[str],
        right_lines: Sequence[str],
        left_label: str = "left",
        right_label: str = "right",
        lineterm: str = '\n'
    ) -> Iterator[str]:
        """
        Generate unified diff output.
        
        Compatible with standard diff -u format.
        """
        left = list(left_lines)
        right = list(right_lines)
        
        # Normalize for comparison if needed
        if self.options.ignore_line_endings:
            left_cmp = [l.rstrip('\r\n') for l in left]
            right_cmp = [r.rstrip('\r\n') for r in right]
        else:
            left_cmp = left
            right_cmp = right
        
        yield from difflib.unified_diff(
            left_cmp,
            right_cmp,
            fromfile=left_label,
            tofile=right_label,
            lineterm=lineterm,
            n=self.options.context_lines
        )
    
    def context_diff(
        self,
        left_lines: Sequence[str],
        right_lines: Sequence[str],
        left_label: str = "left",
        right_label: str = "right",
        lineterm: str = '\n'
    ) -> Iterator[str]:
        """Generate context diff output (diff -c format)."""
        left = [l.rstrip('\r\n') for l in left_lines]
        right = [r.rstrip('\r\n') for r in right_lines]
        
        yield from difflib.context_diff(
            left,
            right,
            fromfile=left_label,
            tofile=right_label,
            lineterm=lineterm,
            n=self.options.context_lines
        )
    
    def compute_intraline_diff(
        self,
        left_line: str,
        right_line: str
    ) -> tuple[list[IntralineDiff], list[IntralineDiff]]:
        """
        Compute character-level differences within a line pair.
        
        Returns:
            Tuple of (left_highlights, right_highlights)
        """
        # Strip line endings for comparison
        left = left_line.rstrip('\r\n')
        right = right_line.rstrip('\r\n')
        
        # Skip if lines are too long
        if (len(left) > self.options.intraline_char_threshold or
            len(right) > self.options.intraline_char_threshold):
            return (
                [IntralineDiff(0, len(left), 'changed')],
                [IntralineDiff(0, len(right), 'changed')]
            )
        
        left_diffs: list[IntralineDiff] = []
        right_diffs: list[IntralineDiff] = []
        
        # Use word-level diff first, then character-level for changed words
        left_words = self._tokenize(left)
        right_words = self._tokenize(right)
        
        matcher = difflib.SequenceMatcher(None, left_words, right_words)
        
        left_pos = 0
        right_pos = 0
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            # Calculate character positions
            left_start = sum(len(w) for w in left_words[:i1])
            left_end = sum(len(w) for w in left_words[:i2])
            right_start = sum(len(w) for w in right_words[:j1])
            right_end = sum(len(w) for w in right_words[:j2])
            
            if tag == 'equal':
                pass  # No highlighting needed
            elif tag == 'replace':
                left_diffs.append(IntralineDiff(left_start, left_end, 'changed'))
                right_diffs.append(IntralineDiff(right_start, right_end, 'changed'))
            elif tag == 'delete':
                left_diffs.append(IntralineDiff(left_start, left_end, 'deleted'))
            elif tag == 'insert':
                right_diffs.append(IntralineDiff(right_start, right_end, 'inserted'))
        
        return left_diffs, right_diffs
    
    def _get_opcodes(
        self,
        left: list[str],
        right: list[str]
    ) -> list[tuple[str, int, int, int, int]]:
        """Get diff opcodes using the configured algorithm."""
        if self.options.algorithm == DiffAlgorithm.PATIENCE:
            return self._patience_diff(left, right)
        elif self.options.algorithm == DiffAlgorithm.HISTOGRAM:
            return self._histogram_diff(left, right)
        elif self.options.algorithm == DiffAlgorithm.MINIMAL:
            matcher = difflib.SequenceMatcher(
                self.options.junk_filter, left, right, autojunk=False
            )
            return matcher.get_opcodes()
        else:  # MYERS (default)
            matcher = difflib.SequenceMatcher(
                self.options.junk_filter, left, right
            )
            return matcher.get_opcodes()
    
    def _patience_diff(
        self,
        left: list[str],
        right: list[str]
    ) -> list[tuple[str, int, int, int, int]]:
        """
        Patience diff algorithm.
        
        Better for code because it anchors on unique lines.
        """
        # Find unique lines in both sequences
        left_unique = {}
        right_unique = {}
        
        for i, line in enumerate(left):
            if line in left_unique:
                left_unique[line] = None  # Mark as non-unique
            else:
                left_unique[line] = i
        
        for i, line in enumerate(right):
            if line in right_unique:
                right_unique[line] = None
            else:
                right_unique[line] = i
        
        # Find common unique lines
        common = []
        for line, left_idx in left_unique.items():
            if left_idx is not None and line in right_unique:
                right_idx = right_unique[line]
                if right_idx is not None:
                    common.append((left_idx, right_idx, line))
        
        # Sort by position in left
        common.sort()
        
        # Find LIS (Longest Increasing Subsequence) by right indices
        if common:
            lis = self._find_lis([c[1] for c in common])
            anchors = [common[i] for i in lis]
        else:
            anchors = []
        
        # Build opcodes using anchors
        return self._build_opcodes_from_anchors(left, right, anchors)
    
    def _histogram_diff(
        self,
        left: list[str],
        right: list[str]
    ) -> list[tuple[str, int, int, int, int]]:
        """
        Histogram diff algorithm.
        
        Uses line frequency to find good anchors.
        """
        # Count line frequencies
        from collections import Counter
        
        left_counts = Counter(left)
        right_counts = Counter(right)
        
        # Find low-frequency common lines as anchors
        common_lines = set(left_counts.keys()) & set(right_counts.keys())
        
        # Score by combined frequency (lower is better)
        scored = [
            (line, left_counts[line] + right_counts[line])
            for line in common_lines
        ]
        scored.sort(key=lambda x: x[1])
        
        # Use low-frequency lines as anchors
        anchor_lines = set(line for line, count in scored if count <= 3)
        
        if not anchor_lines:
            # Fall back to standard diff
            matcher = difflib.SequenceMatcher(None, left, right)
            return matcher.get_opcodes()
        
        # Find anchor positions
        anchors = []
        for i, line in enumerate(left):
            if line in anchor_lines:
                # Find matching position in right
                for j, rline in enumerate(right):
                    if rline == line:
                        anchors.append((i, j, line))
                        anchor_lines.discard(line)  # Only use first occurrence
                        break
        
        anchors.sort()
        
        # Filter to maintain order
        if anchors:
            lis = self._find_lis([a[1] for a in anchors])
            anchors = [anchors[i] for i in lis]
        
        return self._build_opcodes_from_anchors(left, right, anchors)
    
    def _find_lis(self, sequence: list[int]) -> list[int]:
        """Find indices of Longest Increasing Subsequence."""
        if not sequence:
            return []
        
        n = len(sequence)
        # dp[i] = smallest ending element for LIS of length i+1
        dp = []
        # parent[i] = index of previous element in LIS ending at i
        parent = [-1] * n
        # indices[i] = index in original sequence for dp[i]
        indices = []
        
        for i, val in enumerate(sequence):
            # Binary search for position
            lo, hi = 0, len(dp)
            while lo < hi:
                mid = (lo + hi) // 2
                if dp[mid] < val:
                    lo = mid + 1
                else:
                    hi = mid
            
            if lo == len(dp):
                dp.append(val)
                indices.append(i)
            else:
                dp[lo] = val
                indices[lo] = i
            
            parent[i] = indices[lo - 1] if lo > 0 else -1
        
        # Reconstruct LIS
        result = []
        idx = indices[-1] if indices else -1
        while idx >= 0:
            result.append(idx)
            idx = parent[idx]
        
        return list(reversed(result))
    
    def _build_opcodes_from_anchors(
        self,
        left: list[str],
        right: list[str],
        anchors: list[tuple[int, int, str]]
    ) -> list[tuple[str, int, int, int, int]]:
        """Build opcodes using anchor points."""
        opcodes = []
        
        left_pos = 0
        right_pos = 0
        
        for left_idx, right_idx, _ in anchors:
            # Handle region before anchor
            if left_idx > left_pos or right_idx > right_pos:
                # Recursively diff the gap
                gap_left = left[left_pos:left_idx]
                gap_right = right[right_pos:right_idx]
                
                if gap_left and gap_right:
                    matcher = difflib.SequenceMatcher(None, gap_left, gap_right)
                    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                        opcodes.append((
                            tag,
                            left_pos + i1,
                            left_pos + i2,
                            right_pos + j1,
                            right_pos + j2
                        ))
                elif gap_left:
                    opcodes.append(('delete', left_pos, left_idx, right_pos, right_pos))
                elif gap_right:
                    opcodes.append(('insert', left_pos, left_pos, right_pos, right_idx))
            
            # Add anchor as equal
            opcodes.append(('equal', left_idx, left_idx + 1, right_idx, right_idx + 1))
            
            left_pos = left_idx + 1
            right_pos = right_idx + 1
        
        # Handle remaining content
        if left_pos < len(left) or right_pos < len(right):
            gap_left = left[left_pos:]
            gap_right = right[right_pos:]
            
            if gap_left and gap_right:
                matcher = difflib.SequenceMatcher(None, gap_left, gap_right)
                for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                    opcodes.append((
                        tag,
                        left_pos + i1,
                        left_pos + i2,
                        right_pos + j1,
                        right_pos + j2
                    ))
            elif gap_left:
                opcodes.append(('delete', left_pos, len(left), right_pos, right_pos))
            elif gap_right:
                opcodes.append(('insert', left_pos, left_pos, right_pos, len(right)))
        
        return opcodes
    
    def _filter_blank_lines(
        self,
        lines: list[str]
    ) -> tuple[list[str], dict[int, int]]:
        """Filter out blank lines, returning filtered list and index mapping."""
        filtered = []
        mapping = {}
        
        for i, line in enumerate(lines):
            if line.strip():
                mapping[len(filtered)] = i
                filtered.append(line)
        
        return filtered, mapping
    
    def _create_equal_lines(
        self,
        lines: list[str],
        start: int,
        end: int,
        right_start: int
    ) -> list[DiffLine]:
        """Create DiffLine objects for equal lines."""
        result = []
        for i, idx in enumerate(range(start, end)):
            result.append(DiffLine(
                line_type=DiffLineType.UNCHANGED,
                content=lines[idx],
                left_line_num=idx + 1,
                right_line_num=right_start + i + 1
            ))
        return result
    
    def _create_removed_lines(
        self,
        lines: list[str],
        start: int,
        end: int
    ) -> list[DiffLine]:
        """Create DiffLine objects for removed lines."""
        result = []
        for idx in range(start, end):
            result.append(DiffLine(
                line_type=DiffLineType.REMOVED,
                content=lines[idx],
                left_line_num=idx + 1,
                right_line_num=None
            ))
        return result
    
    def _create_added_lines(
        self,
        lines: list[str],
        start: int,
        end: int,
        left_pos: int
    ) -> list[DiffLine]:
        """Create DiffLine objects for added lines."""
        result = []
        for idx in range(start, end):
            result.append(DiffLine(
                line_type=DiffLineType.ADDED,
                content=lines[idx],
                left_line_num=None,
                right_line_num=idx + 1
            ))
        return result
    
    def _create_modified_lines(
        self,
        left: list[str],
        right: list[str],
        i1: int,
        i2: int,
        j1: int,
        j2: int
    ) -> list[tuple[Optional[DiffLine], Optional[DiffLine]]]:
        """Create paired DiffLine objects for modified lines."""
        pairs = []
        
        left_lines = left[i1:i2]
        right_lines = right[j1:j2]
        
        # Pair up lines
        max_len = max(len(left_lines), len(right_lines))
        
        for i in range(max_len):
            left_line = None
            right_line = None
            
            if i < len(left_lines):
                # Compute intraline diff if we have both
                intraline_left = None
                intraline_right = None
                
                if self.options.compute_intraline and i < len(right_lines):
                    intraline_left, intraline_right = self.compute_intraline_diff(
                        left_lines[i], right_lines[i]
                    )
                
                left_line = DiffLine(
                    line_type=DiffLineType.MODIFIED,
                    content=left_lines[i],
                    left_line_num=i1 + i + 1,
                    right_line_num=None,
                    intraline_diff=intraline_left
                )
            
            if i < len(right_lines):
                intraline_right = None
                if self.options.compute_intraline and i < len(left_lines):
                    _, intraline_right = self.compute_intraline_diff(
                        left_lines[i], right_lines[i]
                    )
                
                right_line = DiffLine(
                    line_type=DiffLineType.MODIFIED,
                    content=right_lines[i],
                    left_line_num=None,
                    right_line_num=j1 + i + 1,
                    intraline_diff=intraline_right
                )
            
            pairs.append((left_line, right_line))
        
        return pairs
    
    def _create_hunk(
        self,
        lines: list[DiffLine],
        start_left: int,
        start_right: int
    ) -> DiffHunk:
        """Create a DiffHunk from a list of lines."""
        left_count = sum(1 for l in lines if l.left_line_num is not None)
        right_count = sum(1 for l in lines if l.right_line_num is not None)
        
        return DiffHunk(
            left_start=start_left + 1,  # 1-indexed
            left_count=left_count,
            right_start=start_right + 1,
            right_count=right_count,
            lines=lines
        )
    
    def _calculate_statistics(
        self,
        lines: list[DiffLine],
        total_left: int,
        total_right: int
    ) -> DiffStatistics:
        """Calculate diff statistics from lines."""
        stats = DiffStatistics(
            total_lines_left=total_left,
            total_lines_right=total_right
        )
        
        for line in lines:
            if line.line_type == DiffLineType.UNCHANGED:
                stats.unchanged_lines += 1
            elif line.line_type == DiffLineType.ADDED:
                stats.added_lines += 1
            elif line.line_type == DiffLineType.REMOVED:
                stats.removed_lines += 1
            elif line.line_type == DiffLineType.MODIFIED:
                stats.modified_lines += 1
        
        # Adjust for double-counting of modified lines
        stats.modified_lines //= 2
        
        return stats
    
    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words and whitespace."""
        tokens = []
        pattern = re.compile(r'(\s+|\S+)')
        
        for match in pattern.finditer(text):
            tokens.append(match.group())
        
        return tokens


class SideBySideFormatter:
    """Format diff results for side-by-side display."""
    
    def __init__(self, width: int = 80, tab_size: int = 4):
        self.width = width
        self.tab_size = tab_size
    
    def format(self, result: DiffResult) -> Iterator[tuple[str, str, str]]:
        """
        Format diff for side-by-side display.
        
        Yields tuples of (left_line, separator, right_line)
        """
        for pair in result.line_pairs:
            left = self._format_line(pair.left_line) if pair.left_line else ""
            right = self._format_line(pair.right_line) if pair.right_line else ""
            
            if pair.pair_type == DiffLineType.UNCHANGED:
                sep = "   "
            elif pair.pair_type == DiffLineType.ADDED:
                sep = " > "
            elif pair.pair_type == DiffLineType.REMOVED:
                sep = " < "
            else:
                sep = " | "
            
            yield (left, sep, right)
    
    def _format_line(self, line: DiffLine) -> str:
        """Format a single line with line number."""
        content = line.content.rstrip('\r\n')
        content = content.replace('\t', ' ' * self.tab_size)
        
        line_num = line.left_line_num or line.right_line_num or 0
        prefix = f"{line_num:4d}: "
        
        max_content = self.width - len(prefix)
        if len(content) > max_content:
            content = content[:max_content - 3] + "..."
        
        return prefix + content