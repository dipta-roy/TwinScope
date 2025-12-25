"""
Directory scanner for folder comparison.

Provides efficient, configurable directory traversal with:
- Recursive scanning
- Pattern-based filtering (gitignore-style)
- Symlink handling
- Progress reporting
- Error resilience
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional, Set

from app.core.models import (
    FileMetadata,
    FileType,
    FileFilter,
)


@dataclass
class ScanOptions:
    """Options for directory scanning."""
    recursive: bool = True
    follow_symlinks: bool = False
    include_hidden: bool = False
    max_depth: Optional[int] = None
    
    # File filters
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=lambda: [
        '.git', '.svn', '.hg', '.bzr',
        '__pycache__', '*.pyc', '*.pyo',
        'node_modules', '.npm',
        '.DS_Store', 'Thumbs.db', 'desktop.ini',
        '*.swp', '*.swo', '*~',
        '.idea', '.vscode', '*.suo', '*.user',
    ])
    
    # Size limits
    skip_empty_dirs: bool = False
    min_file_size: Optional[int] = None
    max_file_size: Optional[int] = None
    
    # Error handling
    ignore_permission_errors: bool = True
    ignore_broken_symlinks: bool = True
    
    def should_include(self, path: Path, is_dir: bool) -> bool:
        """Check if a path should be included based on patterns."""
        name = path.name
        
        # Check hidden files
        if not self.include_hidden and name.startswith('.'):
            return False
        
        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return False
            if fnmatch.fnmatch(str(path), pattern):
                return False
        
        # Check include patterns (if specified, only include matching)
        if self.include_patterns:
            matched = False
            for pattern in self.include_patterns:
                if fnmatch.fnmatch(name, pattern):
                    matched = True
                    break
                if fnmatch.fnmatch(str(path), pattern):
                    matched = True
                    break
            if not matched and not is_dir:  # Always include dirs for traversal
                return False
        
        return True


@dataclass
class ScanProgress:
    """Progress information for scanning."""
    current_path: str
    files_found: int
    directories_found: int
    errors: int
    current_depth: int


@dataclass
class ScanResult:
    """Result of a directory scan."""
    root_path: Path
    files: dict[str, FileMetadata]  # Relative path -> metadata
    directories: dict[str, FileMetadata]
    total_size: int
    file_count: int
    directory_count: int
    error_count: int
    errors: list[tuple[str, str]]  # (path, error message)
    scan_time: float
    
    def get_all_paths(self) -> set[str]:
        """Get all relative paths (files and directories)."""
        return set(self.files.keys()) | set(self.directories.keys())
    
    def get_metadata(self, relative_path: str) -> Optional[FileMetadata]:
        """Get metadata for a path."""
        return self.files.get(relative_path) or self.directories.get(relative_path)
    
    def iter_files(self) -> Iterator[tuple[str, FileMetadata]]:
        """Iterate over all files."""
        yield from self.files.items()
    
    def iter_directories(self) -> Iterator[tuple[str, FileMetadata]]:
        """Iterate over all directories."""
        yield from self.directories.items()


class PatternMatcher:
    """
    Gitignore-style pattern matcher. 
    
    Supports:
    - * (matches any characters except /)
    - ** (matches any characters including /)
    - ? (matches single character)
    - [abc] (character class)
    - ! (negation)
    - / prefix (anchored to root)
    - / suffix (directory only)
    """
    
    def __init__(self, patterns: list[str]):
        self._positive_patterns: list[tuple[re.Pattern, bool]] = []  # (regex, dir_only)
        self._negative_patterns: list[tuple[re.Pattern, bool]] = []
        
        for pattern in patterns:
            self._compile_pattern(pattern)
    
    def _compile_pattern(self, pattern: str) -> None:
        """Compile a gitignore pattern to regex."""
        if not pattern or pattern.startswith('#'):
            return
        
        pattern = pattern.strip()
        if not pattern:
            return
        
        # Check for negation
        is_negative = pattern.startswith('!')
        if is_negative:
            pattern = pattern[1:]
        
        # Check for directory-only
        dir_only = pattern.endswith('/')
        if dir_only:
            pattern = pattern[:-1]
        
        # Check for anchored pattern
        anchored = pattern.startswith('/')
        if anchored:
            pattern = pattern[1:]
        
        # Convert to regex
        regex = self._pattern_to_regex(pattern, anchored)
        
        compiled = re.compile(regex)
        
        if is_negative:
            self._negative_patterns.append((compiled, dir_only))
        else:
            self._positive_patterns.append((compiled, dir_only))
    
    def _pattern_to_regex(self, pattern: str, anchored: bool) -> str:
        """Convert gitignore pattern to regex."""
        # Escape special regex characters except our wildcards
        special = '.^$+{}[]|()\\'
        result = []
        i = 0
        
        while i < len(pattern):
            c = pattern[i]
            
            if c == '*':
                if i + 1 < len(pattern) and pattern[i + 1] == '*':
                    # ** matches anything including /
                    if i + 2 < len(pattern) and pattern[i + 2] == '/':
                        result.append('(?:.*/)?')
                        i += 3
                        continue
                    else:
                        result.append('.*')
                        i += 2
                        continue
                else:
                    # * matches anything except /
                    result.append('[^/]*')
            elif c == '?':
                result.append('[^/]')
            elif c == '[':
                # Character class
                j = i + 1
                if j < len(pattern) and pattern[j] == '!':
                    result.append('[^')
                    j += 1
                else:
                    result.append('[')
                while j < len(pattern) and pattern[j] != ']':
                    result.append(pattern[j])
                    j += 1
                result.append(']')
                i = j
            elif c in special:
                result.append('\\' + c)
            else:
                result.append(c)
            
            i += 1
        
        regex = ''.join(result)
        
        if anchored:
            regex = '^' + regex
        else:
            regex = '(?:^|/)' + regex
        
        regex += '(?:/.*)?$'
        
        return regex
    
    def matches(self, path: str, is_dir: bool = False) -> bool:
        """
        Check if a path matches the patterns. 
        
        Returns True if the path should be excluded.
        """
        # Normalize path
        path = path.replace(os.sep, '/')
        if path.startswith('/'):
            path = path[1:]
        
        matched = False
        
        # Check positive patterns (exclude)
        for pattern, dir_only in self._positive_patterns:
            if dir_only and not is_dir:
                continue
            if pattern.search(path):
                matched = True
                break
        
        if not matched:
            return False
        
        # Check negative patterns (re-include)
        for pattern, dir_only in self._negative_patterns:
            if dir_only and not is_dir:
                continue
            if pattern.search(path):
                return False
        
        return True
    
    @classmethod
    def from_gitignore(cls, gitignore_path: Path) -> 'PatternMatcher':
        """Create a matcher from a .gitignore file."""
        patterns = []
        
        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            patterns.append(line)
            except (PermissionError, OSError) as e:
                logging.warning(f"PatternMatcher - Could not read gitignore {gitignore_path}: {e}")
        
        return cls(patterns)


class FolderScanner:
    """
    Scans directories to build a file tree. 
    
    Features:
    - Configurable filtering
    - Progress callbacks
    - Error resilience
    - Efficient memory usage for large directories
    """
    
    def __init__(self, options: Optional[ScanOptions] = None):
        self.options = options or ScanOptions()
        self._cancelled = False
    
    def scan(
        self,
        root_path: Path | str,
        progress_callback: Optional[Callable[[ScanProgress], None]] = None
    ) -> ScanResult:
        """
        Scan a directory tree. 
        
        Args:
            root_path: Root directory to scan
            progress_callback: Called with progress updates
            
        Returns:
            ScanResult with all found files and directories
        """
        import time
        start_time = time.time()
        
        root_path = Path(root_path).resolve()
        
        if not root_path.exists():
            logging.error(f"FolderScanner - Root path not found: {root_path}")
            raise FileNotFoundError(f"Directory not found: {root_path}")
        
        if not root_path.is_dir():
            logging.error(f"FolderScanner - Root path is not a directory: {root_path}")
            raise NotADirectoryError(f"Not a directory: {root_path}")
        
        self._cancelled = False
        
        files: dict[str, FileMetadata] = {}
        directories: dict[str, FileMetadata] = {}
        errors: list[tuple[str, str]] = []
        total_size = 0
        
        # Create pattern matcher from exclude patterns
        matcher = PatternMatcher(self.options.exclude_patterns) if self.options.exclude_patterns else None
        
        # Load .gitignore if present
        gitignore_path = root_path / '.gitignore'
        gitignore_matcher = None
        if gitignore_path.exists():
            try:
                gitignore_matcher = PatternMatcher.from_gitignore(gitignore_path)
            except Exception as e:
                logging.warning(f"FolderScanner - Could not load .gitignore from {gitignore_path}: {e}")
        
        def should_exclude(rel_path: str, is_dir: bool) -> bool:
            """Check if path should be excluded."""
            if matcher and matcher.matches(rel_path, is_dir):
                return True
            if gitignore_matcher and gitignore_matcher.matches(rel_path, is_dir):
                return True
            return False
        
        def on_walk_error(error: OSError):
            if self.options.ignore_permission_errors:
                try:
                    rel_path = str(Path(error.filename).relative_to(root_path)) if error.filename else "unknown"
                except Exception:
                    rel_path = str(error.filename) if error.filename else "unknown"
                errors.append((rel_path, f"Access error: {error.strerror}"))
                logging.warning(f"FolderScanner - Walk error at {rel_path}: {error}")
            else:
                raise error

        for dirpath, dirnames, filenames in os.walk(
            root_path,
            topdown=True,
            followlinks=self.options.follow_symlinks,
            onerror=on_walk_error
        ):
            if self._cancelled:
                logging.info(f"FolderScanner - Scan cancelled during os.walk")
                break
            
            current_path = Path(dirpath)
            rel_dir = current_path.relative_to(root_path)
            current_depth = len(rel_dir.parts)
            
            # Check max depth
            if self.options.max_depth is not None:
                if current_depth > self.options.max_depth:
                    dirnames.clear()  # Don't recurse deeper
                    continue
            
            # Filter directories in-place to control recursion
            if not self.options.recursive and current_depth > 0:
                dirnames.clear()
            else:
                dirnames[:] = [
                    d for d in dirnames
                    if not should_exclude(str((current_path / d).relative_to(root_path)), True)
                ]
            
            # Sort for consistent ordering
            dirnames.sort()
            filenames.sort()
            
            # Process directories
            for dirname in dirnames:
                dir_full_path = current_path / dirname
                rel_path = str(dir_full_path.relative_to(root_path))
                
                try:
                    metadata = self._get_metadata(dir_full_path)
                    directories[rel_path] = metadata
                except Exception as e:
                    if self.options.ignore_permission_errors:
                        errors.append((rel_path, str(e)))
                        logging.warning(f"FolderScanner - Error processing directory {rel_path}: {e}")
                    else:
                        logging.exception(f"FolderScanner - Unhandled error processing directory {rel_path}")
                        raise
            
            # Process files
            for filename in filenames:
                file_full_path = current_path / filename
                rel_path = str(file_full_path.relative_to(root_path))
                
                # Check exclusion
                if should_exclude(rel_path, False):
                    continue
                
                # Check hidden
                if not self.options.include_hidden and filename.startswith('.'):
                    continue
                
                # Check include patterns
                if not self.options.should_include(file_full_path, False):
                    continue
                
                try:
                    metadata = self._get_metadata(file_full_path)
                    
                    # Check size limits
                    if self.options.min_file_size is not None:
                        if metadata.size < self.options.min_file_size:
                            continue
                    if self.options.max_file_size is not None:
                        if metadata.size > self.options.max_file_size:
                            continue
                    
                    files[rel_path] = metadata
                    total_size += metadata.size
                    
                except Exception as e:
                    if self.options.ignore_permission_errors:
                        errors.append((rel_path, str(e)))
                        logging.warning(f"FolderScanner - Error processing file {rel_path}: {e}")
                    else:
                        logging.exception(f"FolderScanner - Unhandled error processing file {rel_path}")
                        raise
            
            # Progress callback
            if progress_callback:
                progress = ScanProgress(
                    current_path=str(rel_dir),
                    files_found=len(files),
                    directories_found=len(directories),
                    errors=len(errors),
                    current_depth=current_depth
                )
                progress_callback(progress)
        
        scan_time = time.time() - start_time
        
        return ScanResult(
            root_path=root_path,
            files=files,
            directories=directories,
            total_size=total_size,
            file_count=len(files),
            directory_count=len(directories),
            error_count=len(errors),
            errors=errors,
            scan_time=scan_time
        )
    
    def scan_lazy(
        self,
        root_path: Path | str
    ) -> Iterator[tuple[str, FileMetadata]]:
        """
        Lazily scan a directory, yielding items as found. 
        
        Memory-efficient for very large directories.
        """
        root_path = Path(root_path).resolve()
        
        matcher = PatternMatcher(self.options.exclude_patterns) if self.options.exclude_patterns else None
        
        for dirpath, dirnames, filenames in os.walk(
            root_path,
            topdown=True,
            followlinks=self.options.follow_symlinks
        ):
            if self._cancelled:
                return
            
            current_path = Path(dirpath)
            
            # Filter directories
            if not self.options.recursive:
                if current_path != root_path:
                    dirnames.clear()
            else:
                dirnames[:] = [
                    d for d in dirnames
                    if not self._should_include_dir(
                        current_path / d, root_path,
                        lambda p, is_dir: matcher.matches(p, is_dir) if matcher else False
                    )
                ]
            
            dirnames.sort()
            filenames.sort()
            
            # Yield directories
            for dirname in dirnames:
                dir_path = current_path / dirname
                rel_path = str(dir_path.relative_to(root_path))
                try:
                    yield (rel_path, self._get_metadata(dir_path))
                except Exception as e:
                    logging.warning(f"FolderScanner - Lazy scan error processing directory {rel_path}: {e}")
            
            # Yield files
            for filename in filenames:
                file_path = current_path / filename
                rel_path = str(file_path.relative_to(root_path))
                
                if matcher and matcher.matches(rel_path, False):
                    continue
                
                if not self.options.include_hidden and filename.startswith('.'):
                    continue
                
                try:
                    yield (rel_path, self._get_metadata(file_path))
                except Exception as e:
                    logging.warning(f"FolderScanner - Lazy scan error processing file {rel_path}: {e}")
    
    def cancel(self) -> None:
        """Cancel an ongoing scan."""
        self._cancelled = True
    
    def _should_include_dir(
        self,
        dir_path: Path,
        root_path: Path,
        exclude_func: Callable[[str, bool], bool]
    ) -> bool:
        """Check if a directory should be included in scan."""
        rel_path = str(dir_path.relative_to(root_path))
        name = dir_path.name
        
        # Check hidden
        if not self.options.include_hidden and name.startswith('.'):
            return False
        
        # Check exclusion patterns
        if exclude_func(rel_path, True):
            return False
        
        # Check general include rules
        if not self.options.should_include(dir_path, True):
            return False
        
        return True
    
    def _get_metadata(self, path: Path) -> FileMetadata:
        """Get metadata for a file or directory."""
        try:
            # Use lstat to not follow symlinks initially
            stat_result = path.lstat()
            
            # Determine file type
            if stat.S_ISLNK(stat_result.st_mode):
                file_type = FileType.SYMLINK
                try:
                    symlink_target = path.resolve()
                except OSError as e:
                    logging.debug(f"FolderScanner - Failed to resolve symlink {path}: {e}")
                    symlink_target = None
            elif stat.S_ISDIR(stat_result.st_mode):
                file_type = FileType.DIRECTORY
                symlink_target = None
            elif stat.S_ISREG(stat_result.st_mode):
                file_type = FileType.FILE
                symlink_target = None
            else:
                file_type = FileType.UNKNOWN
                symlink_target = None
            
            # Get times
            modified_time = datetime.fromtimestamp(stat_result.st_mtime)
            try:
                created_time = datetime.fromtimestamp(stat_result.st_ctime)
            except (OSError, ValueError) as e:
                logging.debug(f"FolderScanner - Failed to get creation time for {path}: {e}")
                created_time = None
            
            # Check attributes
            is_hidden = path.name.startswith('.')
            is_readonly = not os.access(path, os.W_OK)
            
            # On Windows, check hidden attribute
            if os.name == 'nt':
                try:
                    import ctypes
                    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
                    if attrs != -1:
                        is_hidden = bool(attrs & 0x2)  # FILE_ATTRIBUTE_HIDDEN
                        is_readonly = bool(attrs & 0x1)  # FILE_ATTRIBUTE_READONLY
                except Exception as e:
                    logging.debug(f"FolderScanner - Failed to get Windows file attributes for {path}: {e}")
            
            return FileMetadata(
                path=path,
                name=path.name,
                file_type=file_type,
                size=stat_result.st_size if file_type == FileType.FILE else 0,
                modified_time=modified_time,
                created_time=created_time,
                permissions=stat_result.st_mode,
                is_hidden=is_hidden,
                is_readonly=is_readonly,
                symlink_target=symlink_target,
            )
            
        except PermissionError as e:
            return FileMetadata(
                path=path,
                name=path.name,
                file_type=FileType.UNKNOWN,
                error=f"Permission denied: {e}"
            )
        except OSError as e:
            return FileMetadata(
                path=path,
                name=path.name,
                file_type=FileType.UNKNOWN,
                error=f"OS error: {e}"
            )


class DirectoryTree:
    """
    Represents a directory tree structure. 
    
    Provides tree operations and traversal methods.
    """
    
    @dataclass
    class Node:
        """A node in the directory tree."""
        name: str
        path: str
        metadata: FileMetadata
        children: dict[str, 'DirectoryTree.Node'] = field(default_factory=dict)
        parent: Optional['DirectoryTree.Node'] = None
        
        @property
        def is_directory(self) -> bool:
            return self.metadata.file_type == FileType.DIRECTORY
        
        @property
        def is_file(self) -> bool:
            return self.metadata.file_type == FileType.FILE
        
        @property
        def child_count(self) -> int:
            return len(self.children)
        
        def iter_children(self) -> Iterator['DirectoryTree.Node']:
            """Iterate over children sorted by name."""
            for name in sorted(self.children.keys()):
                yield self.children[name]
        
        def iter_all(self) -> Iterator['DirectoryTree.Node']:
            """Iterate over this node and all descendants."""
            yield self
            for child in self.iter_children():
                yield from child.iter_all()
    
    def __init__(self, root_path: Path, scan_result: ScanResult):
        self.root_path = root_path
        self._root: Optional[DirectoryTree.Node] = None
        self._build_tree(scan_result)
    
    @property
    def root(self) -> Node:
        if self._root is None:
            raise ValueError("Tree not built")
        return self._root
    
    def _build_tree(self, scan_result: ScanResult) -> None:
        """Build tree structure from scan result."""
        # Create root node
        self._root = DirectoryTree.Node(
            name=self.root_path.name,
            path="",
            metadata=FileMetadata(
                path=self.root_path,
                name=self.root_path.name,
                file_type=FileType.DIRECTORY,
            )
        )
        
        # Add directories first
        for rel_path, metadata in sorted(scan_result.directories.items()):
            self._add_node(rel_path, metadata)
        
        # Add files
        for rel_path, metadata in sorted(scan_result.files.items()):
            self._add_node(rel_path, metadata)
    
    def _add_node(self, rel_path: str, metadata: FileMetadata) -> Node:
        """Add a node to the tree."""
        parts = Path(rel_path).parts
        
        current = self._root
        current_path = ""
        
        # Navigate/create parent directories
        for i, part in enumerate(parts[:-1]):
            current_path = str(Path(current_path) / part) if current_path else part
            
            if part not in current.children:
                # Create intermediate directory node
                current.children[part] = DirectoryTree.Node(
                    name=part,
                    path=current_path,
                    metadata=FileMetadata(
                        path=self.root_path / current_path,
                        name=part,
                        file_type=FileType.DIRECTORY,
                    ),
                    parent=current
                )
            
            current = current.children[part]
        
        # Add the final node
        name = parts[-1]
        node = DirectoryTree.Node(
            name=name,
            path=rel_path,
            metadata=metadata,
            parent=current
        )
        current.children[name] = node
        
        return node
    
    def get_node(self, rel_path: str) -> Optional[Node]:
        """Get a node by relative path."""
        if not rel_path:
            return self._root
        
        parts = Path(rel_path).parts
        current = self._root
        
        for part in parts:
            if part not in current.children:
                return None
            current = current.children[part]
        
        return current
    
    def iter_files(self) -> Iterator[Node]:
        """Iterate over all file nodes."""
        for node in self._root.iter_all():
            if node.is_file:
                yield node
    
    def iter_directories(self) -> Iterator[Node]:
        """Iterate over all directory nodes."""
        for node in self._root.iter_all():
            if node.is_directory:
                yield node