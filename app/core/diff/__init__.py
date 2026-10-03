"""
Diff module for file comparison operations.

Provides engines for comparing:
- Text files (line-by-line with various options)
- Binary files (byte-level comparison)
- Image files (visual difference detection)
"""

from app.core.diff.binary_diff import (
    BinaryCompareOptions,
    BinaryDiffEngine,
)
from app.core.diff.image_diff import (
    ImageCompareOptions,
    ImageDiffEngine,
    ImageDiffMode,
)
from app.core.diff.text_diff import (
    DiffAlgorithm,
    TextCompareOptions,
    TextDiffEngine,
)

__all__ = [
    # Text diff
    'TextDiffEngine',
    'DiffAlgorithm',
    'TextCompareOptions',
    # Binary diff
    'BinaryDiffEngine',
    'BinaryCompareOptions',
    # Image diff
    'ImageDiffEngine',
    'ImageCompareOptions',
    'ImageDiffMode',
]
