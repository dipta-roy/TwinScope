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

from app.ui.widgets.collapsible_panel import (
    CollapsiblePanel,
    CollapsibleSection,
)
from app.ui.widgets.diff_text_edit import (
    DiffTextEdit,
    DiffViewMode,
    SideBySideDiffWidget,
    UnifiedDiffWidget,
)
from app.ui.widgets.file_tree_widget import (
    FileFilterProxyModel,
    FileTreeItem,
    FileTreeModel,
    FileTreeWidget,
)
from app.ui.widgets.line_number_widget import (
    LineNumberWidget,
)
from app.ui.widgets.path_selector import (
    DualPathSelector,
    PathHistoryCombo,
    PathSelector,
)
from app.ui.widgets.search_widget import (
    FindReplaceWidget,
    SearchWidget,
)
from app.ui.widgets.status_widget import (
    CompareStatusBar,
    FileInfoWidget,
    ProgressWidget,
    StatusIndicator,
)
from app.ui.widgets.syntax_highlighter import (
    DiffAwareSyntaxHighlighter as DiffSyntaxHighlighter,
)
from app.ui.widgets.syntax_highlighter import (
    SyntaxHighlighter,
)
from app.ui.widgets.syntax_highlighter import (
    create_highlighter_for_file as get_highlighter_for_file,
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
