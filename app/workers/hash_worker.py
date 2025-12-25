"""
Workers for file hashing operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.workers.base_worker import BaseWorker, CancellableWorker, ProgressInfo
from app.services.hashing import HashingService, HashAlgorithm, HashResult


class HashWorker(CancellableWorker):
    """
    Worker for computing file hash.
    """
    
    def __init__(
        self,
        path: str | Path,
        algorithm: HashAlgorithm = HashAlgorithm.SHA256,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.path = Path(path)
        self.algorithm = algorithm
    
    def do_work(self) -> HashResult:
        """Compute file hash."""
        self.report_status(f"Hashing {self.path.name}...")
        
        service = HashingService()
        
        def progress_callback(progress) -> None:
            if self.maybe_check_cancelled():
                raise InterruptedError("Cancelled")
            
            self.report_progress(
                progress.bytes_processed,
                progress.total_bytes,
                f"{progress.percent:.1f}%"
            )
        
        result = service.hash_file(
            self.path,
            self.algorithm,
            progress_callback
        )
        
        return result


class BatchHashWorker(CancellableWorker):
    """
    Worker for hashing multiple files.
    """
    
    # Signal emitted for each file hashed
    file_hashed = pyqtSignal(str, object)  # (path, HashResult)
    
    def __init__(
        self,
        paths: list[str | Path],
        algorithm: HashAlgorithm = HashAlgorithm.SHA256,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.paths = [Path(p) for p in paths]
        self.algorithm = algorithm
    
    def do_work(self) -> dict[str, HashResult]:
        """Hash all files."""
        results: dict[str, HashResult] = {}
        
        service = HashingService()
        total = len(self.paths)
        
        for i, path in enumerate(self.paths):
            if self.is_cancelled:
                break
            
            self.report_progress(i, total, path.name)
            
            try:
                result = service.hash_file(path, self.algorithm)
                results[str(path)] = result
                self.file_hashed.emit(str(path), result)
            except Exception as e:
                self.report_status(f"Error hashing {path}: {e}")
        
        return results


class VerifyHashWorker(BaseWorker):
    """
    Worker for verifying file hashes.
    """
    
    def __init__(
        self,
        path: str | Path,
        expected_hash: str,
        algorithm: HashAlgorithm = HashAlgorithm.SHA256,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.path = Path(path)
        self.expected_hash = expected_hash.lower()
        self.algorithm = algorithm
    
    def do_work(self) -> tuple[bool, str]:
        """
        Verify file hash.
        
        Returns (matches, actual_hash).
        """
        service = HashingService()
        result = service.hash_file(self.path, self.algorithm)
        
        matches = result.hash_hex.lower() == self.expected_hash
        return matches, result.hash_hex


class DirectoryHashWorker(CancellableWorker):
    """
    Worker for computing hash of entire directory.
    """
    
    def __init__(
        self,
        path: str | Path,
        algorithm: HashAlgorithm = HashAlgorithm.SHA256,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.path = Path(path)
        self.algorithm = algorithm
    
    def do_work(self) -> HashResult:
        """Compute directory hash."""
        self.report_status(f"Hashing directory {self.path.name}...")
        
        service = HashingService()
        
        def progress_callback(progress) -> None:
            if self.maybe_check_cancelled():
                raise InterruptedError("Cancelled")
            
            self.report_progress_detail(ProgressInfo(
                current=progress.bytes_processed,
                total=progress.total_bytes,
                message="Hashing files...",
                detail=str(progress.file_path) if progress.file_path else ""
            ))
        
        result = service.hash_directory(
            self.path,
            self.algorithm,
            include_names=True,
            progress_callback=progress_callback
        )
        
        return result