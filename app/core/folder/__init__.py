"""
Folder comparison module.

Provides functionality for:
- Recursive directory scanning
- Folder-to-folder comparison
- File filtering with gitignore-style patterns
- Synchronization planning
"""

from app.core.folder.scanner import (
    FolderScanner,
    ScanOptions,
    ScanResult,
    PatternMatcher,
)
from app.core.folder.comparer import (
    FolderComparer,
    CompareOptions as FolderCompareOptions,
)
from app.core.folder.sync import (
    FolderSync,
    SyncOptions,
)

__all__ = [
    # Scanner
    'FolderScanner',
    'ScanOptions',
    'ScanResult',
    'PatternMatcher',
    # Comparer
    'FolderComparer',
    'FolderCompareOptions',
    # Sync
    'FolderSync',
    'SyncOptions',
]