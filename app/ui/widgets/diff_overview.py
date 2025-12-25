from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, QSize, Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPaintEvent, QMouseEvent

from app.core.models import DiffResult, DiffLineType, BinaryDiffResult, ImageDiffResult
from app.ui.widgets.diff_text_edit import DiffColors

class DiffOverviewBar(QWidget):
    """
    Vertical bar showing overview of differences.
    """
    position_clicked = pyqtSignal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(15)
        self._viewport_start: int = 0
        self._viewport_count: int = 0
        self._total_lines: int = 0
        
        # Hunks of differences for more efficient drawing and better visualization
        # List of (start_idx, count, line_type)
        self._diff_hunks: list[tuple[int, int, DiffLineType]] = []
        
        # UI settings
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def set_diff_result(self, result: DiffResult | BinaryDiffResult | ImageDiffResult | None):
        """
        Update diff results.
        
        Args:
            result: The diff result to display
        """
        self._diff_hunks = []
        self._total_lines = 0
        
        if result is None:
            self.update()
            return

        diff_lines = []
        if isinstance(result, DiffResult):
            self._total_lines = len(result.line_pairs)
            for i, pair in enumerate(result.line_pairs):
                if pair.pair_type != DiffLineType.UNCHANGED:
                    diff_lines.append((i, pair.pair_type))
            
        elif isinstance(result, BinaryDiffResult):
            self._total_lines = max(result.left_size, result.right_size)
            if self._total_lines == 0:
                self._total_lines = 1
                
            for diff in result.differences:
                if diff.is_modification:
                    type_ = DiffLineType.MODIFIED
                elif diff.is_addition:
                    type_ = DiffLineType.ADDED
                else:
                    type_ = DiffLineType.REMOVED
                diff_lines.append((diff.offset, type_))
                
        elif isinstance(result, ImageDiffResult):
            self._total_lines = max(result.left_info.height, result.right_info.height)
            if self._total_lines == 0:
                self._total_lines = 1
                
            for region in result.regions:
                # Mark high-level difference regions for images
                # Since image regions have a height, we can use it directly
                self._diff_hunks.append((region.y, region.height, DiffLineType.MODIFIED))
            
        # Group contiguous diff lines into hunks for better rendering
        if diff_lines:
            current_hunk_start = diff_lines[0][0]
            current_hunk_type = diff_lines[0][1]
            current_hunk_count = 1
            
            for i in range(1, len(diff_lines)):
                line_idx, line_type = diff_lines[i]
                # If contiguous and same type, extend hunk
                if line_idx == current_hunk_start + current_hunk_count and line_type == current_hunk_type:
                    current_hunk_count += 1
                else:
                    # Save current hunk and start new one
                    self._diff_hunks.append((current_hunk_start, current_hunk_count, current_hunk_type))
                    current_hunk_start = line_idx
                    current_hunk_type = line_type
                    current_hunk_count = 1
            
            self._diff_hunks.append((current_hunk_start, current_hunk_count, current_hunk_type))
            
        self.update()

    def set_viewport(self, start_idx: int, count: int):
        """Update the currently visible viewport range."""
        if self._viewport_start != start_idx or self._viewport_count != count:
            self._viewport_start = start_idx
            self._viewport_count = count
            self.update()
        
    def _get_color_for_type(self, line_type: DiffLineType) -> QColor:
        """Get color for diff type using strong colors for visibility."""
        if line_type == DiffLineType.ADDED:
            # Green
            return QColor(40, 167, 69)
        elif line_type == DiffLineType.REMOVED:
            # Red
            return QColor(215, 58, 73)
        elif line_type == DiffLineType.MODIFIED:
            # Yellow/Orange
            return QColor(219, 171, 9)
        elif line_type == DiffLineType.EMPTY:
            # Should not happen in diff list usually, but just in case
            return QColor(240, 240, 240)
            
        return QColor(128, 128, 128)
        
    def paintEvent(self, event: QPaintEvent):
        """Paint the diff indicators and viewport."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.fillRect(event.rect(), QColor(250, 250, 250))
        
        # Border
        painter.setPen(QColor(220, 220, 220))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        
        if self._total_lines <= 0:
            return
            
        available_h = float(self.height())
        
        # Paint diff hunks
        min_mark_height = 2.0
        for start_idx, count, line_type in self._diff_hunks:
            # Calculate position and height
            y = (start_idx / self._total_lines) * available_h
            
            # The height should be proportional to the hunk size, but at least min_mark_height
            hunk_h = (count / self._total_lines) * available_h
            display_h = max(min_mark_height, hunk_h)
            
            # Get color
            color = self._get_color_for_type(line_type)
            
            # Draw diff marker
            painter.fillRect(
                QRect(1, int(y), self.width() - 2, int(display_h)), 
                color
            )
            
        # Paint viewport indicator
        if self._viewport_count > 0:
            vy = (self._viewport_start / self._total_lines) * available_h
            vh = (self._viewport_count / self._total_lines) * available_h
            
            # Draw a semi-transparent overlay for the viewport
            viewport_color = QColor(100, 100, 255, 40) # light blue, transparent
            painter.fillRect(
                QRect(0, int(vy), self.width(), int(vh)),
                viewport_color
            )
            
            # Draw viewport border
            painter.setPen(QColor(100, 100, 255, 120))
            painter.drawRect(0, int(vy), self.width() - 1, int(vh))
            
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse click."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Calculate relative position (0.0 to 1.0)
            pos = max(0.0, min(1.0, event.position().y() / self.height()))
            self.position_clicked.emit(pos)
            
    def sizeHint(self):
        return QSize(15, 0)
