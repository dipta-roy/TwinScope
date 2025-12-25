"""
Collapsible panel widgets for the comparison application.

Provides:
- CollapsiblePanel - Basic expandable/collapsible panel
- CollapsibleSection - Section with header that collapses content
- CollapsibleSidebar - Sidebar that minimizes to icons
- AccordionWidget - Multiple exclusive collapsible sections
- CollapsibleGroupBox - Collapsible group box
- AnimatedCollapsiblePanel - Panel with smooth animation
- NestedCollapsiblePanel - Panels that can contain other panels
- ResizableCollapsiblePanel - Collapsible with resize handle
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Dict, Callable, Any

from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QSize, QTimer, QPoint, QRect,
    QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
    QAbstractAnimation, pyqtProperty, QEvent, QObject
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QIcon, QPixmap, QPen, QBrush,
    QPalette, QCursor, QFontMetrics, QMouseEvent, QPaintEvent,
    QEnterEvent, QResizeEvent, QPolygon, QTransform
)
from PyQt6.QtWidgets import (
    QWidget, QToolButton, QPushButton, QLabel, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSizePolicy,
    QScrollArea, QSpacerItem, QStyle, QStyleOption,
    QGraphicsOpacityEffect, QSplitter, QStackedWidget,
    QApplication, QLayout
)


class CollapseDirection(Enum):
    """Direction of collapse animation."""
    VERTICAL = auto()
    HORIZONTAL = auto()


class CollapseState(Enum):
    """State of collapsible widget."""
    EXPANDED = auto()
    COLLAPSED = auto()
    EXPANDING = auto()
    COLLAPSING = auto()


class CollapsibleHeader(QFrame):
    """
    Header widget for collapsible panels.
    
    Features:
    - Title with icon
    - Expand/collapse arrow
    - Optional action buttons
    - Hover highlighting
    - Double-click to toggle
    """
    
    # Signal when clicked
    clicked = pyqtSignal()
    
    # Signal for double click
    double_clicked = pyqtSignal()
    
    def __init__(
        self,
        title: str = "",
        icon: Optional[QIcon] = None,
        collapsible: bool = True,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._title = title
        self._icon = icon
        self._collapsible = collapsible
        self._expanded = True
        self._hover = False
        self._action_buttons: List[QToolButton] = []
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the header UI."""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._collapsible 
                       else Qt.CursorShape.ArrowCursor)
        self.setMinimumHeight(28)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Arrow indicator
        self.arrow_label = QLabel()
        self.arrow_label.setFixedSize(16, 16)
        self._update_arrow()
        if self._collapsible:
            layout.addWidget(self.arrow_label)
        
        # Icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        if self._icon:
            self.icon_label.setPixmap(self._icon.pixmap(16, 16))
            layout.addWidget(self.icon_label)
        
        # Title
        self.title_label = QLabel(self._title)
        self.title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Action buttons container
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(2)
        layout.addLayout(self.actions_layout)
        
        self._update_style()
    
    def _update_arrow(self) -> None:
        """Update the arrow indicator."""
        if self._expanded:
            self.arrow_label.setText("▼")
        else:
            self.arrow_label.setText("▶")
    
    def _update_style(self) -> None:
        """Update visual style."""
        if self._hover:
            self.setStyleSheet("""
                CollapsibleHeader {
                    background-color: #e8e8e8;
                    border-radius: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                CollapsibleHeader {
                    background-color: #f0f0f0;
                    border-radius: 4px;
                }
            """)
    
    def set_expanded(self, expanded: bool) -> None:
        """Set expanded state."""
        self._expanded = expanded
        self._update_arrow()
    
    def is_expanded(self) -> bool:
        """Get expanded state."""
        return self._expanded
    
    def set_title(self, title: str) -> None:
        """Set the header title."""
        self._title = title
        self.title_label.setText(title)
    
    def set_icon(self, icon: QIcon) -> None:
        """Set the header icon."""
        self._icon = icon
        self.icon_label.setPixmap(icon.pixmap(16, 16))
        self.icon_label.setVisible(True)
    
    def add_action_button(
        self,
        icon: QIcon | str,
        tooltip: str = "",
        callback: Optional[Callable] = None
    ) -> QToolButton:
        """Add an action button to the header."""
        btn = QToolButton()
        
        if isinstance(icon, str):
            btn.setText(icon)
        else:
            btn.setIcon(icon)
        
        btn.setToolTip(tooltip)
        btn.setAutoRaise(True)
        btn.setFixedSize(20, 20)
        
        if callback:
            btn.clicked.connect(callback)
        
        self._action_buttons.append(btn)
        self.actions_layout.addWidget(btn)
        
        return btn
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle double click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)
    
    def enterEvent(self, event: QEnterEvent) -> None:
        """Handle mouse enter."""
        self._hover = True
        self._update_style()
        super().enterEvent(event)
    
    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave."""
        self._hover = False
        self._update_style()
        super().leaveEvent(event)


class CollapsiblePanel(QWidget):
    """
    Basic collapsible panel widget.
    
    Features:
    - Clickable header to toggle
    - Smooth animation
    - Custom content widget
    - Save/restore state
    """
    
    # Signal when expanded/collapsed
    toggled = pyqtSignal(bool)  # True = expanded
    
    # Signal before toggle
    about_to_toggle = pyqtSignal(bool)
    
    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
        animated: bool = True,
        initially_expanded: bool = True
    ):
        super().__init__(parent)
        
        self._title = title
        self._animated = animated
        self._expanded = initially_expanded
        self._content_widget: Optional[QWidget] = None
        self._animation: Optional[QPropertyAnimation] = None
        self._collapsed_height = 0
        self._expanded_height = 0
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        self.header = CollapsibleHeader(self._title)
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)
        
        # Content container
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(4)
        layout.addWidget(self.content_container)
        
        # Animation
        if self._animated:
            self._animation = QPropertyAnimation(self.content_container, b"maximumHeight")
            self._animation.setDuration(200)
            self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self._animation.finished.connect(self._on_animation_finished)
        
        # Set initial state
        self.header.set_expanded(self._expanded)
        if not self._expanded:
            self.content_container.setMaximumHeight(0)
            self.content_container.setVisible(False)
    
    def set_content_widget(self, widget: QWidget) -> None:
        """Set the content widget."""
        # Remove old widget
        if self._content_widget:
            self.content_layout.removeWidget(self._content_widget)
            self._content_widget.setParent(None)
        
        self._content_widget = widget
        self.content_layout.addWidget(widget)
        
        # Update heights
        self._update_heights()
    
    def get_content_widget(self) -> Optional[QWidget]:
        """Get the content widget."""
        return self._content_widget
    
    def add_widget(self, widget: QWidget) -> None:
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)
        self._update_heights()
    
    def add_layout(self, layout: QLayout) -> None:
        """Add a layout to the content area."""
        self.content_layout.addLayout(layout)
        self._update_heights()
    
    def _update_heights(self) -> None:
        """Update stored heights for animation."""
        self._collapsed_height = self.header.sizeHint().height()
        
        # Calculate expanded height
        self.content_container.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        self._expanded_height = self.content_container.sizeHint().height()
        
        if not self._expanded:
            self.content_container.setMaximumHeight(0)
    
    def toggle(self) -> None:
        """Toggle expanded/collapsed state."""
        self.set_expanded(not self._expanded)
    
    def set_expanded(self, expanded: bool) -> None:
        """Set expanded state."""
        if expanded == self._expanded:
            return
        
        self.about_to_toggle.emit(expanded)
        self._expanded = expanded
        self.header.set_expanded(expanded)
        
        self._update_heights()
        
        if self._animated and self._animation:
            self.content_container.setVisible(True)
            
            if expanded:
                self._animation.setStartValue(0)
                self._animation.setEndValue(self._expanded_height)
            else:
                self._animation.setStartValue(self._expanded_height)
                self._animation.setEndValue(0)
            
            self._animation.start()
        else:
            if expanded:
                self.content_container.setMaximumHeight(16777215)
                self.content_container.setVisible(True)
            else:
                self.content_container.setMaximumHeight(0)
                self.content_container.setVisible(False)
            
            self.toggled.emit(expanded)
    
    def is_expanded(self) -> bool:
        """Check if panel is expanded."""
        return self._expanded
    
    def expand(self) -> None:
        """Expand the panel."""
        self.set_expanded(True)
    
    def collapse(self) -> None:
        """Collapse the panel."""
        self.set_expanded(False)
    
    def _on_animation_finished(self) -> None:
        """Handle animation completion."""
        if not self._expanded:
            self.content_container.setVisible(False)
        else:
            # Remove max height constraint when expanded
            self.content_container.setMaximumHeight(16777215)
        
        self.toggled.emit(self._expanded)
    
    def set_title(self, title: str) -> None:
        """Set the panel title."""
        self._title = title
        self.header.set_title(title)
    
    def set_icon(self, icon: QIcon) -> None:
        """Set the panel icon."""
        self.header.set_icon(icon)
    
    def add_header_action(
        self,
        icon: QIcon | str,
        tooltip: str = "",
        callback: Optional[Callable] = None
    ) -> QToolButton:
        """Add action button to header."""
        return self.header.add_action_button(icon, tooltip, callback)


class CollapsibleSection(QWidget):
    """
    Collapsible section for use within panels.
    
    Lighter weight than full CollapsiblePanel.
    """
    
    toggled = pyqtSignal(bool)
    
    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._title = title
        self._expanded = True
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the section UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # Header button
        self.header_btn = QToolButton()
        self.header_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.header_btn.setText(self._title)
        self.header_btn.setCheckable(True)
        self.header_btn.setChecked(True)
        self.header_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        self.header_btn.setStyleSheet("""
            QToolButton {
                border: none;
                background-color: transparent;
                font-weight: bold;
                padding: 4px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.header_btn.toggled.connect(self._on_toggled)
        layout.addWidget(self.header_btn)
        
        # Content
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 4, 4, 4)
        self.content_layout.setSpacing(4)
        layout.addWidget(self.content)
    
    def _on_toggled(self, checked: bool) -> None:
        """Handle toggle."""
        self._expanded = checked
        
        if checked:
            self.header_btn.setArrowType(Qt.ArrowType.DownArrow)
            self.content.setVisible(True)
        else:
            self.header_btn.setArrowType(Qt.ArrowType.RightArrow)
            self.content.setVisible(False)
        
        self.toggled.emit(checked)
    
    def add_widget(self, widget: QWidget) -> None:
        """Add widget to section."""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout: QLayout) -> None:
        """Add layout to section."""
        self.content_layout.addLayout(layout)
    
    def set_expanded(self, expanded: bool) -> None:
        """Set expanded state."""
        self.header_btn.setChecked(expanded)
    
    def is_expanded(self) -> bool:
        """Check if expanded."""
        return self._expanded


