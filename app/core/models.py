"""
Core data models for the file comparison application.

This module defines all data structures used across the application:
- Text diff models
- Binary diff models  
- Image diff models
- Folder comparison models
- Merge and conflict resolution models
- File metadata models

All models are designed to be:
- UI-agnostic (can be used with any frontend)
- Serializable (for caching/persistence)
- Type-hinted for IDE support
- Immutable where practical
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PILImage


# =============================================================================
# Enumerations
# =============================================================================

class DiffLineType(Enum):
    """Type of line in a diff result."""
    UNCHANGED = auto()  # Line exists in both files, identical
    ADDED = auto()      # Line exists only in right/new file
    REMOVED = auto()    # Line exists only in left/old file
    MODIFIED = auto()   # Line changed between files
    CONTEXT = auto()    # Context line (unchanged, shown for context)
    EMPTY = auto()      # Placeholder for alignment


class FileStatus(Enum):
    """Status of a file in folder comparison."""
    IDENTICAL = auto()      # Files are identical
    MODIFIED = auto()       # File exists in both but differs
    LEFT_ONLY = auto()      # File exists only in left folder
    RIGHT_ONLY = auto()     # File exists only in right folder
    TYPE_MISMATCH = auto()  # One is file, other is directory
    ERROR = auto()          # Error accessing file


class FileType(Enum):
    """Type of filesystem entry."""
    FILE = auto()
    DIRECTORY = auto()
    SYMLINK = auto()
    UNKNOWN = auto()


class BinaryDiffType(Enum):
    """Type of binary difference."""
    IDENTICAL = auto()
    ADDED = auto()
    REMOVED = auto()
    MODIFIED = auto()


class MergeRegionType(Enum):
    """Type of region in a three-way merge."""
    UNCHANGED = auto()          # Same in all three versions
    LEFT_CHANGED = auto()       # Changed only in left/ours
    RIGHT_CHANGED = auto()      # Changed only in right/theirs
    BOTH_CHANGED_SAME = auto()  # Both changed identically
    CONFLICT = auto()           # Both changed differently (conflict)


class ConflictResolution(Enum):
    """How a merge conflict was resolved."""
    UNRESOLVED = auto()          # Not yet resolved
    USE_LEFT = auto()            # Use left/ours version
    USE_RIGHT = auto()           # Use right/theirs version
    USE_BASE = auto()            # Use base/original version
    USE_BOTH_LEFT_FIRST = auto() # Concatenate: left then right
    USE_BOTH_RIGHT_FIRST = auto() # Concatenate: right then left
    CUSTOM = auto()              # Custom manual resolution


class ThreeWayLineOrigin(Enum):
    """Origin of a line in three-way merge result."""
    BASE = auto()      # From base version (unchanged)
    LEFT = auto()      # From left/ours version
    RIGHT = auto()     # From right/theirs version
    BOTH = auto()      # Same change on both sides
    CONFLICT = auto()  # Part of an unresolved conflict
    RESOLVED = auto()  # From resolved conflict


class CompareMethod(Enum):
    """Method used to compare files."""
    CONTENT = auto()    # Full content comparison
    SIZE = auto()       # Size only
    HASH = auto()       # Hash comparison
    TIMESTAMP = auto()  # Modification time
    QUICK = auto()      # Size + timestamp


class SyncDirection(Enum):
    """Direction for synchronization."""
    LEFT_TO_RIGHT = auto()
    RIGHT_TO_LEFT = auto()
    BIDIRECTIONAL = auto()


class SyncAction(Enum):
    """Action to take during synchronization."""
    COPY_TO_RIGHT = auto()
    COPY_TO_LEFT = auto()
    DELETE_LEFT = auto()
    DELETE_RIGHT = auto()
    SKIP = auto()
    CONFLICT = auto()


# =============================================================================
# Text Diff Models
# =============================================================================

@dataclass(frozen=True)
class IntralineDiff:
    """
    Character-level difference within a single line.
    
    Used to highlight specific changed portions within modified lines.
    """
    start: int          # Start character index (inclusive)
    end: int            # End character index (exclusive)
    diff_type: str      # 'changed', 'inserted', 'deleted'
    
    @property
    def length(self) -> int:
        """Length of the highlighted region."""
        return self.end - self.start


@dataclass
class DiffLine:
    """
    A single line in a diff result.
    
    Represents one line from either the left or right file,
    with information about its type and position.
    """
    line_type: DiffLineType
    content: str
    left_line_num: Optional[int] = None
    right_line_num: Optional[int] = None
    intraline_diff: Optional[list[IntralineDiff]] = None
    
    @property
    def display_content(self) -> str:
        """Get content without line endings for display."""
        return self.content.rstrip('\r\n')
    
    @property
    def has_intraline_diff(self) -> bool:
        """Check if this line has character-level diff info."""
        return self.intraline_diff is not None and len(self.intraline_diff) > 0
    
    @property
    def line_number(self) -> Optional[int]:
        """Get the applicable line number."""
        return self.left_line_num or self.right_line_num
    
    @property
    def prefix(self) -> str:
        """Get the diff prefix character."""
        prefixes = {
            DiffLineType.UNCHANGED: ' ',
            DiffLineType.ADDED: '+',
            DiffLineType.REMOVED: '-',
            DiffLineType.MODIFIED: '!',
            DiffLineType.CONTEXT: ' ',
            DiffLineType.EMPTY: ' ',
        }
        return prefixes.get(self.line_type, ' ')


@dataclass
class LinePair:
    """
    A pair of lines for side-by-side display.
    
    Links corresponding lines from left and right files.
    One or both may be None for additions/deletions.
    """
    left_line: Optional[DiffLine]
    right_line: Optional[DiffLine]
    pair_type: DiffLineType
    
    @property
    def is_different(self) -> bool:
        """Check if the pair represents a difference."""
        return self.pair_type != DiffLineType.UNCHANGED
    
    @property
    def left_content(self) -> str:
        """Get left line content or empty string."""
        return self.left_line.display_content if self.left_line else ""
    
    @property
    def right_content(self) -> str:
        """Get right line content or empty string."""
        return self.right_line.display_content if self.right_line else ""


@dataclass
class DiffHunk:
    """
    A group of related changes (a "hunk" in unified diff terminology).
    
    Contains contiguous lines that include at least one change,
    plus surrounding context lines.
    """
    left_start: int       # Starting line number in left file (1-indexed)
    left_count: int       # Number of lines from left file
    right_start: int      # Starting line number in right file (1-indexed)
    right_count: int      # Number of lines from right file
    lines: list[DiffLine] = field(default_factory=list)
    section_header: str = ""  # Optional function/section name
    
    @property
    def header(self) -> str:
        """Generate unified diff hunk header."""
        base = f"@@ -{self.left_start},{self.left_count} +{self.right_start},{self.right_count} @@"
        if self.section_header:
            return f"{base} {self.section_header}"
        return base
    
    @property
    def change_count(self) -> int:
        """Count of actual changes (non-context lines)."""
        return sum(1 for line in self.lines 
                   if line.line_type not in (DiffLineType.UNCHANGED, DiffLineType.CONTEXT))
    
    def iter_changes(self) -> Iterator[DiffLine]:
        """Iterate over only the changed lines."""
        for line in self.lines:
            if line.line_type not in (DiffLineType.UNCHANGED, DiffLineType.CONTEXT):
                yield line


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
        """Total number of changed lines."""
        return self.added_lines + self.removed_lines + self.modified_lines
    
    @property
    def similarity_ratio(self) -> float:
        """
        Calculate similarity ratio (0.0 to 1.0).
        
        1.0 means identical, 0.0 means completely different.
        """
        total = max(self.total_lines_left, self.total_lines_right)
        if total == 0:
            return 1.0
        return self.unchanged_lines / total
    
    @property
    def change_ratio(self) -> float:
        """Ratio of changed lines to total lines."""
        return 1.0 - self.similarity_ratio
    
    def __str__(self) -> str:
        return (f"+{self.added_lines} -{self.removed_lines} "
                f"~{self.modified_lines} ={self.unchanged_lines}")


@dataclass
class DiffResult:
    """
    Complete result of a text file diff operation.
    
    Contains all information needed to display the diff
    in various formats (side-by-side, unified, etc.).
    """
    left_path: str
    right_path: str
    lines: list[DiffLine]
    hunks: list[DiffHunk]
    line_pairs: list[LinePair]
    is_identical: bool
    is_binary: bool
    similarity_ratio: float
    statistics: Optional[DiffStatistics] = None
    encoding_left: str = 'utf-8'
    encoding_right: str = 'utf-8'
    left_line_ending: str = '\n'
    right_line_ending: str = '\n'
    error: Optional[str] = None
    
    @property
    def has_differences(self) -> bool:
        """Check if there are any differences."""
        return not self.is_identical
    
    @property
    def hunk_count(self) -> int:
        """Number of change hunks."""
        return len(self.hunks)
    
    def get_unified_diff(self, context: int = 3) -> Iterator[str]:
        """Generate unified diff output."""
        yield f"--- {self.left_path}"
        yield f"+++ {self.right_path}"
        
        for hunk in self.hunks:
            yield hunk.header
            for line in hunk.lines:
                yield f"{line.prefix}{line.display_content}"
    
    def get_statistics_summary(self) -> str:
        """Get human-readable statistics summary."""
        if self.statistics:
            return str(self.statistics)
        return "No statistics available"


# =============================================================================
# Binary Diff Models
# =============================================================================

@dataclass(frozen=True)
class ByteDifference:
    """Represents a single byte difference between files."""
    offset: int                    # Byte offset in file
    left_byte: Optional[int]       # Byte value in left file (None if not present)
    right_byte: Optional[int]      # Byte value in right file (None if not present)
    
    @property
    def is_addition(self) -> bool:
        """True if byte was added (only in right)."""
        return self.left_byte is None and self.right_byte is not None
    
    @property
    def is_deletion(self) -> bool:
        """True if byte was deleted (only in left)."""
        return self.left_byte is not None and self.right_byte is None
    
    @property
    def is_modification(self) -> bool:
        """True if byte was modified."""
        return self.left_byte is not None and self.right_byte is not None
    
    def __str__(self) -> str:
        left = f"{self.left_byte:02X}" if self.left_byte is not None else "--"
        right = f"{self.right_byte:02X}" if self.right_byte is not None else "--"
        return f"0x{self.offset:08X}: {left} -> {right}"


@dataclass
class BinaryDiffChunk:
    """
    A chunk of binary data for display in hex dump format.
    
    Contains bytes from both files for side-by-side comparison.
    """
    offset: int                                    # Starting byte offset
    left_bytes: bytes                              # Bytes from left file
    right_bytes: bytes                             # Bytes from right file
    diff_type: BinaryDiffType                      # Type of difference
    diff_offsets: list[int] = field(default_factory=list)  # Relative offsets of differences
    
    @property
    def length(self) -> int:
        """Length of the chunk."""
        return max(len(self.left_bytes), len(self.right_bytes))
    
    def has_difference_at(self, relative_offset: int) -> bool:
        """Check if there's a difference at the given relative offset."""
        return relative_offset in self.diff_offsets


