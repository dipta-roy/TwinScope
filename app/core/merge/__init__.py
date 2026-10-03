"""
Merge module for three-way file merging.
"""

from app.core.merge.three_way import (
    Diff3Merge,
    MergeStrategy,
    ThreeWayMergeEngine,
)

__all__ = [
    'ThreeWayMergeEngine',
    'MergeStrategy',
    'Diff3Merge',
]
