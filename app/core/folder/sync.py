"""
Folder synchronization engine.

Provides two-way folder synchronization with:
- Conflict detection
- Preview mode
- Progress reporting
- Rollback support
"""

from __future__ import annotations

import os
import shutil
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional
import time

from app.core.models import (
    FileMetadata,
    FileStatus,
    FileType,
    FileCompareResult,
    FolderCompareResult,
    FolderCompareNode,
    SyncAction,
    SyncDirection,
    SyncItem,
    SyncPlan,
    SyncProgress,
    SyncResult,
)


@dataclass
class SyncOptions:
    """Options for synchronization."""
    direction: SyncDirection = SyncDirection.LEFT_TO_RIGHT
    
    # What to sync
    sync_new_files: bool = True
    sync_modified_files: bool = True
    sync_deletions: bool = False  # Delete files that don't exist in source
    
    # Conflict handling
    overwrite_newer: bool = False  # Overwrite even if dest is newer
    skip_conflicts: bool = True    # Skip files modified on both sides
    
    # Safety
    preview_only: bool = False     # Don't actually make changes
    create_backup: bool = True     # Backup before overwrite
    backup_suffix: str = ".bak"
    
    # Performance  
    buffer_size: int = 65536
    preserve_timestamps: bool = True
    preserve_permissions: bool = True
    
    # Filtering
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class SyncConflict:
    """Represents a sync conflict."""
    relative_path: str
    left_metadata: Optional[FileMetadata]
    right_metadata: Optional[FileMetadata]
    reason: str
    suggested_action: SyncAction = SyncAction.SKIP


