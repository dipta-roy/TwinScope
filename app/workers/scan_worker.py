"""
Workers for directory scanning operations.
"""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Optional, Callable

from PyQt6.QtCore import QObject, pyqtSignal

from app.workers.base_worker import BaseWorker, CancellableWorker, ProgressInfo
from app.core.folder.scanner import FolderScanner, ScanOptions, ScanResult


class FolderScanWorker(CancellableWorker):
    """
    Worker for scanning a directory tree.
    
    Reports progress as files are discovered.
    """
    
    # Signal emitted for each file found (for live updates)
    file_found = pyqtSignal(str, object)  # (relative_path, FileMetadata)
    
    def __init__(
        self,
        path: str | Path,
        options: Optional[ScanOptions] = None,
        emit_files: bool = False,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.path = Path(path)
        self.options = options or ScanOptions()
        self.emit_files = emit_files
        self._scanner: Optional[FolderScanner] = None
    
    def do_work(self) -> ScanResult:
        """Perform directory scan."""
        self.report_status(f"Scanning {self.path.name}...")
        
        self._scanner = FolderScanner(self.options)
        
        def progress_callback(progress) -> None:
            if self.is_cancelled:
                self._scanner.cancel()
                return
            
            self.report_progress_detail(ProgressInfo(
                current=progress.files_found,
                total=0,  # Unknown total during scan
                message=f"Found {progress.files_found} files",
                detail=progress.current_path
            ))
        
        result = self._scanner.scan(self.path, progress_callback)
        
        # Emit individual files if requested
        if self.emit_files:
            for rel_path, metadata in result.files.items():
                if self.is_cancelled:
                    break
                self.file_found.emit(rel_path, metadata)
        
        return result
    
    def cancel(self) -> None:
        """Cancel the scan."""
        super().cancel()
        if self._scanner:
            self._scanner.cancel()


class BatchScanWorker(CancellableWorker):
    """
    Worker for scanning multiple directories.
    """
    
    # Signal emitted when a directory scan completes
    directory_complete = pyqtSignal(str, object)  # (path, ScanResult)
    
    def __init__(
        self,
        paths: list[str | Path],
        options: Optional[ScanOptions] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.paths = [Path(p) for p in paths]
        self.options = options or ScanOptions()
    
    def do_work(self) -> dict[str, ScanResult]:
        """Scan all directories."""
        results: dict[str, ScanResult] = {}
        
        scanner = FolderScanner(self.options)
        
        for i, path in enumerate(self.paths):
            if self.is_cancelled:
                break
            
            self.report_progress(i, len(self.paths), f"Scanning {path.name}...")
            
            try:
                result = scanner.scan(path)
                results[str(path)] = result
                self.directory_complete.emit(str(path), result)
            except Exception as e:
                self.report_status(f"Error scanning {path}: {e}")
        
        return results


class LazyLoadWorker(BaseWorker):
    """
    Worker for lazy loading directory contents.
    
    Used for expanding nodes in a tree view without blocking.
    """
    
    def __init__(
        self,
        path: str | Path,
        depth: int = 1,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.path = Path(path)
        self.depth = depth
    
    def do_work(self) -> list[tuple[str, object]]:
        """
        Load immediate children of directory.
        
        Returns list of (name, FileMetadata) tuples.
        """
        from app.core.folder.scanner import FolderScanner, ScanOptions
        
        options = ScanOptions(
            recursive=False,
            max_depth=self.depth,
        )
        
        scanner = FolderScanner(options)
        
        children = []
        for rel_path, metadata in scanner.scan_lazy(self.path):
            if self.is_cancelled:
                break
            children.append((rel_path, metadata))
        
        return children


class FileWatcherWorker(BaseWorker):
    """
    Worker that watches for file changes.
    
    Uses polling (cross-platform compatible).
    For production, consider using watchdog library.
    """
    
    # Signal emitted when a change is detected
    change_detected = pyqtSignal(str, str)  # (path, change_type)
    
    def __init__(
        self,
        paths: list[str | Path],
        interval: float = 1.0,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.paths = [Path(p) for p in paths]
        self.interval = interval
        self._file_states: dict[str, tuple[float, int]] = {}  # path -> (mtime, size)
    
    def do_work(self) -> None:
        """Watch for changes continuously."""
        import time
        
        # Initial scan
        self._update_states()
        
        while not self.is_cancelled:
            time.sleep(self.interval)
            
            if self.is_cancelled:
                break
            
            changes = self._check_changes()
            for path, change_type in changes:
                self.change_detected.emit(path, change_type)
    
    def _update_states(self) -> None:
        """Update known file states."""
        for path in self.paths:
            if path.is_dir():
                self._scan_directory(path)
            else:
                self._record_file(path)
    
    def _scan_directory(self, dir_path: Path) -> None:
        """Scan directory for files."""
        try:
            for item in dir_path.rglob('*'):
                if item.is_file():
                    self._record_file(item)
        except PermissionError as e:
            logging.warning(f"FileWatcherWorker - Permission denied scanning directory {dir_path}: {e}")
    
    def _record_file(self, path: Path) -> None:
        """Record file state."""
        try:
            stat = path.stat()
            self._file_states[str(path)] = (stat.st_mtime, stat.st_size)
        except OSError as e:
            logging.debug(f"FileWatcherWorker - Failed to record file {path}: {e}")
    
    def _check_changes(self) -> list[tuple[str, str]]:
        """Check for changes since last check."""
        changes = []
        current_files: set[str] = set()
        
        for path in self.paths:
            if path.is_dir():
                try:
                    for item in path.rglob('*'):
                        if item.is_file():
                            current_files.add(str(item))
                            change = self._check_file(item)
                            if change:
                                changes.append((str(item), change))
                except PermissionError as e:
                    logging.warning(f"FileWatcherWorker - Permission denied checking items in {path}: {e}")
            else:
                current_files.add(str(path))
                change = self._check_file(path)
                if change:
                    changes.append((str(path), change))
        
        # Check for deleted files
        for path in list(self._file_states.keys()):
            if path not in current_files:
                del self._file_states[path]
                changes.append((path, 'deleted'))
        
        return changes
    
    def _check_file(self, path: Path) -> Optional[str]:
        """Check single file for changes."""
        try:
            stat = path.stat()
            current = (stat.st_mtime, stat.st_size)
            
            str_path = str(path)
            if str_path not in self._file_states:
                self._file_states[str_path] = current
                return 'created'
            
            if self._file_states[str_path] != current:
                self._file_states[str_path] = current
                return 'modified'
            
            return None
            
        except OSError:
            if str(path) in self._file_states:
                del self._file_states[str(path)]
                return 'deleted'
            return None