class AccordionWidget(QWidget):
    """
    Accordion widget with mutually exclusive panels.
    
    Only one panel can be expanded at a time.
    """
    
    # Signal when active panel changes
    active_changed = pyqtSignal(int)  # index
    
    def __init__(
        self,
        exclusive: bool = True,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._exclusive = exclusive
        self._panels: List[CollapsiblePanel] = []
        self._active_index = -1
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the accordion UI."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        
        # Add stretch at end
        self._layout.addStretch()
    
    def add_panel(
        self,
        title: str,
        widget: Optional[QWidget] = None,
        expanded: bool = False
    ) -> CollapsiblePanel:
        """Add a panel to the accordion."""
        panel = CollapsiblePanel(title, self, animated=True, initially_expanded=False)
        
        if widget:
            panel.set_content_widget(widget)
        
        # Insert before stretch
        index = self._layout.count() - 1
        self._layout.insertWidget(index, panel)
        
        panel_index = len(self._panels)
        self._panels.append(panel)
        
        # Connect toggle signal
        panel.about_to_toggle.connect(
            lambda exp, idx=panel_index: self._on_panel_toggling(idx, exp)
        )
        
        if expanded:
            panel.set_expanded(True)
            self._active_index = panel_index
        
        return panel
    
    def _on_panel_toggling(self, index: int, expanding: bool) -> None:
        """Handle panel toggle."""
        if not expanding:
            if index == self._active_index:
                self._active_index = -1
            return
        
        if self._exclusive:
            # Collapse other panels
            for i, panel in enumerate(self._panels):
                if i != index and panel.is_expanded():
                    panel.set_expanded(False)
        
        self._active_index = index
        self.active_changed.emit(index)
    
    def get_panel(self, index: int) -> Optional[CollapsiblePanel]:
        """Get panel by index."""
        if 0 <= index < len(self._panels):
            return self._panels[index]
        return None
    
    def set_active(self, index: int) -> None:
        """Set active panel by index."""
        if 0 <= index < len(self._panels):
            self._panels[index].set_expanded(True)
    
    def get_active_index(self) -> int:
        """Get index of active panel."""
        return self._active_index
    
    def count(self) -> int:
        """Get number of panels."""
        return len(self._panels)
    
    def expand_all(self) -> None:
        """Expand all panels (only if not exclusive)."""
        if not self._exclusive:
            for panel in self._panels:
                panel.set_expanded(True)
    
    def collapse_all(self) -> None:
        """Collapse all panels."""
        for panel in self._panels:
            panel.set_expanded(False)
        self._active_index = -1


class CollapsibleSidebar(QWidget):
    """
    Collapsible sidebar that minimizes to icons.
    
    Features:
    - Collapse to icon-only mode
    - Expand on hover (optional)
    - Pinnable
    - Smooth animation
    """
    
    # Signal when collapsed/expanded
    collapsed_changed = pyqtSignal(bool)
    
    # Signal when pinned/unpinned
    pinned_changed = pyqtSignal(bool)
    
    def __init__(
        self,
        position: str = "left",  # "left" or "right"
        collapsed_width: int = 48,
        expanded_width: int = 250,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._position = position
        self._collapsed_width = collapsed_width
        self._expanded_width = expanded_width
        self._collapsed = False
        self._pinned = True
        self._hover_expand = True
        self._hover_timer = QTimer()
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._on_hover_timeout)
        
        self._items: List[Dict[str, Any]] = []
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the sidebar UI."""
        self.setMinimumWidth(self._collapsed_width)
        self.setMaximumWidth(self._expanded_width)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Header with pin button
        header_layout = QHBoxLayout()
        
        self.title_label = QLabel("Sidebar")
        self.title_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.pin_btn = QToolButton()
        self.pin_btn.setText("📌")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(True)
        self.pin_btn.setToolTip("Pin sidebar")
        self.pin_btn.toggled.connect(self._on_pin_toggled)
        header_layout.addWidget(self.pin_btn)
        
        self.collapse_btn = QToolButton()
        self._update_collapse_button()
        self.collapse_btn.clicked.connect(self.toggle)
        header_layout.addWidget(self.collapse_btn)
        
        layout.addLayout(header_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)
        
        # Items container
        self.items_widget = QWidget()
        self.items_layout = QVBoxLayout(self.items_widget)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(2)
        
        # Scroll area for items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.items_widget)
        layout.addWidget(scroll)
        
        # Animation
        self._animation = QPropertyAnimation(self, b"maximumWidth")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self._update_for_state()
    
    def _update_collapse_button(self) -> None:
        """Update collapse button appearance."""
        if self._collapsed:
            arrow = "▶" if self._position == "left" else "◀"
            tooltip = "Expand sidebar"
        else:
            arrow = "◀" if self._position == "left" else "▶"
            tooltip = "Collapse sidebar"
        
        self.collapse_btn.setText(arrow)
        self.collapse_btn.setToolTip(tooltip)
    
    def _update_for_state(self) -> None:
        """Update UI for collapsed/expanded state."""
        self._update_collapse_button()
        
        # Show/hide labels
        self.title_label.setVisible(not self._collapsed)
        self.pin_btn.setVisible(not self._collapsed)
        
        for item in self._items:
            if 'label' in item:
                item['label'].setVisible(not self._collapsed)
    
    def add_item(
        self,
        icon: QIcon | str,
        text: str,
        callback: Optional[Callable] = None,
        tooltip: str = ""
    ) -> QToolButton:
        """Add an item to the sidebar."""
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(8)
        
        # Icon button
        btn = QToolButton()
        if isinstance(icon, str):
            btn.setText(icon)
            font = btn.font()
            font.setPointSize(16)
            btn.setFont(font)
        else:
            btn.setIcon(icon)
            btn.setIconSize(QSize(24, 24))
        
        btn.setToolTip(tooltip or text)
        btn.setAutoRaise(True)
        btn.setFixedSize(36, 36)
        
        if callback:
            btn.clicked.connect(callback)
        
        container_layout.addWidget(btn)
        
        # Label
        label = QLabel(text)
        label.setVisible(not self._collapsed)
        container_layout.addWidget(label)
        
        container_layout.addStretch()
        
        self.items_layout.addWidget(container)
        
        self._items.append({
            'button': btn,
            'label': label,
            'container': container,
            'text': text,
        })
        
        return btn
    
    def add_separator(self) -> None:
        """Add a separator line."""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.items_layout.addWidget(separator)
    
    def add_stretch(self) -> None:
        """Add stretch to push items up."""
        self.items_layout.addStretch()
    
    def toggle(self) -> None:
        """Toggle collapsed state."""
        self.set_collapsed(not self._collapsed)
    
    def set_collapsed(self, collapsed: bool) -> None:
        """Set collapsed state."""
        if collapsed == self._collapsed:
            return
        
        self._collapsed = collapsed
        
        if collapsed:
            self._animation.setStartValue(self._expanded_width)
            self._animation.setEndValue(self._collapsed_width)
        else:
            self._animation.setStartValue(self._collapsed_width)
            self._animation.setEndValue(self._expanded_width)
        
        self._animation.start()
        self._update_for_state()
        self.collapsed_changed.emit(collapsed)
    
    def is_collapsed(self) -> bool:
        """Check if collapsed."""
        return self._collapsed
    
    def _on_pin_toggled(self, pinned: bool) -> None:
        """Handle pin toggle."""
        self._pinned = pinned
        self.pinned_changed.emit(pinned)
    
    def is_pinned(self) -> bool:
        """Check if pinned."""
        return self._pinned
    
    def set_hover_expand(self, enabled: bool) -> None:
        """Enable/disable hover expansion."""
        self._hover_expand = enabled
    
    def enterEvent(self, event: QEnterEvent) -> None:
        """Handle mouse enter."""
        if self._collapsed and self._hover_expand and not self._pinned:
            self._hover_timer.start(300)
        super().enterEvent(event)
    
    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave."""
        self._hover_timer.stop()
        
        if not self._collapsed and self._hover_expand and not self._pinned:
            self.set_collapsed(True)
        
        super().leaveEvent(event)
    
    def _on_hover_timeout(self) -> None:
        """Handle hover timeout."""
        if self._collapsed and self._hover_expand:
            self.set_collapsed(False)
    
    def set_title(self, title: str) -> None:
        """Set sidebar title."""
        self.title_label.setText(title)


class CollapsibleGroupBox(QFrame):
    """
    Collapsible group box widget.
    
    Similar to QGroupBox but can collapse its content.
    """
    
    toggled = pyqtSignal(bool)
    
    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
        checkable: bool = True
    ):
        super().__init__(parent)
        
        self._title = title
        self._checkable = checkable
        self._checked = True
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the group box UI."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Plain)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #e8e8e8;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
        """)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 6, 8, 6)
        
        if self._checkable:
            self.checkbox = QToolButton()
            self.checkbox.setCheckable(True)
            self.checkbox.setChecked(True)
            self.checkbox.setArrowType(Qt.ArrowType.DownArrow)
            self.checkbox.setAutoRaise(True)
            self.checkbox.toggled.connect(self._on_toggled)
            header_layout.addWidget(self.checkbox)
        
        self.title_label = QLabel(self._title)
        self.title_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        layout.addWidget(header_widget)
        
        # Content
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.content_widget)
    
    def _on_toggled(self, checked: bool) -> None:
        """Handle toggle."""
        self._checked = checked
        
        if checked:
            self.checkbox.setArrowType(Qt.ArrowType.DownArrow)
            self.content_widget.setVisible(True)
        else:
            self.checkbox.setArrowType(Qt.ArrowType.RightArrow)
            self.content_widget.setVisible(False)
        
        self.toggled.emit(checked)
    
    def set_title(self, title: str) -> None:
        """Set the group title."""
        self._title = title
        self.title_label.setText(title)
    
    def title(self) -> str:
        """Get the group title."""
        return self._title
    
    def is_checked(self) -> bool:
        """Check if expanded/checked."""
        return self._checked
    
    def set_checked(self, checked: bool) -> None:
        """Set checked/expanded state."""
        if self._checkable:
            self.checkbox.setChecked(checked)
    
    def layout(self) -> QVBoxLayout:
        """Get content layout."""
        return self.content_layout
    
    def add_widget(self, widget: QWidget) -> None:
        """Add widget to content."""
        self.content_layout.addWidget(widget)


class AnimatedCollapsiblePanel(QWidget):
    """
    Collapsible panel with advanced animations.
    
    Features:
    - Fade animation
    - Slide animation
    - Combined effects
    - Customizable easing
    """
    
    toggled = pyqtSignal(bool)
    
    class AnimationType(Enum):
        SLIDE = auto()
        FADE = auto()
        SLIDE_FADE = auto()
    
    def __init__(
        self,
        title: str = "",
        animation_type: AnimationType = AnimationType.SLIDE_FADE,
        duration: int = 250,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._title = title
        self._animation_type = animation_type
        self._duration = duration
        self._expanded = True
        
        self._setup_ui()
        self._setup_animations()
    
    def _setup_ui(self) -> None:
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        self.header = CollapsibleHeader(self._title)
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)
        
        # Content container with clipping
        self.content_container = QWidget()
        self.content_container.setObjectName("contentContainer")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.content_container)
        
        # Opacity effect for fade
        self._opacity_effect = QGraphicsOpacityEffect(self.content_container)
        self._opacity_effect.setOpacity(1.0)
        self.content_container.setGraphicsEffect(self._opacity_effect)
    
    def _setup_animations(self) -> None:
        """Setup animations."""
        # Height animation
        self._height_animation = QPropertyAnimation(
            self.content_container, b"maximumHeight"
        )
        self._height_animation.setDuration(self._duration)
        self._height_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        # Opacity animation
        self._opacity_animation = QPropertyAnimation(
            self._opacity_effect, b"opacity"
        )
        self._opacity_animation.setDuration(self._duration)
        self._opacity_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        # Animation group
        self._animation_group = QParallelAnimationGroup()
        
        if self._animation_type in (self.AnimationType.SLIDE, self.AnimationType.SLIDE_FADE):
            self._animation_group.addAnimation(self._height_animation)
        
        if self._animation_type in (self.AnimationType.FADE, self.AnimationType.SLIDE_FADE):
            self._animation_group.addAnimation(self._opacity_animation)
        
        self._animation_group.finished.connect(self._on_animation_finished)
    
    def toggle(self) -> None:
        """Toggle expanded state."""
        self.set_expanded(not self._expanded)
    
    def set_expanded(self, expanded: bool) -> None:
        """Set expanded state with animation."""
        if expanded == self._expanded:
            return
        
        self._expanded = expanded
        self.header.set_expanded(expanded)
        
        # Get content height
        self.content_container.setMaximumHeight(16777215)
        content_height = self.content_container.sizeHint().height()
        
        if not expanded:
            self.content_container.setMaximumHeight(content_height)
        
        # Setup animations
        if expanded:
            # Expanding
            self._height_animation.setStartValue(0)
            self._height_animation.setEndValue(content_height)
            self._opacity_animation.setStartValue(0.0)
            self._opacity_animation.setEndValue(1.0)
            self.content_container.setVisible(True)
        else:
            # Collapsing
            self._height_animation.setStartValue(content_height)
            self._height_animation.setEndValue(0)
            self._opacity_animation.setStartValue(1.0)
            self._opacity_animation.setEndValue(0.0)
        
        self._animation_group.start()
    
    def _on_animation_finished(self) -> None:
        """Handle animation completion."""
        if not self._expanded:
            self.content_container.setVisible(False)
        else:
            self.content_container.setMaximumHeight(16777215)
        
        self.toggled.emit(self._expanded)
    
    def is_expanded(self) -> bool:
        """Check if expanded."""
        return self._expanded
    
    def add_widget(self, widget: QWidget) -> None:
        """Add widget to content."""
        self.content_layout.addWidget(widget)
    
    def set_animation_duration(self, duration: int) -> None:
        """Set animation duration in ms."""
        self._duration = duration
        self._height_animation.setDuration(duration)
        self._opacity_animation.setDuration(duration)


class NestedCollapsiblePanel(QWidget):
    """
    Collapsible panel that can contain child panels.
    
    Supports hierarchical organization of content.
    """
    
    toggled = pyqtSignal(bool)
    
    def __init__(
        self,
        title: str = "",
        level: int = 0,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._title = title
        self._level = level
        self._expanded = True
        self._children: List[NestedCollapsiblePanel] = []
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with indentation based on level
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4 + (self._level * 16), 4, 4, 4)
        header_layout.setSpacing(4)
        
        # Arrow
        self.arrow_btn = QToolButton()
        self.arrow_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.arrow_btn.setAutoRaise(True)
        self.arrow_btn.setFixedSize(20, 20)
        self.arrow_btn.clicked.connect(self.toggle)
        header_layout.addWidget(self.arrow_btn)
        
        # Title
        self.title_label = QLabel(self._title)
        font_size = max(9, 12 - self._level)
        font = self.title_label.font()
        font.setPointSize(font_size)
        if self._level == 0:
            font.setBold(True)
        self.title_label.setFont(font)
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        layout.addWidget(header_widget)
        
        # Content container
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        layout.addWidget(self.content_widget)
        
        # Styling based on level
        bg_color = max(240, 255 - (self._level * 10))
        header_widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color}, {bg_color}, {bg_color});
            }}
        """)
    
    def toggle(self) -> None:
        """Toggle expanded state."""
        self._expanded = not self._expanded
        
        if self._expanded:
            self.arrow_btn.setArrowType(Qt.ArrowType.DownArrow)
            self.content_widget.setVisible(True)
        else:
            self.arrow_btn.setArrowType(Qt.ArrowType.RightArrow)
            self.content_widget.setVisible(False)
        
        self.toggled.emit(self._expanded)
    
    def add_child_panel(self, title: str) -> 'NestedCollapsiblePanel':
        """Add a child panel."""
        child = NestedCollapsiblePanel(title, self._level + 1, self)
        self._children.append(child)
        self.content_layout.addWidget(child)
        return child
    
    def add_widget(self, widget: QWidget) -> None:
        """Add a widget to content."""
        # Create a container with proper indentation
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins((self._level + 1) * 16, 2, 4, 2)
        container_layout.addWidget(widget)
        self.content_layout.addWidget(container)
    
    def expand_all(self) -> None:
        """Expand this panel and all children."""
        if not self._expanded:
            self.toggle()
        
        for child in self._children:
            child.expand_all()
    
    def collapse_all(self) -> None:
        """Collapse this panel and all children."""
        for child in self._children:
            child.collapse_all()
        
        if self._expanded:
            self.toggle()


