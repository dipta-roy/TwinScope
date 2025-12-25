"""
Merge module for three-way file merging.
"""

from app.core.merge.three_way import (
    ThreeWayMergeEngine,
    MergeStrategy,
    Diff3Merge,
)

__all__ = [
    'ThreeWayMergeEngine',
    'MergeStrategy',
    'Diff3Merge',
]