@dataclass
class BinaryDiffResult:
    """Result of a binary file diff operation."""
    left_path: str
    right_path: str
    left_size: int
    right_size: int
    is_identical: bool
    differences: list[ByteDifference]
    chunks: list[BinaryDiffChunk]
    total_differences: int
    truncated: bool = False          # True if stopped before finding all differences
    first_diff_offset: Optional[int] = None
    left_hash: Optional[str] = None
    right_hash: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def size_difference(self) -> int:
        """Difference in file sizes."""
        return self.right_size - self.left_size
    
    @property
    def size_match(self) -> bool:
        """Check if files have the same size."""
        return self.left_size == self.right_size


# =============================================================================
# Image Diff Models
# =============================================================================

@dataclass
class ImageInfo:
    """Metadata about an image file."""
    width: int
    height: int
    mode: str                    # PIL mode: RGB, RGBA, L, etc.
    format: Optional[str]        # File format: PNG, JPEG, etc.
    file_size: int
    has_alpha: bool
    bit_depth: int = 8
    dpi: Optional[tuple[int, int]] = None
    
    @property
    def dimensions(self) -> tuple[int, int]:
        """Get (width, height) tuple."""
        return (self.width, self.height)
    
    @property
    def pixel_count(self) -> int:
        """Total number of pixels."""
        return self.width * self.height
    
    @property
    def aspect_ratio(self) -> float:
        """Width / height ratio."""
        return self.width / self.height if self.height > 0 else 0
    
    def __str__(self) -> str:
        return f"{self.width}x{self.height} {self.mode} ({self.format})"


