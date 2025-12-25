"""
Diff module for file comparison operations.

Provides engines for comparing:
- Text files (line-by-line with various options)
- Binary files (byte-level comparison)
- Image files (visual difference detection)
"""

from app.core.diff.text_diff import (
    TextDiffEngine,
    DiffAlgorithm,
    TextCompareOptions,
)
from app.core.diff.binary_diff import (
    BinaryDiffEngine,
    BinaryCompareOptions,
)
from app.core.diff.image_diff import (
    ImageDiffEngine,
    ImageCompareOptions,
    ImageDiffMode,
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