"""
Merge components package for TwinScope.
"""

from app.ui.merge.conflict_widget import (
    ConflictWidget,
    CustomResolutionDialog,
)
from app.ui.merge.conflict_navigation import (
    ConflictListWidget,
)

__all__ = [
    'ConflictWidget',
    'CustomResolutionDialog',
    'ConflictListWidget',
]