@dataclass
class ImageDiffRegion:
    """A rectangular region of difference in an image."""
    x: int                  # Left edge
    y: int                  # Top edge
    width: int              # Width of region
    height: int             # Height of region
    pixel_count: int        # Number of different pixels
    difference_ratio: float # Ratio of different pixels in region
    avg_difference: float = 0.0  # Average color difference
    
    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Get (x1, y1, x2, y2) bounds."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)
    
    @property
    def area(self) -> int:
        """Total area of the region."""
        return self.width * self.height
    
    @property
    def center(self) -> tuple[int, int]:
        """Center point of the region."""
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class ImageDiffResult:
    """Result of an image comparison operation."""
    left_path: str
    right_path: str
    left_info: ImageInfo
    right_info: ImageInfo
    is_identical: bool
    similarity: float                    # 0.0 to 1.0
    left_image: Any                      # Original processed left image
    right_image: Any                     # Original processed right image
    difference_image: Any                # PIL.Image of differences
    visualization_image: Any             # PIL.Image visualization
    regions: list[ImageDiffRegion]       # Regions of difference
    size_match: bool
    different_pixel_count: int = 0
    error: Optional[str] = None
    
    @property
    def difference_percentage(self) -> float:
        """Percentage of pixels that are different."""
        return (1.0 - self.similarity) * 100
    
    @property
    def dimensions_match(self) -> bool:
        """Check if image dimensions match."""
        return self.left_info.dimensions == self.right_info.dimensions