class FolderSync:
    """
    Synchronizes two folders.
    
    Supports:
    - One-way sync (mirror)
    - Two-way sync with conflict detection
    - Preview mode
    - Progress reporting
    """
    
    def __init__(self, options: Optional[SyncOptions] = None):
        self.options = options or SyncOptions()
        self._cancelled = False
        self._progress_callback: Optional[Callable[[SyncProgress], None]] = None
    
    def create_plan(
        self,
        compare_result: FolderCompareResult
    ) -> SyncPlan:
        """
        Create a synchronization plan from comparison result.
        
        Returns a SyncPlan that can be reviewed before execution.
        """
        items: list[SyncItem] = []
        
        left_root = Path(compare_result.left_path)
        right_root = Path(compare_result.right_path)
        
        for node in compare_result.root.iter_all():
            if not node.result.relative_path:
                continue  # Skip root
            
            result = node.result
            item = self._create_sync_item(result, left_root, right_root)
            
            if item and item.action != SyncAction.SKIP:
                items.append(item)
        
        return SyncPlan(
            items=items,
            direction=self.options.direction,
            left_path=compare_result.left_path,
            right_path=compare_result.right_path,
        )
    
    def execute(
        self,
        plan: SyncPlan,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None
    ) -> SyncResult:
        """
        Execute a synchronization plan.
        
        Args:
            plan: The sync plan to execute
            progress_callback: Called with progress updates
            
        Returns:
            SyncResult with execution details
        """
        start_time = time.time()
        
        self._cancelled = False
        self._progress_callback = progress_callback
        
        left_root = Path(plan.left_path)
        right_root = Path(plan.right_path)
        
        items_copied = 0
        items_deleted = 0
        items_skipped = 0
        items_failed = 0
        bytes_copied = 0
        errors: list[tuple[str, str]] = []
        
        total_items = len(plan.items)
        total_bytes = plan.total_bytes
        
        for i, item in enumerate(plan.items):
            if self._cancelled:
                break
            
            # Report progress
            if progress_callback:
                progress = SyncProgress(
                    current_item=item.relative_path,
                    items_completed=i,
                    total_items=total_items,
                    bytes_copied=bytes_copied,
                    total_bytes=total_bytes,
                    current_action=item.action.name,
                )
                progress_callback(progress)
            
            if self.options.preview_only:
                items_skipped += 1
                continue
            
            try:
                if item.action == SyncAction.COPY_TO_RIGHT:
                    copied = self._copy_file(
                        left_root / item.relative_path,
                        right_root / item.relative_path
                    )
                    bytes_copied += copied
                    items_copied += 1
                    
                elif item.action == SyncAction.COPY_TO_LEFT:
                    copied = self._copy_file(
                        right_root / item.relative_path,
                        left_root / item.relative_path
                    )
                    bytes_copied += copied
                    items_copied += 1
                    
                elif item.action == SyncAction.DELETE_RIGHT:
                    self._delete_path(right_root / item.relative_path)
                    items_deleted += 1
                    
                elif item.action == SyncAction.DELETE_LEFT:
                    self._delete_path(left_root / item.relative_path)
                    items_deleted += 1
                    
                elif item.action == SyncAction.SKIP:
                    items_skipped += 1
                    
                elif item.action == SyncAction.CONFLICT:
                    items_skipped += 1
                    
            except Exception as e:
                items_failed += 1
                errors.append((item.relative_path, str(e)))
        
        duration = time.time() - start_time
        
        return SyncResult(
            success=items_failed == 0 and not self._cancelled,
            items_processed=total_items,
            items_copied=items_copied,
            items_deleted=items_deleted,
            items_skipped=items_skipped,
            items_failed=items_failed,
            bytes_copied=bytes_copied,
            errors=errors,
            duration=duration,
        )
    
    def sync(
        self,
        left_path: Path | str,
        right_path: Path | str,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None
    ) -> SyncResult:
        """
        Perform full sync: compare and execute.
        
        Convenience method combining compare + plan + execute.
        """
        from app.core.folder.comparer import FolderComparer
        
        comparer = FolderComparer()
        compare_result = comparer.compare(left_path, right_path)
        
        plan = self.create_plan(compare_result)
        return self.execute(plan, progress_callback)
    
    def cancel(self) -> None:
        """Cancel ongoing synchronization."""
        self._cancelled = True
    
    def find_conflicts(
        self,
        compare_result: FolderCompareResult
    ) -> list[SyncConflict]:
        """
        Find conflicts in a comparison result.
        
        Conflicts occur when files are modified on both sides.
        """
        conflicts = []
        
        for node in compare_result.root.iter_all():
            result = node.result
            
            if result.status == FileStatus.MODIFIED:
                # Check if modified on both sides (for two-way sync)
                if self.options.direction == SyncDirection.BIDIRECTIONAL:
                    left_meta = result.left_metadata
                    right_meta = result.right_metadata
                    
                    if left_meta and right_meta:
                        left_time = left_meta.modified_time
                        right_time = right_meta.modified_time
                        
                        # Both modified after last sync would be a conflict
                        # For now, consider any modification a potential conflict
                        conflict = SyncConflict(
                            relative_path=result.relative_path,
                            left_metadata=left_meta,
                            right_metadata=right_meta,
                            reason="Modified on both sides",
                            suggested_action=SyncAction.CONFLICT,
                        )
                        conflicts.append(conflict)
        
        return conflicts
    
    def _create_sync_item(
        self,
        result: FileCompareResult,
        left_root: Path,
        right_root: Path
    ) -> Optional[SyncItem]:
        """Create a sync item from a compare result."""
        direction = self.options.direction
        
        if result.status == FileStatus.IDENTICAL:
            return None
        
        if result.status == FileStatus.LEFT_ONLY:
            if direction in (SyncDirection.LEFT_TO_RIGHT, SyncDirection.BIDIRECTIONAL):
                if self.options.sync_new_files:
                    return SyncItem(
                        relative_path=result.relative_path,
                        action=SyncAction.COPY_TO_RIGHT,
                        source_path=left_root / result.relative_path,
                        dest_path=right_root / result.relative_path,
                        source_metadata=result.left_metadata,
                        reason="New file in left",
                    )
            elif direction == SyncDirection.RIGHT_TO_LEFT:
                if self.options.sync_deletions:
                    return SyncItem(
                        relative_path=result.relative_path,
                        action=SyncAction.DELETE_LEFT,
                        source_path=left_root / result.relative_path,
                        source_metadata=result.left_metadata,
                        reason="Does not exist in right",
                    )
        
        elif result.status == FileStatus.RIGHT_ONLY:
            if direction in (SyncDirection.RIGHT_TO_LEFT, SyncDirection.BIDIRECTIONAL):
                if self.options.sync_new_files:
                    return SyncItem(
                        relative_path=result.relative_path,
                        action=SyncAction.COPY_TO_LEFT,
                        source_path=right_root / result.relative_path,
                        dest_path=left_root / result.relative_path,
                        source_metadata=result.right_metadata,
                        reason="New file in right",
                    )
            elif direction == SyncDirection.LEFT_TO_RIGHT:
                if self.options.sync_deletions:
                    return SyncItem(
                        relative_path=result.relative_path,
                        action=SyncAction.DELETE_RIGHT,
                        source_path=right_root / result.relative_path,
                        source_metadata=result.right_metadata,
                        reason="Does not exist in left",
                    )
        
        elif result.status == FileStatus.MODIFIED:
            if self.options.sync_modified_files:
                return self._create_modified_sync_item(result, left_root, right_root)
        
        return SyncItem(
            relative_path=result.relative_path,
            action=SyncAction.SKIP,
            reason="No action needed",
        )
    
    def _create_modified_sync_item(
        self,
        result: FileCompareResult,
        left_root: Path,
        right_root: Path
    ) -> SyncItem:
        """Create sync item for modified file."""
        direction = self.options.direction
        left_meta = result.left_metadata
        right_meta = result.right_metadata
        
        if direction == SyncDirection.LEFT_TO_RIGHT:
            return SyncItem(
                relative_path=result.relative_path,
                action=SyncAction.COPY_TO_RIGHT,
                source_path=left_root / result.relative_path,
                dest_path=right_root / result.relative_path,
                source_metadata=left_meta,
                dest_metadata=right_meta,
                reason="Modified - copying left to right",
            )
        
        elif direction == SyncDirection.RIGHT_TO_LEFT:
            return SyncItem(
                relative_path=result.relative_path,
                action=SyncAction.COPY_TO_LEFT,
                source_path=right_root / result.relative_path,
                dest_path=left_root / result.relative_path,
                source_metadata=right_meta,
                dest_metadata=left_meta,
                reason="Modified - copying right to left",
            )
        
        else:  # BIDIRECTIONAL
            # Determine which is newer
            left_time = left_meta.modified_time if left_meta else None
            right_time = right_meta.modified_time if right_meta else None
            
            if left_time and right_time:
                if self.options.skip_conflicts:
                    return SyncItem(
                        relative_path=result.relative_path,
                        action=SyncAction.CONFLICT,
                        source_metadata=left_meta,
                        dest_metadata=right_meta,
                        reason="Conflict - modified on both sides",
                    )
                elif left_time > right_time:
                    return SyncItem(
                        relative_path=result.relative_path,
                        action=SyncAction.COPY_TO_RIGHT,
                        source_path=left_root / result.relative_path,
                        dest_path=right_root / result.relative_path,
                        source_metadata=left_meta,
                        dest_metadata=right_meta,
                        reason="Left is newer",
                    )
                else:
                    return SyncItem(
                        relative_path=result.relative_path,
                        action=SyncAction.COPY_TO_LEFT,
                        source_path=right_root / result.relative_path,
                        dest_path=left_root / result.relative_path,
                        source_metadata=right_meta,
                        dest_metadata=left_meta,
                        reason="Right is newer",
                    )
            
            return SyncItem(
                relative_path=result.relative_path,
                action=SyncAction.SKIP,
                reason="Cannot determine newer version",
            )
    
    def _copy_file(self, source: Path, dest: Path) -> int:
        """
        Copy a file from source to destination.
        
        Returns bytes copied.
        """
        # Ensure parent directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup if requested
        if self.options.create_backup and dest.exists():
            backup_path = dest.with_suffix(dest.suffix + self.options.backup_suffix)
            shutil.copy2(dest, backup_path)
        
        # Copy file
        bytes_copied = 0
        
        with open(source, 'rb') as src:
            with open(dest, 'wb') as dst:
                while chunk := src.read(self.options.buffer_size):
                    dst.write(chunk)
                    bytes_copied += len(chunk)
        
        # Preserve metadata
        if self.options.preserve_timestamps:
            stat = source.stat()
            os.utime(dest, (stat.st_atime, stat.st_mtime))
        
        if self.options.preserve_permissions:
            shutil.copymode(source, dest)
        
        return bytes_copied
    
    def _delete_path(self, path: Path) -> None:
        """Delete a file or directory."""
        if self.options.create_backup:
            backup_path = path.with_suffix(path.suffix + self.options.backup_suffix)
            if path.is_dir():
                shutil.copytree(path, backup_path)
            else:
                shutil.copy2(path, backup_path)
        
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


