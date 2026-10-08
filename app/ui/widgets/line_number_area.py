"""
Line number area components for diff text editors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple, Dict
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPaintEvent, QPainter
from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
    from app.ui.widgets.diff_text_edit import DiffTextEdit


class LineNumberArea(QWidget):
    """
    Widget for displaying line numbers alongside a text editor.
    
    Supports:
    - Regular line numbers
    - Diff line numbers (left/right)
    - Click to select line
    - Current line highlighting
    """

    clicked = pyqtSignal(int)  # Line number clicked

    def __init__(
        self,
        editor: DiffTextEdit,
        side: str = 'left'  # 'left', 'right', or 'both'
    ):
        super().__init__(editor)
        self.editor = editor
        self.side = side
        from app.ui.widgets.diff_text_edit import DiffColors
        self.colors = DiffColors()
        self._width = 50
        self._line_numbers: Dict[int, Tuple[Optional[int], Optional[int]]] = {}

    def set_line_numbers(
        self,
        line_numbers: Dict[int, Tuple[Optional[int], Optional[int]]]
    ) -> None:
        """Set the line number mapping. Block index -> (left_num, right_num)"""
        self._line_numbers = line_numbers
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._width, 0)

    def update_width(self) -> None:
        """Calculate and update width based on line count."""
        if self.side == 'both':
            max_num = max(
                (max(ln[0] or 0, ln[1] or 0) for ln in self._line_numbers.values()),
                default=1
            )
            digits = max(len(str(max_num)), 3)
            self._width = 10 + self.fontMetrics().horizontalAdvance('9') * digits * 2 + 10
        else:
            digits = len(str(max(1, self.editor.blockCount())))
            self._width = 10 + self.fontMetrics().horizontalAdvance('9') * digits

        self.setFixedWidth(self._width)

    def paintEvent(self, a0: Optional[QPaintEvent]) -> None:
        """Paint line numbers."""
        if a0 is None:
            return
        painter = QPainter(self)
        painter.fillRect(a0.rect(), self.colors.line_number_bg)

        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())

        current_block = self.editor.textCursor().blockNumber()

        while block.isValid() and top <= a0.rect().bottom():
            if block.isVisible() and bottom >= a0.rect().top():
                # Get line number(s)
                if block_number in self._line_numbers:
                    left_num, right_num = self._line_numbers[block_number]
                else:
                    left_num = block_number + 1
                    right_num = block_number + 1

                # Highlight current line
                if block_number == current_block:
                    painter.fillRect(
                        0, top,
                        self._width,
                        self.fontMetrics().height(),
                        self.colors.current_line_bg
                    )

                # Draw line number(s)
                painter.setPen(self.colors.line_number_fg)

                if self.side == 'both':
                    # Draw left and right numbers
                    half_width = self._width // 2 - 5

                    if left_num is not None:
                        painter.drawText(
                            0, top,
                            half_width, self.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight,
                            str(left_num)
                        )

                    if right_num is not None:
                        painter.drawText(
                            half_width + 10, top,
                            half_width, self.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight,
                            str(right_num)
                        )
                else:
                    # Draw single number
                    num = left_num if self.side == 'left' else right_num
                    if num is not None:
                        painter.drawText(
                            0, top,
                            self._width - 5, self.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight,
                            str(num)
                        )

            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1

    def mousePressEvent(self, a0: Optional[QMouseEvent]) -> None:
        """Handle click to select line."""
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            # Find clicked line
            block = self.editor.firstVisibleBlock()
            top = int(self.editor.blockBoundingGeometry(block).translated(
                self.editor.contentOffset()).top())

            while block.isValid():
                bottom = top + int(self.editor.blockBoundingRect(block).height())
                if top <= a0.position().y() < bottom:
                    self.clicked.emit(block.blockNumber())
                    break
                block = block.next()
                top = bottom


class DualLineNumberArea(QWidget):
    """
    Line number area showing both left and right line numbers.
    
    Used for unified diff view.
    """

    def __init__(self, editor: DiffTextEdit):
        super().__init__(editor)
        self.editor = editor
        from app.ui.widgets.diff_text_edit import DiffColors
        self.colors = DiffColors()
        self._line_numbers: Dict[int, Tuple[Optional[int], Optional[int]]] = {}

    def set_line_numbers(
        self,
        line_numbers: Dict[int, Tuple[Optional[int], Optional[int]]]
    ) -> None:
        """Set line number mapping."""
        self._line_numbers = line_numbers
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._calculate_width(), 0)

    def _calculate_width(self) -> int:
        """Calculate required width."""
        max_left = max((ln[0] or 0 for ln in self._line_numbers.values()), default=0)
        max_right = max((ln[1] or 0 for ln in self._line_numbers.values()), default=0)

        digits_left = len(str(max(max_left, 1)))
        digits_right = len(str(max(max_right, 1)))

        char_width = self.fontMetrics().horizontalAdvance('9')
        return 20 + char_width * (digits_left + digits_right + 2)

    def paintEvent(self, a0: Optional[QPaintEvent]) -> None:
        """Paint dual line numbers."""
        if a0 is None:
            return
        painter = QPainter(self)
        painter.fillRect(a0.rect(), self.colors.line_number_bg)

        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())

        width = self.width()
        half = width // 2

        while block.isValid() and top <= a0.rect().bottom():
            if block.isVisible() and bottom >= a0.rect().top():
                if block_number in self._line_numbers:
                    left_num, right_num = self._line_numbers[block_number]
                else:
                    left_num, right_num = None, None

                painter.setPen(self.colors.line_number_fg)

                # Left number
                if left_num is not None:
                    painter.drawText(
                        0, top, half - 5,
                        self.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight,
                        str(left_num)
                    )

                # Right number
                if right_num is not None:
                    painter.drawText(
                        half + 5, top, half - 5,
                        self.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight,
                        str(right_num)
                    )

            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1