# =============================================================================
# Folder Comparison Models
# =============================================================================

@dataclass
class FileMetadata:
    """Metadata for a file or directory."""
    path: Path
    name: str
    file_type: FileType
    size: int = 0
    modified_time: Optional[datetime] = None
    created_time: Optional[datetime] = None
    permissions: int = 0
    is_hidden: bool = False
    is_readonly: bool = False
    symlink_target: Optional[Path] = None
    hash_value: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def is_file(self) -> bool:
        return self.file_type == FileType.FILE
    
    @property
    def is_directory(self) -> bool:
        return self.file_type == FileType.DIRECTORY
    
    @property
    def is_symlink(self) -> bool:
        return self.file_type == FileType.SYMLINK
    
    @property
    def extension(self) -> str:
        """Get file extension (lowercase, without dot)."""
        if self.is_file:
            return self.path.suffix.lower().lstrip('.')
        return ""
    
    @property
    def size_formatted(self) -> str:
        """Get human-readable file size."""
        size = self.size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


@dataclass
class FileCompareResult:
    """Result of comparing a single file pair."""
    relative_path: str
    left_metadata: Optional[FileMetadata]
    right_metadata: Optional[FileMetadata]
    status: FileStatus
    compare_method: CompareMethod = CompareMethod.CONTENT
    similarity: float = 0.0
    error: Optional[str] = None
    
    @property
    def name(self) -> str:
        """Get the file name."""
        return Path(self.relative_path).name
    
    @property
    def exists_left(self) -> bool:
        return self.left_metadata is not None
    
    @property
    def exists_right(self) -> bool:
        return self.right_metadata is not None
    
    @property
    def exists_both(self) -> bool:
        return self.exists_left and self.exists_right
    
    @property
    def is_identical(self) -> bool:
        return self.status == FileStatus.IDENTICAL
    
    @property
    def is_directory(self) -> bool:
        if self.left_metadata:
            return self.left_metadata.is_directory
        if self.right_metadata:
            return self.right_metadata.is_directory
        return False
    
    @property
    def size_left(self) -> int:
        return self.left_metadata.size if self.left_metadata else 0
    
    @property
    def size_right(self) -> int:
        return self.right_metadata.size if self.right_metadata else 0


