"""
Line number display widgets.

Provides standalone line number widgets that can be
paired with any text editor.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QMouseEvent, QPaintEvent
from PyQt6.QtWidgets import QWidget, QPlainTextEdit


class LineNumberWidget(QWidget):
    """
    Standalone line number widget.
    
    Can be used with any QPlainTextEdit.
    """
    
    line_clicked = pyqtSignal(int)
    line_double_clicked = pyqtSignal(int)
    
    def __init__(
        self,
        editor: QPlainTextEdit,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent or editor)
        self.editor = editor
        
        # Colors
        self.background_color = QColor(245, 245, 245)
        self.text_color = QColor(128, 128, 128)
        self.current_line_bg = QColor(255, 255, 200)
        self.current_line_fg = QColor(0, 0, 0)
        
        # Settings
        self.padding = 10
        self.min_digits = 3
        
        # Connect editor signals
        self.editor.blockCountChanged.connect(self._update_width)
        self.editor.updateRequest.connect(self._on_update_request)
        
        self._update_width()
    
    def set_colors(
        self,
        background: QColor,
        text: QColor,
        current_bg: Optional[QColor] = None,
        current_fg: Optional[QColor] = None
    ) -> None:
        """Set color scheme."""
        self.background_color = background
        self.text_color = text
        if current_bg:
            self.current_line_bg = current_bg
    # Compatibility aliases
    def update_width(self) -> None:
        self._update_width()
        
    def update_area(self, rect: QRect, dy: int) -> None:
        self._on_update_request(rect, dy)

    
    def set_line_numbers(self, line_numbers: list[Optional[int]]) -> None:
        """Set explicit line numbers to display."""
        self._line_map = line_numbers
        self.update()

    def _get_line_number(self, block_number: int) -> str:
        """Get string representation of line number."""
        if hasattr(self, '_line_map') and self._line_map:
            if 0 <= block_number < len(self._line_map):
                num = self._line_map[block_number]
                return str(num) if num is not None else ""
            return ""
        return str(block_number + 1)

    def _update_width(self, _: int = 0) -> None:
        """Update width based on line count."""
        digits = max(
            self.min_digits,
            len(str(self.editor.blockCount()))
        )
        width = self.padding * 2 + self.fontMetrics().horizontalAdvance('9') * digits
        self.setFixedWidth(width)
    
    def _on_update_request(self, rect: QRect, dy: int) -> None:
        """Handle editor update."""
        if dy:
            self.scroll(0, dy)
        else:
            self.update(0, rect.y(), self.width(), rect.height())
    
    def sizeHint(self) -> QSize:
        return QSize(self.width(), 0)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint line numbers."""
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.background_color)
        
        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        
        # Get block geometry
        top = int(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())
        
        # Current line
        current_block = self.editor.textCursor().blockNumber()
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = self._get_line_number(block_number)
                
                # Highlight current line
                if block_number == current_block:
                    painter.fillRect(
                        0, top, self.width(),
                        int(self.editor.blockBoundingRect(block).height()),
                        self.current_line_bg
                    )
                    painter.setPen(self.current_line_fg)
                else:
                    painter.setPen(self.text_color)
                
                painter.drawText(
                    0, top,
                    self.width() - self.padding,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    number
                )
            
            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse click."""
        if event.button() == Qt.MouseButton.LeftButton:
            line = self._line_at_position(event.position().y())
            if line >= 0:
                self.line_clicked.emit(line)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle double click."""
        if event.button() == Qt.MouseButton.LeftButton:
            line = self._line_at_position(event.position().y())
            if line >= 0:
                self.line_double_clicked.emit(line)
    
    def _line_at_position(self, y: float) -> int:
        """Get line number at y position."""
        block = self.editor.firstVisibleBlock()
        top = int(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        
        while block.isValid():
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            if top <= y < bottom:
                return block.blockNumber()
            block = block.next()
            top = bottom
        
        return -1


class ChangeMarkerWidget(QWidget):
    """
    Widget showing change markers alongside an editor.
    
    Shows colored markers indicating additions, deletions, modifications.
    """
    
    def __init__(
        self,
        editor: QPlainTextEdit,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent or editor)
        self.editor = editor
        
        # Colors
        self.added_color = QColor(100, 200, 100)
        self.removed_color = QColor(200, 100, 100)
        self.modified_color = QColor(200, 200, 100)
        
        # Markers: line_number -> 'added'|'removed'|'modified'
        self._markers: dict[int, str] = {}
        
        self.setFixedWidth(8)
        
        self.editor.updateRequest.connect(self._on_update_request)
    
    def set_markers(self, markers: dict[int, str]) -> None:
        """Set change markers."""
        self._markers = markers
        self.update()
    
    def clear_markers(self) -> None:
        """Clear all markers."""
        self._markers.clear()
        self.update()
    
    def _on_update_request(self, rect: QRect, dy: int) -> None:
        """Handle editor update."""
        if dy:
            self.scroll(0, dy)
        else:
            self.update(0, rect.y(), self.width(), rect.height())
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint change markers."""
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(250, 250, 250))
        
        if not self._markers:
            return
        
        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        
        top = int(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if block_number in self._markers:
                    marker_type = self._markers[block_number]
                    
                    if marker_type == 'added':
                        color = self.added_color
                    elif marker_type == 'removed':
                        color = self.removed_color
                    else:
                        color = self.modified_color
                    
                    painter.fillRect(
                        2, top + 2,
                        4, int(self.editor.blockBoundingRect(block).height()) - 4,
                        color
                    )
            
            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1