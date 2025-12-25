"""
Binary file diff engine.

Provides byte-level comparison with:
- Byte offset information
- Hex dump output
- Difference highlighting
- Chunk-based comparison for large files
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Callable, BinaryIO

from app.core.models import (
    BinaryDiffResult,
    BinaryDiffChunk,
    BinaryDiffType,
)


@dataclass
class BinaryCompareOptions:
    """Options for binary comparison."""
    chunk_size: int = 4096
    max_differences: int = 1000  # Stop after this many differences
    context_bytes: int = 16  # Bytes of context around differences
    align_to: int = 16  # Align output to this boundary
    ignore_trailing_nulls: bool = False


@dataclass
class ByteDifference:
    """Represents a single byte difference."""
    offset: int
    left_byte: Optional[int]
    right_byte: Optional[int]
    
    @property
    def is_addition(self) -> bool:
        return self.left_byte is None
    
    @property
    def is_deletion(self) -> bool:
        return self.right_byte is None
    
    @property
    def is_modification(self) -> bool:
        return self.left_byte is not None and self.right_byte is not None


@dataclass
class BinaryRegion:
    """A region of bytes for display."""
    offset: int
    left_bytes: bytes
    right_bytes: bytes
    diff_type: BinaryDiffType
    differences: list[int] = field(default_factory=list)  # Offsets of differing bytes


class BinaryDiffEngine:
    """
    Engine for comparing binary files.
    
    Provides detailed byte-level comparison with hex output.
    """
    
    def __init__(self, options: Optional[BinaryCompareOptions] = None):
        self.options = options or BinaryCompareOptions()
    
    def compare(
        self,
        left_path: Path | str,
        right_path: Path | str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> BinaryDiffResult:
        """
        Compare two binary files.
        
        Args:
            left_path: Path to left file
            right_path: Path to right file
            progress_callback: Called with (bytes_processed, total_bytes)
            
        Returns:
            BinaryDiffResult with comparison details
        """
        left_path = Path(left_path)
        right_path = Path(right_path)
        
        try:
            left_exists = left_path.exists() and left_path.is_file()
            right_exists = right_path.exists() and right_path.is_file()
            
            left_size = left_path.stat().st_size if left_exists else 0
            right_size = right_path.stat().st_size if right_exists else 0
            total_size = max(left_size, right_size)
            
            differences: list[ByteDifference] = []
            chunks: list[BinaryDiffChunk] = []
            
            # Using null context managers if files don't exist
            import contextlib
            
            left_ctx = open(left_path, 'rb') if left_exists else contextlib.nullcontext()
            right_ctx = open(right_path, 'rb') if right_exists else contextlib.nullcontext()
            
            with left_ctx as left_file, right_ctx as right_file:
                offset = 0
                bytes_processed = 0
                
                while True:
                    left_chunk = left_file.read(self.options.chunk_size) if left_exists else b''
                    right_chunk = right_file.read(self.options.chunk_size) if right_exists else b''
                    
                    if not left_chunk and not right_chunk:
                        if offset == 0 and (left_exists or right_exists):
                            # Special case: at least one file exists but is empty
                            # Or we just finished reading
                            pass
                        
                        if offset >= total_size:
                            break
                    
                    # Compare chunks
                    chunk_diffs = self._compare_chunks(
                        left_chunk, right_chunk, offset
                    )
                    
                    if chunk_diffs:
                        differences.extend(chunk_diffs)
                        
                        # Create display chunk
                        chunk = self._create_diff_chunk(
                            left_chunk, right_chunk, offset, chunk_diffs
                        )
                        chunks.append(chunk)
                    
                    chunk_len = max(len(left_chunk), len(right_chunk))
                    offset += chunk_len
                    bytes_processed = offset
                    
                    if progress_callback:
                        progress_callback(bytes_processed, total_size)
                    
                    # If both are empty/EOF, break
                    if not left_chunk and not right_chunk:
                        break

                    # Check limit
                    if len(differences) >= self.options.max_differences:
                        break
            
            is_identical = len(differences) == 0 and left_size == right_size and (left_exists == right_exists)
            
            return BinaryDiffResult(
                left_path=str(left_path) if left_exists else "",
                right_path=str(right_path),
                left_size=left_size,
                right_size=right_size,
                is_identical=is_identical,
                differences=differences,
                chunks=chunks,
                total_differences=len(differences),
                truncated=len(differences) >= self.options.max_differences
            )
        except (PermissionError, OSError) as e:
            logging.error(f"BinaryDiffEngine - Error comparing files {left_path} and {right_path}: {e}")
            raise

    def quick_compare(
        self,
        left_path: Path | str,
        right_path: Path | str
    ) -> tuple[bool, Optional[int]]:
        """
        Quick comparison returning (is_identical, first_diff_offset).
        
        More efficient than full compare when you only need to know
        if files are identical.
        """
        left_path = Path(left_path)
        right_path = Path(right_path)
        
        try:
            left_exists = left_path.exists() and left_path.is_file()
            right_exists = right_path.exists() and right_path.is_file()
            
            if not left_exists or not right_exists:
                if not left_exists and not right_exists:
                    return True, None
                return False, 0

            # Size check
            left_size = left_path.stat().st_size
            right_size = right_path.stat().st_size
            
            if left_size != right_size:
                return False, 0
            
            # Byte-by-byte comparison
            with open(left_path, 'rb') as lf, open(right_path, 'rb') as rf:
                offset = 0
                while True:
                    left_chunk = lf.read(self.options.chunk_size)
                    right_chunk = rf.read(self.options.chunk_size)
                    
                    if left_chunk != right_chunk:
                        # Find exact offset
                        for i, (lb, rb) in enumerate(zip(left_chunk, right_chunk)):
                            if lb != rb:
                                return False, offset + i
                        # Different lengths
                        return False, offset + min(len(left_chunk), len(right_chunk))
                    
                    if not left_chunk:
                        break
                    
                    offset += len(left_chunk)
        except (PermissionError, OSError) as e:
            logging.error(f"BinaryDiffEngine - Error in quick compare for {left_path} and {right_path}: {e}")
            raise
        
        return True, None
    
    def compare_bytes(
        self,
        left_data: bytes,
        right_data: bytes
    ) -> BinaryDiffResult:
        """Compare two byte sequences directly."""
        differences: list[ByteDifference] = []
        
        max_len = max(len(left_data), len(right_data))
        
        for i in range(max_len):
            left_byte = left_data[i] if i < len(left_data) else None
            right_byte = right_data[i] if i < len(right_data) else None
            
            if left_byte != right_byte:
                differences.append(ByteDifference(i, left_byte, right_byte))
                
                if len(differences) >= self.options.max_differences:
                    break
        
        chunks = self._build_chunks_from_differences(
            left_data, right_data, differences
        )
        
        return BinaryDiffResult(
            left_path="<bytes>",
            right_path="<bytes>",
            left_size=len(left_data),
            right_size=len(right_data),
            is_identical=len(differences) == 0,
            differences=differences,
            chunks=chunks,
            total_differences=len(differences),
            truncated=len(differences) >= self.options.max_differences
        )
    
    def hex_dump(
        self,
        data: bytes,
        offset: int = 0,
        bytes_per_line: int = 16
    ) -> Iterator[str]:
        """
        Generate hex dump of binary data.
        
        Yields lines in the format:
        OFFSET: XX XX XX XX ... | ASCII...
        """
        for i in range(0, len(data), bytes_per_line):
            chunk = data[i:i + bytes_per_line]
            
            # Offset
            line = f"{offset + i:08X}: "
            
            # Hex bytes
            hex_parts = []
            for j, byte in enumerate(chunk):
                hex_parts.append(f"{byte:02X}")
                if j == 7:  # Extra space in middle
                    hex_parts.append("")
            
            # Pad if necessary
            while len(hex_parts) < bytes_per_line + 1:
                hex_parts.append("  ")
            
            line += " ".join(hex_parts)
            
            # ASCII representation
            line += " | "
            for byte in chunk:
                if 32 <= byte < 127:
                    line += chr(byte)
                else:
                    line += "."
            
            yield line
    
    def hex_dump_comparison(
        self,
        chunk: BinaryDiffChunk,
        bytes_per_line: int = 16
    ) -> Iterator[tuple[str, str, list[int]]]:
        """
        Generate side-by-side hex dump comparison.
        
        Yields tuples of (left_line, right_line, diff_positions)
        """
        left_data = chunk.left_bytes
        right_data = chunk.right_bytes
        max_len = max(len(left_data), len(right_data))
        
        for i in range(0, max_len, bytes_per_line):
            left_chunk = left_data[i:i + bytes_per_line] if i < len(left_data) else b''
            right_chunk = right_data[i:i + bytes_per_line] if i < len(right_data) else b''
            
            # Find differences in this line
            diff_positions = []
            for j in range(bytes_per_line):
                left_byte = left_chunk[j] if j < len(left_chunk) else None
                right_byte = right_chunk[j] if j < len(right_chunk) else None
                if left_byte != right_byte:
                    diff_positions.append(j)
            
            left_line = self._format_hex_line(left_chunk, chunk.offset + i, bytes_per_line)
            right_line = self._format_hex_line(right_chunk, chunk.offset + i, bytes_per_line)
            
            yield (left_line, right_line, diff_positions)
    
    def _compare_chunks(
        self,
        left: bytes,
        right: bytes,
        offset: int
    ) -> list[ByteDifference]:
        """Compare two chunks and return differences."""
        differences = []
        
        max_len = max(len(left), len(right))
        
        for i in range(max_len):
            left_byte = left[i] if i < len(left) else None
            right_byte = right[i] if i < len(right) else None
            
            if left_byte != right_byte:
                # Handle trailing nulls option
                if self.options.ignore_trailing_nulls:
                    if (left_byte == 0 and right_byte is None) or \
                       (right_byte == 0 and left_byte is None):
                        continue
                
                differences.append(ByteDifference(
                    offset + i, left_byte, right_byte
                ))
        
        return differences
    
    def _create_diff_chunk(
        self,
        left: bytes,
        right: bytes,
        offset: int,
        differences: list[ByteDifference]
    ) -> BinaryDiffChunk:
        """Create a display chunk for a region with differences."""
        # Determine chunk type
        if not left:
            diff_type = BinaryDiffType.ADDED
        elif not right:
            diff_type = BinaryDiffType.REMOVED
        else:
            diff_type = BinaryDiffType.MODIFIED
        
        # Calculate display range with context
        if differences:
            min_offset = min(d.offset for d in differences)
            max_offset = max(d.offset for d in differences)
            
            # Align to boundary
            start = (min_offset // self.options.align_to) * self.options.align_to
            end = ((max_offset // self.options.align_to) + 1) * self.options.align_to
            
            # Add context
            start = max(offset, start - self.options.context_bytes)
            end = min(offset + max(len(left), len(right)), end + self.options.context_bytes)
            
            # Align start
            start = (start // self.options.align_to) * self.options.align_to
        else:
            start = offset
            end = offset + max(len(left), len(right))
        
        # Extract bytes for display
        rel_start = start - offset
        rel_end = end - offset
        
        left_bytes = left[rel_start:rel_end] if rel_start < len(left) else b''
        right_bytes = right[rel_start:rel_end] if rel_start < len(right) else b''
        
        # Relative difference offsets
        diff_offsets = [d.offset - start for d in differences 
                       if start <= d.offset < end]
        
        return BinaryDiffChunk(
            offset=start,
            left_bytes=left_bytes,
            right_bytes=right_bytes,
            diff_type=diff_type,
            diff_offsets=diff_offsets
        )
    
    def _build_chunks_from_differences(
        self,
        left_data: bytes,
        right_data: bytes,
        differences: list[ByteDifference]
    ) -> list[BinaryDiffChunk]:
        """Build display chunks from a list of differences."""
        if not differences:
            return []
        
        chunks = []
        
        # Group differences that are close together
        groups: list[list[ByteDifference]] = []
        current_group: list[ByteDifference] = []
        
        for diff in differences:
            if not current_group:
                current_group = [diff]
            elif diff.offset - current_group[-1].offset <= self.options.align_to * 2:
                current_group.append(diff)
            else:
                groups.append(current_group)
                current_group = [diff]
        
        if current_group:
            groups.append(current_group)
        
        # Create chunk for each group
        for group in groups:
            min_offset = min(d.offset for d in group)
            max_offset = max(d.offset for d in group)
            
            # Align and add context
            start = (min_offset // self.options.align_to) * self.options.align_to
            start = max(0, start - self.options.context_bytes)
            start = (start // self.options.align_to) * self.options.align_to
            
            end = ((max_offset // self.options.align_to) + 1) * self.options.align_to
            end += self.options.context_bytes
            
            left_bytes = left_data[start:end] if start < len(left_data) else b''
            right_bytes = right_data[start:end] if start < len(right_data) else b''
            
            # Determine type
            if all(d.is_addition for d in group):
                diff_type = BinaryDiffType.ADDED
            elif all(d.is_deletion for d in group):
                diff_type = BinaryDiffType.REMOVED
            else:
                diff_type = BinaryDiffType.MODIFIED
            
            chunks.append(BinaryDiffChunk(
                offset=start,
                left_bytes=left_bytes,
                right_bytes=right_bytes,
                diff_type=diff_type,
                diff_offsets=[d.offset - start for d in group]
            ))
        
        return chunks
    
    def _format_hex_line(
        self,
        data: bytes,
        offset: int,
        bytes_per_line: int
    ) -> str:
        """Format a single line of hex dump."""
        if not data:
            return f"{offset:08X}: " + "   " * bytes_per_line + " | "
        
        line = f"{offset:08X}: "
        
        # Hex bytes
        hex_parts = []
        for i in range(bytes_per_line):
            if i < len(data):
                hex_parts.append(f"{data[i]:02X}")
            else:
                hex_parts.append("  ")
        
        line += " ".join(hex_parts)
        
        # ASCII
        line += " | "
        for byte in data:
            if 32 <= byte < 127:
                line += chr(byte)
            else:
                line += "."
        
        return line


class BinaryPatch:
    """
    Create and apply binary patches.
    
    Uses a simple format storing offset, length, and replacement bytes.
    """
    
    MAGIC = b'BPATCH01'
    
    @dataclass
    class PatchEntry:
        """A single patch entry."""
        offset: int
        original_length: int
        original_bytes: bytes
        new_bytes: bytes
    
    @classmethod
    def create_patch(
        cls,
        original: bytes,
        modified: bytes
    ) -> bytes:
        """Create a patch that transforms original into modified."""
        entries: list[cls.PatchEntry] = []
        
        # Find differences
        engine = BinaryDiffEngine()
        result = engine.compare_bytes(original, modified)
        
        # Group consecutive differences
        if result.differences:
            current_start = result.differences[0].offset
            current_orig = []
            current_new = []
            last_offset = current_start - 1
            
            for diff in result.differences:
                if diff.offset > last_offset + 1:
                    # Save current group
                    if current_orig or current_new:
                        entries.append(cls.PatchEntry(
                            offset=current_start,
                            original_length=len(current_orig),
                            original_bytes=bytes(b for b in current_orig if b is not None),
                            new_bytes=bytes(b for b in current_new if b is not None)
                        ))
                    current_start = diff.offset
                    current_orig = []
                    current_new = []
                
                current_orig.append(diff.left_byte)
                current_new.append(diff.right_byte)
                last_offset = diff.offset
            
            # Save last group
            if current_orig or current_new:
                entries.append(cls.PatchEntry(
                    offset=current_start,
                    original_length=len(current_orig),
                    original_bytes=bytes(b for b in current_orig if b is not None),
                    new_bytes=bytes(b for b in current_new if b is not None)
                ))
        
        # Serialize patch
        return cls._serialize_patch(entries, len(original), len(modified))
    
    @classmethod
    def apply_patch(
        cls,
        original: bytes,
        patch: bytes
    ) -> bytes:
        """Apply a patch to transform original data."""
        entries, orig_size, new_size = cls._deserialize_patch(patch)
        
        if len(original) != orig_size:
            raise ValueError(f"Original size mismatch: expected {orig_size}, got {len(original)}")
        
        # Apply patches in reverse order to maintain offsets
        result = bytearray(original)
        
        for entry in reversed(entries):
            # Verify original bytes
            actual = result[entry.offset:entry.offset + entry.original_length]
            if bytes(actual) != entry.original_bytes:
                raise ValueError(f"Original bytes mismatch at offset {entry.offset}")
            
            # Apply replacement
            result[entry.offset:entry.offset + entry.original_length] = entry.new_bytes
        
        if len(result) != new_size:
            raise ValueError(f"Result size mismatch: expected {new_size}, got {len(result)}")
        
        return bytes(result)
    
    @classmethod
    def _serialize_patch(
        cls,
        entries: list[PatchEntry],
        orig_size: int,
        new_size: int
    ) -> bytes:
        """Serialize patch entries to bytes."""
        import struct
        
        data = bytearray(cls.MAGIC)
        
        # Header: original size, new size, entry count
        data.extend(struct.pack('<QQI', orig_size, new_size, len(entries)))
        
        # Entries
        for entry in entries:
            data.extend(struct.pack('<QHH',
                entry.offset,
                entry.original_length,
                len(entry.new_bytes)
            ))
            data.extend(entry.original_bytes)
            data.extend(entry.new_bytes)
        
        return bytes(data)
    
    @classmethod
    def _deserialize_patch(
        cls,
        patch: bytes
    ) -> tuple[list[PatchEntry], int, int]:
        """Deserialize patch from bytes."""
        import struct
        
        if not patch.startswith(cls.MAGIC):
            raise ValueError("Invalid patch format")
        
        pos = len(cls.MAGIC)
        
        # Header
        orig_size, new_size, entry_count = struct.unpack('<QQI', patch[pos:pos + 20])
        pos += 20
        
        entries = []
        for _ in range(entry_count):
            offset, orig_len, new_len = struct.unpack('<QHH', patch[pos:pos + 12])
            pos += 12
            
            orig_bytes = patch[pos:pos + orig_len]
            pos += orig_len
            
            new_bytes = patch[pos:pos + new_len]
            pos += new_len
            
            entries.append(cls.PatchEntry(
                offset=offset,
                original_length=orig_len,
                original_bytes=orig_bytes,
                new_bytes=new_bytes
            ))
        
        return entries, orig_size, new_size