@dataclass
class FolderCompareNode:
    """
    A node in the folder comparison tree.
    
    Represents either a file or directory with its comparison status.
    Can have children for directories.
    """
    result: FileCompareResult
    children: list['FolderCompareNode'] = field(default_factory=list)
    parent: Optional['FolderCompareNode'] = None
    expanded: bool = False
    
    @property
    def name(self) -> str:
        return self.result.name
    
    @property
    def status(self) -> FileStatus:
        return self.result.status
    
    @property
    def is_directory(self) -> bool:
        return self.result.is_directory
    
    @property
    def child_count(self) -> int:
        return len(self.children)
    
    @property
    def has_differences(self) -> bool:
        """Check if this node or any children have differences."""
        if self.result.status != FileStatus.IDENTICAL:
            return True
        return any(child.has_differences for child in self.children)
    
    def iter_all(self) -> Iterator['FolderCompareNode']:
        """Iterate over this node and all descendants."""
        yield self
        for child in self.children:
            yield from child.iter_all()
    
    def iter_different(self) -> Iterator['FolderCompareNode']:
        """Iterate over nodes with differences."""
        for node in self.iter_all():
            if node.result.status != FileStatus.IDENTICAL:
                yield node


@dataclass
class FolderCompareResult:
    """Complete result of a folder comparison."""
    left_path: str
    right_path: str
    root: FolderCompareNode
    total_files: int = 0
    total_directories: int = 0
    identical_count: int = 0
    modified_count: int = 0
    left_only_count: int = 0
    right_only_count: int = 0
    error_count: int = 0
    compare_time: float = 0.0        # Time taken in seconds
    error: Optional[str] = None
    
    @property
    def total_differences(self) -> int:
        """Total number of differences found."""
        return self.modified_count + self.left_only_count + self.right_only_count
    
    @property
    def is_identical(self) -> bool:
        """Check if folders are identical."""
        return self.total_differences == 0 and self.error_count == 0
    
    @property
    def summary(self) -> str:
        """Get a summary string."""
        return (f"Files: {self.total_files}, Dirs: {self.total_directories}, "
                f"Identical: {self.identical_count}, Modified: {self.modified_count}, "
                f"Left only: {self.left_only_count}, Right only: {self.right_only_count}")
    
    def iter_by_status(self, status: FileStatus) -> Iterator[FileCompareResult]:
        """Iterate over results with the given status."""
        for node in self.root.iter_all():
            if node.result.status == status:
                yield node.result


@dataclass
class FolderCompareProgress:
    """Progress information for folder comparison."""
    current_path: str
    files_processed: int
    total_files: int
    directories_processed: int
    phase: str = "scanning"  # scanning, comparing, hashing
    
    @property
    def percent(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.files_processed / self.total_files) * 100


# =============================================================================
# Merge Models
# =============================================================================

@dataclass
class MergeRegion:
    """
    A region in a three-way merge result.
    
    Represents a contiguous section of the merge with a specific type.
    """
    region_type: MergeRegionType
    base_start: int           # Start line in base
    base_end: int             # End line in base (exclusive)
    left_start: int           # Start line in left
    left_end: int             # End line in left
    right_start: int          # Start line in right
    right_end: int            # End line in right
    lines: list[str]          # Resulting lines for this region
    base_lines: list[str] = field(default_factory=list)
    left_lines: list[str] = field(default_factory=list)
    right_lines: list[str] = field(default_factory=list)
    
    @property
    def is_conflict(self) -> bool:
        return self.region_type == MergeRegionType.CONFLICT
    
    @property
    def line_count(self) -> int:
        return len(self.lines)


