"""
Selectors, inputs, and utility widgets for toolbar.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QMenu,
    QSpinBox,
    QStyle,
    QToolButton,
    QWidget,
)

from app.constants.constants import COMMON_ENCODINGS, LINE_ENDINGS


class ToolbarSearchBox(QLineEdit):
    """
    Search box optimized for toolbar use.
    
    Compact with clear button and search icon.
    """

    # Signal for search (with slight delay)
    search_triggered = pyqtSignal(str)

    def __init__(
        self,
        placeholder: str = "Search...",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self._delay_timer = QTimer()
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._emit_search)

        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMaximumWidth(200)

        # Add search icon
        style = self.style()
        if style is not None:
            self.addAction(
                style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
                QLineEdit.ActionPosition.LeadingPosition
            )

        self.textChanged.connect(self._on_text_changed)
        self.returnPressed.connect(self._emit_search)

    def _on_text_changed(self, text: str) -> None:
        """Handle text changes with delay."""
        self._delay_timer.stop()
        self._delay_timer.start(300)  # 300ms delay

    def _emit_search(self) -> None:
        """Emit search signal."""
        self.search_triggered.emit(self.text())


class ToolbarSeparator(QFrame):
    """
    Vertical separator for toolbars.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setFixedWidth(2)
        self.setMinimumHeight(20)


class ToolbarLabel(QLabel):
    """
    Label styled for toolbar use.
    """

    def __init__(
        self,
        text: str = "",
        bold: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(text, parent)

        if bold:
            font = self.font()
            font.setBold(True)
            self.setFont(font)

        self.setContentsMargins(4, 0, 4, 0)


class EncodingSelector(QComboBox):
    """
    Dropdown for selecting text encoding.
    """

    # Signal when encoding changes
    encoding_changed = pyqtSignal(str)

    COMMON_ENCODINGS = COMMON_ENCODINGS

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        for name, encoding in self.COMMON_ENCODINGS:
            self.addItem(name, encoding)

        self.setCurrentIndex(0)
        self.currentIndexChanged.connect(self._on_changed)

        self.setToolTip("File encoding")
        self.setMinimumWidth(100)

    def _on_changed(self, index: int) -> None:
        """Handle selection change."""
        encoding = self.currentData()
        self.encoding_changed.emit(encoding)

    def get_encoding(self) -> str:
        """Get selected encoding."""
        return self.currentData()

    def set_encoding(self, encoding: str) -> None:
        """Set encoding by value."""
        for i in range(self.count()):
            if self.itemData(i) == encoding:
                self.setCurrentIndex(i)
                return


class LineEndingSelector(QComboBox):
    """
    Dropdown for selecting line ending style.
    """

    # Signal when line ending changes
    line_ending_changed = pyqtSignal(str)

    LINE_ENDINGS = LINE_ENDINGS

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        for name, value in self.LINE_ENDINGS:
            self.addItem(name, value)

        self.setCurrentIndex(0)
        self.currentIndexChanged.connect(self._on_changed)

        self.setToolTip("Line ending style")
        self.setMinimumWidth(100)

    def _on_changed(self, index: int) -> None:
        """Handle selection change."""
        value = self.currentData()
        self.line_ending_changed.emit(value)

    def get_line_ending(self) -> str:
        """Get selected line ending."""
        return self.currentData()

    def set_line_ending(self, value: str) -> None:
        """Set line ending by value."""
        for i in range(self.count()):
            if self.itemData(i) == value:
                self.setCurrentIndex(i)
                return


class FontSizeSpinner(QSpinBox):
    """
    Spinner for font size selection.
    """

    def __init__(
        self,
        min_size: int = 6,
        max_size: int = 72,
        default_size: int = 10,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self.setRange(min_size, max_size)
        self.setValue(default_size)
        self.setSuffix(" pt")
        self.setToolTip("Font size")
        self.setFixedWidth(70)


class SplitButton(QToolButton):
    """
    Button with dropdown menu split from main action.
    
    Click executes default action, dropdown shows alternatives.
    """

    def __init__(
        self,
        text: str = "",
        icon: Optional[QIcon] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self._default_action: Optional[QAction] = None

        if icon:
            self.setIcon(icon)
        if text:
            self.setText(text)

        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self._menu = QMenu(self)
        self.setMenu(self._menu)

        self.clicked.connect(self._on_clicked)

    def set_default_action(self, action: QAction) -> None:
        """Set the default action (executed on button click)."""
        self._default_action = action
        self.setText(action.text())
        if action.icon():
            self.setIcon(action.icon())
        self.setToolTip(action.toolTip())

    def add_action(self, action: QAction, is_default: bool = False) -> None:
        """Add an action to the dropdown."""
        self._menu.addAction(action)

        if is_default:
            self.set_default_action(action)

    def add_separator(self) -> None:
        """Add a separator to the menu."""
        self._menu.addSeparator()

    def _on_clicked(self) -> None:
        """Handle button click."""
        if self._default_action:
            self._default_action.trigger()
