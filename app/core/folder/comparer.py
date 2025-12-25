"""
Folder comparison engine.

Compares two directory trees and identifies:
- Identical files
- Modified files
- Files only in left
- Files only in right
- Type mismatches (file vs directory)
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional
import time
import logging

from app.core.models import (
    FileMetadata,
    FileStatus,
    FileType,
    FileCompareResult,
    FolderCompareNode,
    FolderCompareResult,
    FolderCompareProgress,
    CompareMethod,
)
from app.core.folder.scanner import FolderScanner, ScanOptions, ScanResult


@dataclass
class CompareOptions:
    """Options for folder comparison."""
    # Comparison method
    compare_contents: bool = True
    use_hash: bool = True
    hash_algorithm: str = 'sha256'
    quick_compare: bool = True  # Use size + mtime before content
    
    # Content comparison options
    ignore_line_endings: bool = True
    ignore_whitespace: bool = False
    ignore_case: bool = False
    
    # Scanning options
    recursive: bool = True
    follow_symlinks: bool = False
    include_hidden: bool = False
    
    # Filtering
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=lambda: [
        '.git', '.svn', '__pycache__', 'node_modules',
        '.DS_Store', 'Thumbs.db', '*.pyc',
    ])
    
    # Performance
    max_file_size: int = 100 * 1024 * 1024  # 100 MB
    parallel_workers: int = 8
    chunk_size: int = 65536
    
    # Error handling
    ignore_errors: bool = True


@dataclass
class CompareProgress:
    """Progress of comparison operation."""
    phase: str  # 'scanning_left', 'scanning_right', 'comparing'
    current_path: str
    items_processed: int
    total_items: int
    percent: float


class FolderComparer:
    """
    Compares two folder trees.
    
    Uses configurable comparison strategies:
    - Quick compare: size + modification time
    - Content compare: byte-by-byte
    - Hash compare: SHA-256 or other hash
    """
    
    def __init__(self, options: Optional[CompareOptions] = None):
        self.options = options or CompareOptions()
        self._cancelled = False
        self._progress_callback: Optional[Callable[[CompareProgress], None]] = None
    
    def compare(
        self,
        left_path: Path | str,
        right_path: Path | str,
        progress_callback: Optional[Callable[[CompareProgress], None]] = None
    ) -> FolderCompareResult:
        """
        Compare two directories.
        
        Args:
            left_path: Left/source directory
            right_path: Right/target directory
            progress_callback: Called with progress updates
            
        Returns:
            FolderCompareResult with comparison details
        """
        start_time = time.time()
        
        left_path = Path(left_path).resolve()
        right_path = Path(right_path).resolve()
        
        self._cancelled = False
        self._progress_callback = progress_callback
        
        # Validate paths
        if not left_path.exists():
            logging.error(f"Left path not found: {left_path}")
            raise FileNotFoundError(f"Left path not found: {left_path}")
        if not right_path.exists():
            logging.error(f"Right path not found: {right_path}")
            raise FileNotFoundError(f"Right path not found: {right_path}")
        if not left_path.is_dir():
            logging.error(f"Left path is not a directory: {left_path}")
            raise NotADirectoryError(f"Left path is not a directory: {left_path}")
        if not right_path.is_dir():
            logging.error(f"Right path is not a directory: {right_path}")
            raise NotADirectoryError(f"Right path is not a directory: {right_path}")
        
        # Create scanner options
        scan_options = ScanOptions(
            recursive=self.options.recursive,
            follow_symlinks=self.options.follow_symlinks,
            include_hidden=self.options.include_hidden,
            include_patterns=self.options.include_patterns,
            exclude_patterns=self.options.exclude_patterns,
            ignore_permission_errors=self.options.ignore_errors,
        )
        
        scanner = FolderScanner(scan_options)
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            left_future = executor.submit(
                scanner.scan,
                left_path,
                lambda p: self._report_progress('scanning_left', p.current_path, p.files_found, 0, 0)
            )
            right_future = executor.submit(
                scanner.scan,
                right_path,
                lambda p: self._report_progress('scanning_right', p.current_path, p.files_found, 0, 0)
            )

            self._report_progress('scanning_left', '', 0, 0, 0) # Initial progress report
            self._report_progress('scanning_right', '', 0, 0, 0) # Initial progress report

            left_scan = left_future.result()
            right_scan = right_future.result()
        
        if self._cancelled:
            logging.info("FolderComparer - Comparison cancelled during left scan.")
            return self._create_cancelled_result(left_path, right_path, error_message="Comparison cancelled during left scan.")
        
        if self._cancelled:
            logging.info("FolderComparer - Comparison cancelled during right scan.")
            return self._create_cancelled_result(left_path, right_path, error_message="Comparison cancelled during right scan.")
        
        try:
            result = self._compare_scans(
                left_path, right_path,
                left_scan, right_scan
            )
            
            if self._cancelled:
                logging.info("FolderComparer - Comparison cancelled after scanning, before final result calculation.")
                return self._create_cancelled_result(left_path, right_path, error_message="Comparison cancelled.")

            result.compare_time = time.time() - start_time
            return result
        except Exception as e:
            logging.error(f"FolderComparer - Error during scan comparison: {e}")
            return self._create_cancelled_result(left_path, right_path, error_message=str(e))
    
    def compare_async(
        self,
        left_path: Path | str,
        right_path: Path | str,
    ) -> 'CompareTask':
        """
        Start async comparison.
        
        Returns a CompareTask that can be monitored and cancelled.
        """
        return CompareTask(self, left_path, right_path)
    
    def cancel(self) -> None:
        """Cancel ongoing comparison."""
        self._cancelled = True
    
    def _compare_scans(
        self,
        left_path: Path,
        right_path: Path,
        left_scan: ScanResult,
        right_scan: ScanResult
    ) -> FolderCompareResult:
        """Compare two scan results."""
        # Get all unique paths
        left_paths = left_scan.get_all_paths()
        right_paths = right_scan.get_all_paths()
        
        # Determine how to match paths
        if self.options.ignore_case:
            # Map lowercase paths to original casing (preferring left)
            left_map = {p.lower(): p for p in left_paths}
            right_map = {p.lower(): p for p in right_paths}
            
            all_lower = sorted(set(left_map.keys()) | set(right_map.keys()))
            comparison_paths = []
            for lower in all_lower:
                l_orig = left_map.get(lower)
                r_orig = right_map.get(lower)
                # Use left path as the canonical relative path if it exists
                canonical = l_orig if l_orig is not None else r_orig
                comparison_paths.append((canonical, l_orig, r_orig))
        else:
            all_paths = sorted(left_paths | right_paths)
            comparison_paths = [(p, p, p) for p in all_paths]
        
        # Compare each path
        results: dict[str, FileCompareResult] = {}
        total_items = len(comparison_paths)
        processed = 0
        
        # Use parallel comparison for files
        file_comparisons = []
        
        for rel_path, l_orig, r_orig in comparison_paths:
            if self._cancelled:
                logging.info("FolderComparer - Comparison cancelled during _compare_scans.")
                break
            
            left_meta = left_scan.get_metadata(l_orig) if l_orig else None
            right_meta = right_scan.get_metadata(r_orig) if r_orig else None
            
            # Quick status determination
            if left_meta is None:
                status = FileStatus.RIGHT_ONLY
                compare_result = FileCompareResult(
                    relative_path=rel_path,
                    left_metadata=None,
                    right_metadata=right_meta,
                    status=status,
                    compare_method=CompareMethod.CONTENT,
                )
            elif right_meta is None:
                status = FileStatus.LEFT_ONLY
                compare_result = FileCompareResult(
                    relative_path=rel_path,
                    left_metadata=left_meta,
                    right_metadata=None,
                    status=status,
                    compare_method=CompareMethod.CONTENT,
                )
            elif left_meta.file_type != right_meta.file_type:
                status = FileStatus.TYPE_MISMATCH
                compare_result = FileCompareResult(
                    relative_path=rel_path,
                    left_metadata=left_meta,
                    right_metadata=right_meta,
                    status=status,
                    compare_method=CompareMethod.CONTENT,
                )
            elif left_meta.is_directory:
                # Directories are compared by existence only
                status = FileStatus.IDENTICAL
                compare_result = FileCompareResult(
                    relative_path=rel_path,
                    left_metadata=left_meta,
                    right_metadata=right_meta,
                    status=status,
                    compare_method=CompareMethod.CONTENT,
                )
            else:
                # Files need content comparison
                file_comparisons.append((rel_path, left_meta, right_meta))
                continue
            
            results[rel_path] = compare_result
            processed += 1
            self._report_progress('comparing', rel_path, processed, total_items, 
                                 processed / total_items * 100)
        
        # Compare files in parallel
        if file_comparisons and not self._cancelled:
            file_results = self._compare_files_parallel(
                left_path, right_path,
                file_comparisons,
                processed, total_items
            )
            results.update(file_results)
        
        # Build tree structure
        try:
            root_node = self._build_tree(results, left_path.name)
        except Exception as e:
            logging.error(f"FolderComparer - Error building tree structure: {e}")
            raise

        
        # Calculate statistics
        stats = self._calculate_statistics(results)
        
        return FolderCompareResult(
            left_path=str(left_path),
            right_path=str(right_path),
            root=root_node,
            total_files=stats['total_files'],
            total_directories=stats['total_dirs'],
            identical_count=stats['identical'],
            modified_count=stats['modified'],
            left_only_count=stats['left_only'],
            right_only_count=stats['right_only'],
            error_count=stats['errors'],
        )
    
    def _compare_files_parallel(
        self,
        left_root: Path,
        right_root: Path,
        comparisons: list[tuple[str, FileMetadata, FileMetadata]],
        base_processed: int,
        total_items: int
    ) -> dict[str, FileCompareResult]:
        """Compare files using parallel workers."""
        results: dict[str, FileCompareResult] = {}
        processed = base_processed
        
        with ThreadPoolExecutor(max_workers=self.options.parallel_workers) as executor:
            futures = {}
            
            for rel_path, left_meta, right_meta in comparisons:
                if self._cancelled:
                    break
                
                future = executor.submit(
                    self._compare_single_file,
                    left_meta.path,
                    right_meta.path,
                    left_meta,
                    right_meta,
                    rel_path
                )
                futures[future] = rel_path
            
            for future in as_completed(futures):
                if self._cancelled:
                    executor.shutdown(wait=False)
                    logging.info("FolderComparer - Parallel file comparison cancelled.")
                    break
                
                rel_path = futures[future]
                try:
                    result = future.result()
                    results[rel_path] = result
                except Exception as e:
                    logging.error(f"FolderComparer - Error in parallel comparison for {rel_path}: {e}")
                    results[rel_path] = FileCompareResult(
                        relative_path=rel_path,
                        left_metadata=None,
                        right_metadata=None,
                        status=FileStatus.ERROR,
                        error=str(e)
                    )
                
                processed += 1
                self._report_progress('comparing', rel_path, processed, total_items,
                                     processed / total_items * 100)
        return results
    
    def _compare_single_file(
        self,
        left_path: Path,
        right_path: Path,
        left_meta: FileMetadata,
        right_meta: FileMetadata,
        rel_path: str
    ) -> FileCompareResult:
        """Compare a single file pair."""
        compare_method = CompareMethod.CONTENT
        
        # Quick compare first
        if self.options.quick_compare:
            # Size check
            if left_meta.size != right_meta.size:
                similarity = 0.0
                if self.options.compare_contents and left_meta.size < 1024 * 1024:
                    similarity = self._calculate_similarity(left_path, right_path)

                return FileCompareResult(
                    relative_path=rel_path,
                    left_metadata=left_meta,
                    right_metadata=right_meta,
                    status=FileStatus.MODIFIED,
                    compare_method=CompareMethod.SIZE,
                    similarity=similarity
                )
            
            # If sizes match and we don't need content compare, check mtime
            if not self.options.compare_contents:
                if left_meta.modified_time == right_meta.modified_time:
                    return FileCompareResult(
                        relative_path=rel_path,
                        left_metadata=left_meta,
                        right_metadata=right_meta,
                        status=FileStatus.IDENTICAL,
                        compare_method=CompareMethod.TIMESTAMP,
                        similarity=1.0,
                    )
        
        # Skip large files
        if left_meta.size > self.options.max_file_size:
            # Just compare by size/mtime
            is_same = (left_meta.size == right_meta.size and 
                      left_meta.modified_time == right_meta.modified_time)
            
            similarity = 1.0 if is_same else 0.0
            if not is_same and self.options.compare_contents and left_meta.size < 1024 * 1024:
                similarity = self._calculate_similarity(left_path, right_path)

            return FileCompareResult(
                relative_path=rel_path,
                left_metadata=left_meta,
                right_metadata=right_meta,
                status=FileStatus.IDENTICAL if is_same else FileStatus.MODIFIED,
                compare_method=CompareMethod.QUICK,
                similarity=similarity
            )
        
        # Content comparison
        if self.options.compare_contents:
            if self.options.use_hash:
                compare_method = CompareMethod.HASH
                is_identical = self._compare_by_hash(left_path, right_path)
            else:
                compare_method = CompareMethod.CONTENT
                is_identical = self._compare_by_content(left_path, right_path)
            
            status = FileStatus.IDENTICAL if is_identical else FileStatus.MODIFIED
            similarity = 1.0 if is_identical else 0.0
            
            if not is_identical and self.options.compare_contents and left_meta.size < 1024 * 1024:
                similarity = self._calculate_similarity(left_path, right_path)

            return FileCompareResult(
                relative_path=rel_path,
                left_metadata=left_meta,
                right_metadata=right_meta,
                status=status,
                compare_method=compare_method,
                similarity=similarity,
            )
        
        # Default: identical if same size
        similarity = 1.0 if left_meta.size == right_meta.size else 0.0
        if similarity == 0.0 and self.options.compare_contents and left_meta.size < 1024 * 1024:
            similarity = self._calculate_similarity(left_path, right_path)

        return FileCompareResult(
            relative_path=rel_path,
            left_metadata=left_meta,
            right_metadata=right_meta,
            status=FileStatus.IDENTICAL if left_meta.size == right_meta.size else FileStatus.MODIFIED,
            compare_method=CompareMethod.SIZE,
            similarity=similarity
        )

    def _calculate_similarity(self, left_path: Path, right_path: Path) -> float:
        """Calculate similarity ratio for modified files."""
        try:
            from app.services.file_io import FileIOService
            io_service = FileIOService()
            
            # Check if it's an image extension
            IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico', '.svg'}
            if left_path.suffix.lower() in IMAGE_EXTENSIONS:
                try:
                    from app.core.diff.image_diff import ImageDiffEngine
                    engine = ImageDiffEngine()
                    res = engine.compare(left_path, right_path)
                    return res.similarity
                except ImportError:
                    return 0.0
            
            # Try to read as text or document
            res1 = io_service.read_file(left_path)
            res2 = io_service.read_file(right_path)
            
            if res1.success and res2.success and res1.content and res2.content:
                import difflib
                # Use faster similarity calculation if possible, but ratio() is standard
                matcher = difflib.SequenceMatcher(None, res1.content.lines, res2.content.lines)
                return matcher.ratio()
            
            return 0.0
        except Exception as e:
            logging.debug(f"FolderComparer - Failed to calculate similarity for {left_path}: {e}")
            return 0.0
    
    def _compare_by_content(self, left_path: Path, right_path: Path) -> bool:
        """Compare files byte-by-byte."""
        try:
            with open(left_path, 'rb') as f1, open(right_path, 'rb') as f2:
                while True:
                    chunk1 = f1.read(self.options.chunk_size)
                    chunk2 = f2.read(self.options.chunk_size)
                    
                    if chunk1 != chunk2:
                        return False
                    
                    if not chunk1:  # EOF
                        return True
        except Exception as e:
            logging.error(f"FolderComparer - Error comparing content for {left_path} and {right_path}: {e}")
            raise
    
    def _compare_by_hash(self, left_path: Path, right_path: Path) -> bool:
        """Compare files by hash."""
        try:
            left_hash = self._compute_hash(left_path)
            right_hash = self._compute_hash(right_path)
            return left_hash == right_hash
        except Exception as e:
            logging.error(f"FolderComparer - Error comparing hash for {left_path} and {right_path}: {e}")
            raise
    
    def _compute_hash(self, path: Path) -> str:
        """Compute hash of a file."""
        try:
            hasher = hashlib.new(self.options.hash_algorithm)
            
            with open(path, 'rb') as f:
                while chunk := f.read(self.options.chunk_size):
                    hasher.update(chunk)
            
            return hasher.hexdigest()
        except Exception as e:
            logging.error(f"FolderComparer - Error computing hash for {path}: {e}")
            raise
    
    def _build_tree(
        self,
        results: dict[str, FileCompareResult],
        root_name: str
    ) -> FolderCompareNode:
        """Build a tree structure from flat results."""
        # Create root node
        root_result = FileCompareResult(
            relative_path="",
            left_metadata=None,
            right_metadata=None,
            status=FileStatus.IDENTICAL,
        )
        root = FolderCompareNode(result=root_result)
        
        # Map to track created nodes
        nodes: dict[str, FolderCompareNode] = {"": root}
        
        # Sort paths to ensure parents are created before children
        for rel_path in sorted(results.keys()):
            result = results[rel_path]
            
            # Find or create parent
            parent_path = str(Path(rel_path).parent)
            if parent_path == ".":
                parent_path = ""
            
            if parent_path not in nodes:
                # Create intermediate directory nodes
                self._ensure_parent_nodes(nodes, parent_path, root)
            
            parent_node = nodes[parent_path]
            
            # Create this node
            node = FolderCompareNode(result=result, parent=parent_node)
            parent_node.children.append(node)
            nodes[rel_path] = node
        
        # Sort children by name
        self._sort_tree(root)
        return root
    
    def _ensure_parent_nodes(
        self,
        nodes: dict[str, FolderCompareNode],
        path: str,
        root: FolderCompareNode
    ) -> None:
        """Ensure all parent nodes exist."""
        parts = Path(path).parts
        current_path = ""
        current_node = root
        
        for part in parts:
            current_path = str(Path(current_path) / part) if current_path else part
            
            if current_path not in nodes:
                # Create directory node
                result = FileCompareResult(
                    relative_path=current_path,
                    left_metadata=FileMetadata(
                        path=Path(current_path),
                        name=part,
                        file_type=FileType.DIRECTORY,
                    ),
                    right_metadata=FileMetadata(
                        path=Path(current_path),
                        name=part,
                        file_type=FileType.DIRECTORY,
                    ),
                    status=FileStatus.IDENTICAL,
                )
                node = FolderCompareNode(result=result, parent=current_node)
                current_node.children.append(node)
                nodes[current_path] = node
                current_node = node
            else:
                current_node = nodes[current_path]
    
    def _sort_tree(self, node: FolderCompareNode) -> None:
        """Recursively sort tree children."""
        node.children.sort(key=lambda n: (
            0 if n.is_directory else 1,
            n.name.lower()
        ))
        
        for child in node.children:
            self._sort_tree(child)
    
    def _calculate_statistics(
        self,
        results: dict[str, FileCompareResult]
    ) -> dict[str, int]:
        """Calculate comparison statistics."""
        stats = {
            'total_files': 0,
            'total_dirs': 0,
            'identical': 0,
            'modified': 0,
            'left_only': 0,
            'right_only': 0,
            'errors': 0,
        }
        
        for result in results.values():
            if result.is_directory:
                stats['total_dirs'] += 1
            else:
                stats['total_files'] += 1
            
            if result.status == FileStatus.IDENTICAL:
                stats['identical'] += 1
            elif result.status == FileStatus.MODIFIED:
                stats['modified'] += 1
            elif result.status == FileStatus.LEFT_ONLY:
                stats['left_only'] += 1
            elif result.status == FileStatus.RIGHT_ONLY:
                stats['right_only'] += 1
            elif result.status == FileStatus.ERROR:
                stats['errors'] += 1
        return stats
    
    def _report_progress(
        self,
        phase: str,
        current_path: str,
        processed: int,
        total: int,
        percent: float
    ) -> None:
        """Report progress to callback."""
        if self._progress_callback:
            progress = CompareProgress(
                phase=phase,
                current_path=current_path,
                items_processed=processed,
                total_items=total,
                percent=percent
            )
            self._progress_callback(progress)
    
    def _create_cancelled_result(
        self,
        left_path: Path,
        right_path: Path
    ) -> FolderCompareResult:
        """Create a result for cancelled comparison."""
        root = FolderCompareNode(
            result=FileCompareResult(
                relative_path="",
                left_metadata=None,
                right_metadata=None,
                status=FileStatus.ERROR,
                error="Comparison cancelled"
            )
        )
        
        return FolderCompareResult(
            left_path=str(left_path),
            right_path=str(right_path),
            root=root,
            error="Comparison cancelled"
        )


class CompareTask:
    """
    Async comparison task wrapper.
    
    Allows monitoring and cancellation of comparison.
    """
    
    def __init__(
        self,
        comparer: FolderComparer,
        left_path: Path | str,
        right_path: Path | str
    ):
        self._comparer = comparer
        self._left_path = Path(left_path)
        self._right_path = Path(right_path)
        self._result: Optional[FolderCompareResult] = None
        self._error: Optional[Exception] = None
        self._progress: Optional[CompareProgress] = None
        self._done = False
        self._cancelled = False
    
    @property
    def is_done(self) -> bool:
        return self._done
    
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
    
    @property
    def result(self) -> Optional[FolderCompareResult]:
        return self._result
    
    @property
    def error(self) -> Optional[Exception]:
        return self._error
    
    @property
    def progress(self) -> Optional[CompareProgress]:
        return self._progress
    
    def cancel(self) -> None:
        """Cancel the comparison."""
        self._cancelled = True
        self._comparer.cancel()
    
    def run(self) -> FolderCompareResult:
        """Run the comparison synchronously."""
        try:
            self._result = self._comparer.compare(
                self._left_path,
                self._right_path,
                self._on_progress
            )
            return self._result
        except Exception as e:
            self._error = e
            raise
        finally:
            self._done = True
    
    def _on_progress(self, progress: CompareProgress) -> None:
        """Handle progress updates."""
        self._progress = progress


class QuickComparer:
    """
    Fast folder comparison using only metadata.
    
    Compares by file size and modification time only.
    Much faster than content comparison for initial overview.
    """
    
    def __init__(self):
        self._scanner = FolderScanner()
    
    def compare(
        self,
        left_path: Path | str,
        right_path: Path | str
    ) -> dict[str, str]:
        """
        Quick comparison returning status for each path.
        
        Returns dict mapping relative path to status string:
        'identical', 'modified', 'left_only', 'right_only'
        """
        left_path = Path(left_path)
        right_path = Path(right_path)
        
        left_files: dict[str, tuple[int, float]] = {}  # path -> (size, mtime)
        right_files: dict[str, tuple[int, float]] = {}
        
        # Scan left
        for rel_path, meta in self._scanner.scan_lazy(left_path):
            if meta.is_file:
                mtime = meta.modified_time.timestamp() if meta.modified_time else 0
                left_files[rel_path] = (meta.size, mtime)
        
        # Scan right
        for rel_path, meta in self._scanner.scan_lazy(right_path):
            if meta.is_file:
                mtime = meta.modified_time.timestamp() if meta.modified_time else 0
                right_files[rel_path] = (meta.size, mtime)
        
        # Compare
        result = {}
        
        all_paths = set(left_files.keys()) | set(right_files.keys())
        
        for path in all_paths:
            if path in left_files and path in right_files:
                left_size, left_mtime = left_files[path]
                right_size, right_mtime = right_files[path]
                
                if left_size == right_size and abs(left_mtime - right_mtime) < 2:
                    result[path] = 'identical'
                else:
                    result[path] = 'modified'
            elif path in left_files:
                result[path] = 'left_only'
            else:
                result[path] = 'right_only'
        
        return result