@dataclass
class MergeConflict:
    """
    Represents a merge conflict requiring resolution.
    
    Contains the conflicting content from all three versions
    and tracks resolution status.
    """
    conflict_id: int
    base_start: int
    base_end: int
    left_start: int
    left_end: int
    right_start: int
    right_end: int
    base_lines: list[str]
    left_lines: list[str]
    right_lines: list[str]
    resolution: Optional[ConflictResolution] = None
    resolved_lines: list[str] = field(default_factory=list)
    auto_resolved: bool = False
    
    @property
    def is_resolved(self) -> bool:
        return self.resolution is not None and self.resolution != ConflictResolution.UNRESOLVED
    
    @property
    def base_content(self) -> str:
        return ''.join(self.base_lines)
    
    @property
    def left_content(self) -> str:
        return ''.join(self.left_lines)
    
    @property
    def right_content(self) -> str:
        return ''.join(self.right_lines)
    
    @property
    def resolved_content(self) -> str:
        return ''.join(self.resolved_lines)
    
    def get_preview(self, resolution: ConflictResolution) -> list[str]:
        """Get preview of what a resolution would produce."""
        if resolution == ConflictResolution.USE_LEFT:
            return list(self.left_lines)
        elif resolution == ConflictResolution.USE_RIGHT:
            return list(self.right_lines)
        elif resolution == ConflictResolution.USE_BASE:
            return list(self.base_lines)
        elif resolution == ConflictResolution.USE_BOTH_LEFT_FIRST:
            return list(self.left_lines) + list(self.right_lines)
        elif resolution == ConflictResolution.USE_BOTH_RIGHT_FIRST:
            return list(self.right_lines) + list(self.left_lines)
        else:
            return []


@dataclass
class ThreeWayLine:
    """A single line in a three-way merge view."""
    content: str
    origin: ThreeWayLineOrigin
    conflict_id: Optional[int] = None
    line_number_base: Optional[int] = None
    line_number_left: Optional[int] = None
    line_number_right: Optional[int] = None
    
    @property
    def is_from_conflict(self) -> bool:
        return self.conflict_id is not None


@dataclass
class MergeResult:
    """
    Complete result of a three-way merge operation.
    
    Contains the merged content and all conflict information.
    """
    merged_lines: list[str]
    conflicts: list[MergeConflict]
    regions: list[MergeRegion]
    three_way_lines: list[ThreeWayLine]
    has_conflicts: bool
    auto_resolved_count: int = 0
    base_path: Optional[str] = None
    left_path: Optional[str] = None
    right_path: Optional[str] = None
    
    @property
    def merged_text(self) -> str:
        """Get merged content as a single string."""
        return ''.join(self.merged_lines)
    
    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)
    
    @property
    def unresolved_count(self) -> int:
        """Number of unresolved conflicts."""
        return sum(1 for c in self.conflicts if not c.is_resolved)
    
    @property
    def resolved_count(self) -> int:
        """Number of resolved conflicts."""
        return sum(1 for c in self.conflicts if c.is_resolved)
    
    def is_fully_resolved(self) -> bool:
        """Check if all conflicts have been resolved."""
        return all(c.is_resolved for c in self.conflicts)
    
    def get_conflict(self, conflict_id: int) -> Optional[MergeConflict]:
        """Get a conflict by ID."""
        for conflict in self.conflicts:
            if conflict.conflict_id == conflict_id:
                return conflict
        return None


# =============================================================================
# Sync Models
# =============================================================================

@dataclass
class SyncItem:
    """An item to be synchronized."""
    relative_path: str
    action: SyncAction
    source_path: Optional[Path] = None
    dest_path: Optional[Path] = None
    source_metadata: Optional[FileMetadata] = None
    dest_metadata: Optional[FileMetadata] = None
    reason: str = ""
    
    @property
    def name(self) -> str:
        return Path(self.relative_path).name
    
    @property
    def is_copy(self) -> bool:
        return self.action in (SyncAction.COPY_TO_LEFT, SyncAction.COPY_TO_RIGHT)
    
    @property
    def is_delete(self) -> bool:
        return self.action in (SyncAction.DELETE_LEFT, SyncAction.DELETE_RIGHT)


@dataclass
class SyncPlan:
    """A plan for folder synchronization."""
    items: list[SyncItem]
    direction: SyncDirection
    left_path: str
    right_path: str
    
    @property
    def total_items(self) -> int:
        return len(self.items)
    
    @property
    def copy_count(self) -> int:
        return sum(1 for item in self.items if item.is_copy)
    
    @property
    def delete_count(self) -> int:
        return sum(1 for item in self.items if item.is_delete)
    
    @property
    def conflict_count(self) -> int:
        return sum(1 for item in self.items if item.action == SyncAction.CONFLICT)
    
    @property
    def total_bytes(self) -> int:
        """Total bytes to be copied."""
        total = 0
        for item in self.items:
            if item.is_copy and item.source_metadata:
                total += item.source_metadata.size
        return total
    
    def iter_by_action(self, action: SyncAction) -> Iterator[SyncItem]:
        """Iterate over items with the given action."""
        for item in self.items:
            if item.action == action:
                yield item


