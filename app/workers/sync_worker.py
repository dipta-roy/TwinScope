"""
Workers for folder synchronization operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.workers.base_worker import BaseWorker, CancellableWorker, ProgressInfo
from app.core.folder.sync import FolderSync, SyncOptions, SyncPlan, SyncResult
from app.core.folder.comparer import FolderComparer, CompareOptions
from app.core.models import FolderCompareResult, SyncItem


class SyncPlanWorker(CancellableWorker):
    """
    Worker for creating a synchronization plan.
    
    Compares folders and generates a plan without executing.
    """
    
    def __init__(
        self,
        left_path: str | Path,
        right_path: str | Path,
        sync_options: Optional[SyncOptions] = None,
        compare_options: Optional[CompareOptions] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.sync_options = sync_options or SyncOptions()
        self.compare_options = compare_options or CompareOptions()
    
    def do_work(self) -> tuple[FolderCompareResult, SyncPlan]:
        """Create sync plan."""
        # First, compare folders
        self.report_status("Comparing folders...")
        
        comparer = FolderComparer(self.compare_options)
        
        def compare_progress(progress) -> None:
            if self.is_cancelled:
                comparer.cancel()
                return
            
            self.report_progress_detail(ProgressInfo(
                current=progress.items_processed,
                total=progress.total_items,
                message=f"Comparing: {progress.phase}",
                detail=progress.current_path
            ))
        
        compare_result = comparer.compare(
            self.left_path,
            self.right_path,
            compare_progress
        )
        
        if self.is_cancelled:
            raise InterruptedError("Cancelled")
        
        # Create sync plan
        self.report_status("Creating sync plan...")
        
        sync = FolderSync(self.sync_options)
        plan = sync.create_plan(compare_result)
        
        return compare_result, plan


class SyncWorker(CancellableWorker):
    """
    Worker for executing folder synchronization.
    
    Reports progress for each file operation.
    """
    
    # Signal emitted for each item synced
    item_synced = pyqtSignal(object)  # SyncItem
    
    # Signal emitted when an error occurs (but continues)
    sync_error = pyqtSignal(str, str)  # (path, error)
    
    def __init__(
        self,
        plan: SyncPlan,
        options: Optional[SyncOptions] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.plan = plan
        self.options = options or SyncOptions()
        self._sync: Optional[FolderSync] = None
    
    def do_work(self) -> SyncResult:
        """Execute synchronization."""
        self.report_status("Starting synchronization...")
        
        self._sync = FolderSync(self.options)
        
        def progress_callback(progress) -> None:
            if self.is_cancelled:
                self._sync.cancel()
                return
            
            self.report_progress_detail(ProgressInfo(
                current=progress.items_completed,
                total=progress.total_items,
                message=progress.current_action,
                detail=progress.current_item
            ))
        
        result = self._sync.execute(self.plan, progress_callback)
        
        # Report errors
        for path, error in result.errors:
            self.sync_error.emit(path, error)
        
        return result
    
    def cancel(self) -> None:
        """Cancel synchronization."""
        super().cancel()
        if self._sync:
            self._sync.cancel()


class FullSyncWorker(CancellableWorker):
    """
    Worker that performs full sync: compare, plan, and execute.
    
    Convenience worker for simple sync operations.
    """
    
    # Emitted after comparison, before sync
    plan_ready = pyqtSignal(object, object)  # (FolderCompareResult, SyncPlan)
    
    def __init__(
        self,
        left_path: str | Path,
        right_path: str | Path,
        sync_options: Optional[SyncOptions] = None,
        auto_execute: bool = True,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent=parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.sync_options = sync_options or SyncOptions()
        self.auto_execute = auto_execute
        self._result: Optional[SyncResult] = None
    
    def do_work(self) -> SyncResult:
        """Perform full sync."""
        # Compare
        self.report_status("Comparing folders...")
        comparer = FolderComparer()
        compare_result = comparer.compare(self.left_path, self.right_path)
        
        if self.is_cancelled:
            raise InterruptedError("Cancelled")
        
        # Plan
        self.report_status("Planning sync...")
        sync = FolderSync(self.sync_options)
        plan = sync.create_plan(compare_result)
        
        self.plan_ready.emit(compare_result, plan)
        
        if not self.auto_execute:
            return SyncResult(
                success=True,
                items_processed=0,
                items_copied=0,
                items_deleted=0,
                items_skipped=plan.total_items,
                items_failed=0,
                bytes_copied=0,
            )
        
        if self.is_cancelled:
            raise InterruptedError("Cancelled")
        
        # Execute
        self.report_status("Synchronizing...")
        
        def progress_callback(progress) -> None:
            if self.is_cancelled:
                sync.cancel()
                return
            self.report_progress(
                progress.items_completed,
                progress.total_items,
                progress.current_item
            )
        
        result = sync.execute(plan, progress_callback)
        
        return result


class CopyWorker(BaseWorker):
    """
    Worker for copying files/folders.
    
    Simpler than full sync for single copy operations.
    """
    
    def __init__(
        self,
        source: str | Path,
        destination: str | Path,
        overwrite: bool = False,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.source = Path(source)
        self.destination = Path(destination)
        self.overwrite = overwrite
    
    def do_work(self) -> int:
        """
        Copy file or folder.
        
        Returns bytes copied.
        """
        import shutil
        
        if self.destination.exists() and not self.overwrite:
            raise FileExistsError(f"Destination exists: {self.destination}")
        
        if self.source.is_dir():
            return self._copy_directory()
        else:
            return self._copy_file()
    
    def _copy_file(self) -> int:
        """Copy a single file."""
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        
        size = self.source.stat().st_size
        copied = 0
        buffer_size = 65536
        
        with open(self.source, 'rb') as src:
            with open(self.destination, 'wb') as dst:
                while chunk := src.read(buffer_size):
                    if self.is_cancelled:
                        raise InterruptedError("Cancelled")
                    dst.write(chunk)
                    copied += len(chunk)
                    self.report_progress(copied, size, self.source.name)
        
        return copied
    
    def _copy_directory(self) -> int:
        """Copy a directory tree."""
        import shutil
        
        total_size = sum(
            f.stat().st_size
            for f in self.source.rglob('*')
            if f.is_file()
        )
        
        copied = 0
        
        for src_file in self.source.rglob('*'):
            if self.is_cancelled:
                raise InterruptedError("Cancelled")
            
            rel_path = src_file.relative_to(self.source)
            dst_path = self.destination / rel_path
            
            if src_file.is_dir():
                dst_path.mkdir(parents=True, exist_ok=True)
            else:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_path)
                copied += src_file.stat().st_size
                self.report_progress(copied, total_size, str(rel_path))
        
        return copied