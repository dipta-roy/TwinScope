"""
Workers for file and folder comparison operations.
"""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Optional

from PyQt6.QtCore import QObject

from app.workers.base_worker import BaseWorker, CancellableWorker, ProgressInfo
from app.core.diff.text_diff import TextDiffEngine, TextCompareOptions
from app.core.diff.binary_diff import BinaryDiffEngine, BinaryCompareOptions
from app.core.diff.image_diff import ImageDiffEngine, ImageCompareOptions
from app.core.folder.comparer import FolderComparer, CompareOptions
from app.core.models import DiffResult, BinaryDiffResult, ImageDiffResult, FolderCompareResult
from app.services.file_io import FileIOService, ReadResult # Added



class TextCompareWorker(CancellableWorker):
    """
    Worker for comparing text files.
    
    Runs text diff engine in background thread.
    """
    
    def __init__(
        self,
        left_path: str | Path,
        right_path: str | Path,
        options: Optional[TextCompareOptions] = None,
        encoding: str = 'utf-8',
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.options = options or TextCompareOptions()
        self.encoding = encoding
    
    def do_work(self) -> DiffResult:
        """Perform text comparison."""
        self.report_status(f"Comparing {self.left_path.name}...")

        file_io_service = FileIOService()

        # Read left file
        if self.left_path and self.left_path.is_file():
            self.report_progress(0, 100, "Reading left file...")
            left_read_result = file_io_service.read_file(self.left_path, encoding=self.encoding)
            if not left_read_result.success:
                if left_read_result.is_binary:
                    raise IOError(f"File appears to be binary and cannot be compared as text: {self.left_path}")
                raise IOError(f"Failed to read left file: {left_read_result.error}")
            left_lines = left_read_result.content.lines if left_read_result.content else []
        else:
            left_lines = []
        self.check_cancelled()

        # Read right file
        if self.right_path and self.right_path.is_file():
            self.report_progress(50, 100, "Reading right file...")
            right_read_result = file_io_service.read_file(self.right_path, encoding=self.encoding)
            if not right_read_result.success:
                if right_read_result.is_binary:
                    raise IOError(f"File appears to be binary and cannot be compared as text: {self.right_path}")
                raise IOError(f"Failed to read right file: {right_read_result.error}")
            right_lines = right_read_result.content.lines if right_read_result.content else []
        else:
            right_lines = []
        self.check_cancelled()
        
        # Compare
        self.report_status("Computing differences...")
        engine = TextDiffEngine(self.options)
        result = engine.compare(
            left_lines,
            right_lines,
            str(self.left_path),
            str(self.right_path)
        )
        
        self.report_status("Complete")
        return result


class TextCompareWorkerFromContent(CancellableWorker):
    """
    Worker for comparing text content directly.
    
    Useful when content is already in memory.
    """
    
    def __init__(
        self,
        left_content: str,
        right_content: str,
        left_label: str = "Left",
        right_label: str = "Right",
        options: Optional[TextCompareOptions] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.left_content = left_content
        self.right_content = right_content
        self.left_label = left_label
        self.right_label = right_label
        self.options = options or TextCompareOptions()
    
    def do_work(self) -> DiffResult:
        """Perform text comparison."""
        self.report_status("Computing differences...")
        
        left_lines = self.left_content.splitlines(keepends=True)
        right_lines = self.right_content.splitlines(keepends=True)
        
        engine = TextDiffEngine(self.options)
        return engine.compare(
            left_lines,
            right_lines,
            self.left_label,
            self.right_label
        )


class BinaryCompareWorker(CancellableWorker):
    """
    Worker for comparing binary files.
    """
    
    def __init__(
        self,
        left_path: str | Path,
        right_path: str | Path,
        options: Optional[BinaryCompareOptions] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.options = options or BinaryCompareOptions()
    
    def do_work(self) -> BinaryDiffResult:
        """Perform binary comparison."""
        self.report_status(f"Comparing {self.left_path.name}...")
        
        engine = BinaryDiffEngine(self.options)
        
        def progress_callback(processed: int, total: int) -> None:
            if self.maybe_check_cancelled():
                raise InterruptedError("Cancelled")
            self.report_progress(processed, total, "Comparing bytes...")
        
        result = engine.compare(
            self.left_path,
            self.right_path,
            progress_callback
        )
        
        return result


class ImageCompareWorker(CancellableWorker):
    """
    Worker for comparing image files.
    """
    
    def __init__(
        self,
        left_path: str | Path,
        right_path: str | Path,
        options: Optional[ImageCompareOptions] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.options = options or ImageCompareOptions()
    
    def do_work(self) -> ImageDiffResult:
        """Perform image comparison."""
        self.report_status(f"Comparing {self.left_path.name}...")
        
        engine = ImageDiffEngine(self.options)
        
        def progress_callback(processed: int, total: int) -> None:
            if self.maybe_check_cancelled():
                raise InterruptedError("Cancelled")
            self.report_progress(processed, total, "Analyzing images...")
        
        result = engine.compare(
            self.left_path,
            self.right_path,
            progress_callback
        )
        
        return result


class FolderCompareWorker(CancellableWorker):
    """
    Worker for comparing folders.
    
    Handles large directory trees without blocking the UI.
    """
    
    def __init__(
        self,
        left_path: str | Path,
        right_path: str | Path,
        options: Optional[CompareOptions] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.options = options or CompareOptions()
        self._comparer: Optional[FolderComparer] = None
    
    def do_work(self) -> FolderCompareResult:
        self.report_status("Starting folder comparison...")
        
        self._comparer = FolderComparer(self.options)
        
        def progress_callback(progress) -> None:
            if self.is_cancelled:
                self._comparer.cancel()
                return
            
            self.report_progress_detail(ProgressInfo(
                current=progress.items_processed,
                total=progress.total_items,
                message=progress.phase,
                detail=progress.current_path
            ))
        
        result = self._comparer.compare(
            self.left_path,
            self.right_path,
            progress_callback
        )
        return result
    
    def cancel(self) -> None:
        """Cancel the comparison."""
        super().cancel()
        if self._comparer:
            self._comparer.cancel()


class QuickCompareWorker(BaseWorker):
    """
    Worker for quick file comparison (size + mtime only).
    
    Much faster than content comparison.
    """
    
    def __init__(
        self,
        left_path: str | Path,
        right_path: str | Path,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
    
    def do_work(self) -> dict[str, str]:
        """Perform quick comparison."""
        from app.core.folder.comparer import QuickComparer
        
        self.report_status("Quick comparing...")
        
        comparer = QuickComparer()
        return comparer.compare(self.left_path, self.right_path)


class FileTypeDetectWorker(BaseWorker):
    """
    Worker to detect file types and choose appropriate comparison.
    """
    
    # Known text extensions
    TEXT_EXTENSIONS = {
        '.txt', '.md', '.rst', '.json', '.xml', '.html', '.htm',
        '.css', '.js', '.ts', '.py', '.rb', '.java', '.c', '.cpp',
        '.h', '.hpp', '.cs', '.go', '.rs', '.swift', '.kt', '.scala',
        '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
        '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        '.sql', '.graphql', '.proto',
        '.vue', '.jsx', '.tsx', '.svelte',
        '.r', '.R', '.jl', '.m', '.matlab',
        '.tex', '.bib', '.sty',
        '.csv', '.tsv',
        '.log', '.diff', '.patch',
    }
    
    # Known image extensions
    IMAGE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif',
        '.webp', '.ico', '.svg',
    }
    
    # Known binary extensions
    BINARY_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib', '.bin', '.dat',
        '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
        '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wav', '.flac',
        '.ttf', '.otf', '.woff', '.woff2',
    }
    
    def __init__(
        self,
        file_path: str | Path,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.file_path = Path(file_path)
    
    def do_work(self) -> str:
        """
        Detect file type.
        
        Returns one of: 'text', 'image', 'binary', 'unknown'
        """
        suffix = self.file_path.suffix.lower()
        
        if suffix in self.TEXT_EXTENSIONS:
            return 'text'
        elif suffix in self.IMAGE_EXTENSIONS:
            return 'image'
        elif suffix in self.BINARY_EXTENSIONS:
            return 'binary'
        
        # Try to detect by content
        try:
            with open(self.file_path, 'rb') as f:
                chunk = f.read(8192)
            
            # Check for null bytes (binary indicator)
            if b'\x00' in chunk:
                return 'binary'
            
            # Check for image magic bytes
            if chunk.startswith(b'\x89PNG') or chunk.startswith(b'\xff\xd8\xff'):
                return 'image'
            
            # Try to decode as UTF-8
            try:
                chunk.decode('utf-8')
                return 'text'
            except UnicodeDecodeError:
                logging.debug(f"FileTypeDetectWorker - {self.file_path} is not valid UTF-8")
            
            # Try Latin-1 (always succeeds)
            try:
                chunk.decode('latin-1')
                # Check if mostly printable
                printable = sum(1 for b in chunk if 32 <= b < 127 or b in (9, 10, 13))
                if printable / len(chunk) > 0.7:
                    return 'text'
            except Exception as e:
                logging.debug(f"FileTypeDetectWorker - Latin-1 check failed for {self.file_path}: {e}")
            
            return 'binary'
            
        except Exception:
            return 'unknown'