@dataclass
class SyncProgress:
    """Progress information for sync operation."""
    current_item: str
    items_completed: int
    total_items: int
    bytes_copied: int
    total_bytes: int
    current_action: str = ""
    
    @property
    def percent_items(self) -> float:
        if self.total_items == 0:
            return 0.0
        return (self.items_completed / self.total_items) * 100
    
    @property
    def percent_bytes(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.bytes_copied / self.total_bytes) * 100


@dataclass
class SyncResult:
    """Result of a synchronization operation."""
    success: bool
    items_processed: int
    items_copied: int
    items_deleted: int
    items_skipped: int
    items_failed: int
    bytes_copied: int
    errors: list[tuple[str, str]] = field(default_factory=list)  # (path, error)
    duration: float = 0.0
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


# =============================================================================
# Filter and Options Models
# =============================================================================

@dataclass
class FileFilter:
    """Filter for including/excluding files."""
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    include_extensions: list[str] = field(default_factory=list)
    exclude_extensions: list[str] = field(default_factory=list)
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    include_hidden: bool = False
    follow_symlinks: bool = False
    
    def matches(self, metadata: FileMetadata) -> bool:
        """Check if a file matches this filter."""
        # Check hidden
        if not self.include_hidden and metadata.is_hidden:
            return False
        
        # Check size
        if self.min_size is not None and metadata.size < self.min_size:
            return False
        if self.max_size is not None and metadata.size > self.max_size:
            return False
        
        # Check extensions
        if self.include_extensions:
            if metadata.extension not in self.include_extensions:
                return False
        if self.exclude_extensions:
            if metadata.extension in self.exclude_extensions:
                return False
        
        # Pattern matching would require fnmatch
        # Simplified for now
        
        return True


@dataclass
class CompareOptions:
    """Options for comparison operations."""
    # Content comparison options
    ignore_whitespace: bool = False
    ignore_case: bool = False
    ignore_blank_lines: bool = False
    ignore_line_endings: bool = True
    
    # Folder comparison options
    recursive: bool = True
    compare_contents: bool = True
    use_hash: bool = False
    quick_compare: bool = True  # Size + mtime only
    
    # Filter
    file_filter: Optional[FileFilter] = None
    
    # Performance
    max_file_size: int = 100 * 1024 * 1024  # 100 MB
    parallel_workers: int = 4
    
    # Output
    context_lines: int = 3


# =============================================================================
# Error Models
# =============================================================================

@dataclass
class CompareError:
    """Error information for comparison operations."""
    path: str
    error_type: str
    message: str
    recoverable: bool = True
    
    def __str__(self) -> str:
        return f"{self.error_type}: {self.path} - {self.message}"


@dataclass
class OperationResult:
    """Generic result for any operation."""
    success: bool
    message: str = ""
    error: Optional[CompareError] = None
    data: Any = None


# =============================================================================
# Session/State Models
# =============================================================================

@dataclass
class CompareSession:
    """Represents a comparison session that can be saved/restored."""
    session_id: str
    created_at: datetime
    left_path: str
    right_path: str
    compare_type: str  # 'file', 'folder', 'image', 'binary'
    options: CompareOptions
    result_summary: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat(),
            'left_path': self.left_path,
            'right_path': self.right_path,
            'compare_type': self.compare_type,
            'result_summary': self.result_summary,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CompareSession':
        """Create from dictionary."""
        return cls(
            session_id=data['session_id'],
            created_at=datetime.fromisoformat(data['created_at']),
            left_path=data['left_path'],
            right_path=data['right_path'],
            compare_type=data['compare_type'],
            options=CompareOptions(),  # Would need proper deserialization
            result_summary=data.get('result_summary'),
        )