class ResizableCollapsiblePanel(QWidget):
    """
    Collapsible panel with resize handle.
    
    User can drag to resize the panel height/width.
    """
    
    toggled = pyqtSignal(bool)
    resized = pyqtSignal(int)  # new size
    
    def __init__(
        self,
        title: str = "",
        direction: CollapseDirection = CollapseDirection.VERTICAL,
        min_size: int = 100,
        max_size: int = 500,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._title = title
        self._direction = direction
        self._min_size = min_size
        self._max_size = max_size
        self._current_size = 200
        self._expanded = True
        self._resizing = False
        self._resize_start = QPoint()
        self._size_start = 0
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the panel UI."""
        if self._direction == CollapseDirection.VERTICAL:
            layout = QVBoxLayout(self)
        else:
            layout = QHBoxLayout(self)
        
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        self.header = CollapsibleHeader(self._title)
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)
        
        # Content
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        
        if self._direction == CollapseDirection.VERTICAL:
            self.content_widget.setMinimumHeight(self._min_size)
            self.content_widget.setMaximumHeight(self._max_size)
            self.content_widget.setFixedHeight(self._current_size)
        else:
            self.content_widget.setMinimumWidth(self._min_size)
            self.content_widget.setMaximumWidth(self._max_size)
            self.content_widget.setFixedWidth(self._current_size)
        
        layout.addWidget(self.content_widget)
        
        # Resize handle
        self.resize_handle = QFrame()
        self.resize_handle.setFrameShape(QFrame.Shape.HLine if 
            self._direction == CollapseDirection.VERTICAL else QFrame.Shape.VLine)
        self.resize_handle.setFrameShadow(QFrame.Shadow.Sunken)
        
        if self._direction == CollapseDirection.VERTICAL:
            self.resize_handle.setFixedHeight(5)
            self.resize_handle.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.resize_handle.setFixedWidth(5)
            self.resize_handle.setCursor(Qt.CursorShape.SizeHorCursor)
        
        self.resize_handle.setStyleSheet("""
            QFrame {
                background-color: #d0d0d0;
            }
            QFrame:hover {
                background-color: #0078d4;
            }
        """)
        
        self.resize_handle.installEventFilter(self)
        layout.addWidget(self.resize_handle)
    
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Handle resize handle events."""
        if obj == self.resize_handle:
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = event
                if mouse_event.button() == Qt.MouseButton.LeftButton:
                    self._resizing = True
                    self._resize_start = mouse_event.globalPosition().toPoint()
                    self._size_start = self._current_size
                    return True
            
            elif event.type() == QEvent.Type.MouseMove:
                if self._resizing:
                    mouse_event = event
                    pos = mouse_event.globalPosition().toPoint()
                    
                    if self._direction == CollapseDirection.VERTICAL:
                        delta = pos.y() - self._resize_start.y()
                    else:
                        delta = pos.x() - self._resize_start.x()
                    
                    new_size = max(self._min_size, 
                                  min(self._max_size, self._size_start + delta))
                    
                    self._set_content_size(new_size)
                    return True
            
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._resizing:
                    self._resizing = False
                    self.resized.emit(self._current_size)
                    return True
        
        return super().eventFilter(obj, event)
    
    def _set_content_size(self, size: int) -> None:
        """Set content size."""
        self._current_size = size
        
        if self._direction == CollapseDirection.VERTICAL:
            self.content_widget.setFixedHeight(size)
        else:
            self.content_widget.setFixedWidth(size)
    
    def toggle(self) -> None:
        """Toggle expanded state."""
        self._expanded = not self._expanded
        self.header.set_expanded(self._expanded)
        self.content_widget.setVisible(self._expanded)
        self.resize_handle.setVisible(self._expanded)
        self.toggled.emit(self._expanded)
    
    def is_expanded(self) -> bool:
        """Check if expanded."""
        return self._expanded
    
    def add_widget(self, widget: QWidget) -> None:
        """Add widget to content."""
        self.content_layout.addWidget(widget)
    
    def get_size(self) -> int:
        """Get current content size."""
        return self._current_size
    
    def set_size(self, size: int) -> None:
        """Set content size."""
        size = max(self._min_size, min(self._max_size, size))
        self._set_content_size(size)


class CollapsibleSplitterHandle(QWidget):
    """
    Custom splitter handle with collapse button.
    """
    
    collapse_clicked = pyqtSignal()
    
    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._orientation = orientation
        self._hover = False
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the handle UI."""
        if self._orientation == Qt.Orientation.Horizontal:
            self.setFixedWidth(8)
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            layout = QVBoxLayout(self)
        else:
            self.setFixedHeight(8)
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            layout = QHBoxLayout(self)
        
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Collapse button
        self.collapse_btn = QToolButton()
        self.collapse_btn.setFixedSize(16, 16)
        self.collapse_btn.setAutoRaise(True)
        self.collapse_btn.clicked.connect(self.collapse_clicked.emit)
        self._update_button()
        
        layout.addStretch()
        layout.addWidget(self.collapse_btn)
        layout.addStretch()
        
        self.collapse_btn.setVisible(False)
    
    def _update_button(self) -> None:
        """Update button appearance."""
        if self._orientation == Qt.Orientation.Horizontal:
            self.collapse_btn.setText("◀")
        else:
            self.collapse_btn.setText("▲")
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the handle."""
        painter = QPainter(self)
        
        if self._hover:
            painter.fillRect(self.rect(), QColor(200, 200, 200))
        else:
            painter.fillRect(self.rect(), QColor(230, 230, 230))
        
        # Draw dots
        painter.setPen(QColor(150, 150, 150))
        center = self.rect().center()
        
        if self._orientation == Qt.Orientation.Horizontal:
            for i in range(-2, 3):
                painter.drawPoint(center.x(), center.y() + i * 8)
        else:
            for i in range(-2, 3):
                painter.drawPoint(center.x() + i * 8, center.y())
    
    def enterEvent(self, event: QEnterEvent) -> None:
        """Handle mouse enter."""
        self._hover = True
        self.collapse_btn.setVisible(True)
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave."""
        self._hover = False
        self.collapse_btn.setVisible(False)
        self.update()
        super().leaveEvent(event)


class PanelContainer(QWidget):
    """
    Container that manages multiple collapsible panels.
    
    Provides consistent layout and state management.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._panels: Dict[str, CollapsiblePanel] = {}
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the container UI."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        
        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self._scroll_widget = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setContentsMargins(4, 4, 4, 4)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.addStretch()
        
        self._scroll.setWidget(self._scroll_widget)
        self._layout.addWidget(self._scroll)
    
    def add_panel(
        self,
        name: str,
        title: str,
        widget: Optional[QWidget] = None,
        expanded: bool = True
    ) -> CollapsiblePanel:
        """Add a panel to the container."""
        panel = CollapsiblePanel(title, animated=True, initially_expanded=expanded)
        
        if widget:
            panel.set_content_widget(widget)
        
        self._panels[name] = panel
        
        # Insert before stretch
        index = self._scroll_layout.count() - 1
        self._scroll_layout.insertWidget(index, panel)
        
        return panel
    
    def get_panel(self, name: str) -> Optional[CollapsiblePanel]:
        """Get panel by name."""
        return self._panels.get(name)
    
    def remove_panel(self, name: str) -> None:
        """Remove a panel."""
        if name in self._panels:
            panel = self._panels.pop(name)
            self._scroll_layout.removeWidget(panel)
            panel.deleteLater()
    
    def expand_all(self) -> None:
        """Expand all panels."""
        for panel in self._panels.values():
            panel.set_expanded(True)
    
    def collapse_all(self) -> None:
        """Collapse all panels."""
        for panel in self._panels.values():
            panel.set_expanded(False)
    
    def save_state(self) -> Dict[str, bool]:
        """Save panel states."""
        return {name: panel.is_expanded() for name, panel in self._panels.items()}
    
    def restore_state(self, state: Dict[str, bool]) -> None:
        """Restore panel states."""
        for name, expanded in state.items():
            if name in self._panels:
                self._panels[name].set_expanded(expanded)


class ToolPanel(CollapsiblePanel):
    """
    Specialized panel for tool options.
    
    Provides standardized layout for tool settings.
    """
    
    def __init__(
        self,
        title: str = "Options",
        parent: Optional[QWidget] = None
    ):
        super().__init__(title, parent)
        
        self._form_layout = None
    
    def add_option(
        self,
        label: str,
        widget: QWidget,
        tooltip: str = ""
    ) -> None:
        """Add an option row with label."""
        if self._form_layout is None:
            self._form_layout = QGridLayout()
            self._form_layout.setColumnStretch(1, 1)
            self.add_layout(self._form_layout)
        
        row = self._form_layout.rowCount()
        
        label_widget = QLabel(label)
        if tooltip:
            label_widget.setToolTip(tooltip)
            widget.setToolTip(tooltip)
        
        self._form_layout.addWidget(label_widget, row, 0)
        self._form_layout.addWidget(widget, row, 1)
    
    def add_checkbox_option(
        self,
        label: str,
        checked: bool = False,
        tooltip: str = "",
        callback: Optional[Callable[[bool], None]] = None
    ) -> QCheckBox:
        """Add a checkbox option."""
        checkbox = QCheckBox(label)
        checkbox.setChecked(checked)
        
        if tooltip:
            checkbox.setToolTip(tooltip)
        
        if callback:
            checkbox.toggled.connect(callback)
        
        self.add_widget(checkbox)
        return checkbox
    
    def add_separator(self) -> None:
        """Add a horizontal separator."""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.add_widget(separator)