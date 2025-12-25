"""
Workers for merge operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.workers.base_worker import BaseWorker, CancellableWorker
from app.core.merge.three_way import ThreeWayMergeEngine, MergeStrategy
from app.core.models import MergeResult, MergeConflict, ConflictResolution


class MergeWorker(BaseWorker):
    """
    Worker for three-way merge operations.
    """
    
    def __init__(
        self,
        base_path: str | Path,
        left_path: str | Path,
        right_path: str | Path,
        strategy: MergeStrategy = MergeStrategy.MANUAL,
        encoding: str = 'utf-8',
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.base_path = Path(base_path)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.strategy = strategy
        self.encoding = encoding
    
    def do_work(self) -> MergeResult:
        """Perform three-way merge."""
        self.report_status("Reading files...")
        
        # Read files
        with open(self.base_path, 'r', encoding=self.encoding, errors='replace') as f:
            base_lines = f.readlines()
        
        with open(self.left_path, 'r', encoding=self.encoding, errors='replace') as f:
            left_lines = f.readlines()
        
        with open(self.right_path, 'r', encoding=self.encoding, errors='replace') as f:
            right_lines = f.readlines()
        
        # Merge
        self.report_status("Merging...")
        
        engine = ThreeWayMergeEngine(self.strategy)
        result = engine.merge(
            base_lines,
            left_lines,
            right_lines,
            left_label=str(self.left_path),
            right_label=str(self.right_path),
            base_label=str(self.base_path)
        )
        
        return result


class MergeFromContentWorker(BaseWorker):
    """
    Worker for merging text content directly.
    """
    
    def __init__(
        self,
        base_content: str,
        left_content: str,
        right_content: str,
        strategy: MergeStrategy = MergeStrategy.MANUAL,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.base_content = base_content
        self.left_content = left_content
        self.right_content = right_content
        self.strategy = strategy
    
    def do_work(self) -> MergeResult:
        """Perform merge on content."""
        engine = ThreeWayMergeEngine(self.strategy)
        
        base_lines = self.base_content.splitlines(keepends=True)
        left_lines = self.left_content.splitlines(keepends=True)
        right_lines = self.right_content.splitlines(keepends=True)
        
        return engine.merge(base_lines, left_lines, right_lines)


class AutoMergeWorker(BaseWorker):
    """
    Worker that attempts automatic merge resolution.
    """
    
    # Signal for each conflict that couldn't be auto-resolved
    conflict_found = pyqtSignal(object)  # MergeConflict
    
    def __init__(
        self,
        merge_result: MergeResult,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.merge_result = merge_result
    
    def do_work(self) -> MergeResult:
        """Attempt to auto-resolve conflicts."""
        from app.core.merge.conflict_resolver import AutoMerger
        
        merger = AutoMerger(
            auto_resolve_whitespace=True,
            auto_resolve_identical=True
        )
        
        result, resolved_count = merger.try_auto_resolve(self.merge_result)
        
        # Emit remaining conflicts
        for conflict in result.conflicts:
            if not conflict.is_resolved:
                self.conflict_found.emit(conflict)
        
        self.report_status(f"Auto-resolved {resolved_count} conflicts")
        
        return result


class SaveMergeWorker(BaseWorker):
    """
    Worker for saving merge result to file.
    """
    
    def __init__(
        self,
        merge_result: MergeResult,
        output_path: str | Path,
        encoding: str = 'utf-8',
        create_backup: bool = True,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.merge_result = merge_result
        self.output_path = Path(output_path)
        self.encoding = encoding
        self.create_backup = create_backup
    
    def do_work(self) -> bool:
        """Save merge result."""
        import shutil
        
        # Create backup
        if self.create_backup and self.output_path.exists():
            backup_path = self.output_path.with_suffix(
                self.output_path.suffix + '.orig'
            )
            shutil.copy2(self.output_path, backup_path)
        
        # Write merged content
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.output_path, 'w', encoding=self.encoding) as f:
            f.write(self.merge_result.merged_text)
        
        return True