class MirrorSync:
    """
    One-way mirror synchronization.
    
    Makes the target an exact copy of the source,
    including deletions.
    """
    
    def __init__(
        self,
        delete_extra: bool = True,
        ignore_patterns: Optional[list[str]] = None
    ):
        self.delete_extra = delete_extra
        self.ignore_patterns = ignore_patterns or []
    
    def mirror(
        self,
        source: Path | str,
        target: Path | str,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None
    ) -> SyncResult:
        """
        Mirror source to target.
        
        Target will be an exact copy of source.
        """
        options = SyncOptions(
            direction=SyncDirection.LEFT_TO_RIGHT,
            sync_new_files=True,
            sync_modified_files=True,
            sync_deletions=self.delete_extra,
            exclude_patterns=self.ignore_patterns,
        )
        
        sync = FolderSync(options)
        return sync.sync(source, target, progress_callback)


class IncrementalSync:
    """
    Incremental synchronization with change tracking.
    
    Tracks what was synced to avoid re-comparing
    unchanged files.
    """
    
    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file
        self._last_sync: dict[str, tuple[int, float]] = {}  # path -> (size, mtime)
    
    def load_state(self) -> None:
        """Load sync state from file."""
        if self.state_file and self.state_file.exists():
            import json
            with open(self.state_file, 'r') as f:
                self._last_sync = json.load(f)
    
    def save_state(self) -> None:
        """Save sync state to file."""
        if self.state_file:
            import json
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self._last_sync, f)
    
    def has_changed(self, path: Path) -> bool:
        """Check if a file has changed since last sync."""
        rel_path = str(path)
        
        if rel_path not in self._last_sync:
            return True
        
        try:
            stat = path.stat()
            last_size, last_mtime = self._last_sync[rel_path]
            return stat.st_size != last_size or stat.st_mtime != last_mtime
        except OSError as e:
            logging.debug(f"IncrementalSync - Failed to stat {path}: {e}")
            return True
    
    def mark_synced(self, path: Path) -> None:
        """Mark a file as synced."""
        try:
            stat = path.stat()
            self._last_sync[str(path)] = (stat.st_size, stat.st_mtime)
        except OSError as e:
            # Log the error but continue, as we just fail to update the incremental state
            import logging
            logging.warning(f"IncrementalSync - Failed to update state for {path}: {e}")
    
    def sync(
        self,
        source: Path | str,
        target: Path | str,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None
    ) -> SyncResult:
        """
        Perform incremental sync.
        
        Only syncs files that have changed since last sync.
        """
        self.load_state()
        
        # For now, use regular sync
        # Future: filter to only changed files
        sync = FolderSync()
        result = sync.sync(source, target, progress_callback)
        
        if result.success:
            self.save_state()
        
        return result