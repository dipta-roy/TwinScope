"""
PyQt6 User Interface module.

Provides the main application window and all views:
- File comparison (side-by-side diff)
- Folder comparison (tree view)
- Merge view (three-way)
- Binary and image comparison views
"""

from app.ui.main_window import MainWindow
from app.ui.file_compare_view import FileCompareView
from app.ui.folder_compare_view import FolderCompareView
from app.ui.merge_view import MergeView

__all__ = [
    'MainWindow',
    'FileCompareView',
    'FolderCompareView',
    'MergeView',
]