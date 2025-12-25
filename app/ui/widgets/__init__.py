"""
Reusable UI widgets for the file comparison application.

Provides specialized widgets for:
- Diff display and editing
- File/folder selection
- Tree views
- Progress indicators
- Search functionality
- Syntax highlighting
"""

from app.ui.widgets.diff_text_edit import (
    DiffTextEdit,
    SideBySideDiffWidget,
    UnifiedDiffWidget,
    DiffViewMode,
)
from app.ui.widgets.line_number_widget import (
    LineNumberWidget,
)
from app.ui.widgets.file_tree_widget import (
    FileTreeWidget,
    FileTreeModel,
    FileTreeItem,
    FileFilterProxyModel,
)
from app.ui.widgets.path_selector import (
    PathSelector,
    DualPathSelector,
    PathHistoryCombo,
)
from app.ui.widgets.status_widget import (
    StatusIndicator,
    CompareStatusBar,
    ProgressWidget,
    FileInfoWidget,
)
from app.ui.widgets.search_widget import (
    SearchWidget,
    FindReplaceWidget,
)
from app.ui.widgets.syntax_highlighter import (
    SyntaxHighlighter,
    DiffAwareSyntaxHighlighter as DiffSyntaxHighlighter,
    create_highlighter_for_file as get_highlighter_for_file,
)

from app.ui.widgets.collapsible_panel import (
    CollapsiblePanel,
    CollapsibleSection,
)

__all__ = [
    # Diff widgets
    'DiffTextEdit',
    'SideBySideDiffWidget',
    'UnifiedDiffWidget',
    'DiffViewMode',
    # Line numbers
    'LineNumberWidget',
    # File tree
    'FileTreeWidget',
    'FileTreeModel',
    'FileTreeItem',
    'FileFilterProxyModel',
    # Path selection
    'PathSelector',
    'DualPathSelector',
    'PathHistoryCombo',
    # Status
    'StatusIndicator',
    'CompareStatusBar',
    'ProgressWidget',
    'FileInfoWidget',
    # Search
    'SearchWidget',
    'FindReplaceWidget',
    # Syntax
    'SyntaxHighlighter',
    'DiffSyntaxHighlighter',
    'get_highlighter_for_file',

    # Panels
    'CollapsiblePanel',
    'CollapsibleSection',
]