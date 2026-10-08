"""
Toolbar widgets package for TwinScope.
"""

from app.ui.widgets.toolbar.path_selector import PathSelectorButton
from app.ui.widgets.toolbar.navigation import (
    NavigationButtons,
    ViewModeSelector,
    ZoomControl,
)
from app.ui.widgets.toolbar.indicators import (
    BadgeButton,
    ProgressIndicator,
    StatusIndicator,
)
from app.ui.widgets.toolbar.selectors import (
    EncodingSelector,
    FontSizeSpinner,
    LineEndingSelector,
    SplitButton,
    ToolbarLabel,
    ToolbarSearchBox,
    ToolbarSeparator,
)
from app.ui.widgets.toolbar.action_bars import (
    CompareButton,
    CompareOptionsToolbar,
    FilterBar,
    QuickActionBar,
    RefreshButton,
    SwapButton,
    ToolbarFactory,
)

__all__ = [
    'PathSelectorButton',
    'NavigationButtons',
    'ViewModeSelector',
    'ZoomControl',
    'ProgressIndicator',
    'StatusIndicator',
    'BadgeButton',
    'EncodingSelector',
    'FontSizeSpinner',
    'LineEndingSelector',
    'SplitButton',
    'ToolbarLabel',
    'ToolbarSearchBox',
    'ToolbarSeparator',
    'CompareButton',
    'CompareOptionsToolbar',
    'FilterBar',
    'QuickActionBar',
    'RefreshButton',
    'SwapButton',
    'ToolbarFactory',
]
