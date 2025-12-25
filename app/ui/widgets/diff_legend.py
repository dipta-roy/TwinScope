from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtGui import QPixmap, QColor
from typing import Optional

from app.ui.widgets.diff_text_edit import DiffColors

class DiffLegend(QWidget):
    def __init__(self, parent=None, colors: Optional[DiffColors] = None):
        super().__init__(parent)
        
        self._colors = colors or DiffColors()
        self._color_boxes = []  # Store references to color boxes
        
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(15, 5, 15, 5)
        self._layout.setSpacing(15)
        
        # Similarity label (Match %)
        self._similarity_label = QLabel("")
        self._similarity_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                color: #2da44e;
                background-color: #dafbe1;
                border: 1px solid #2da44e;
                border-radius: 4px;
                padding: 2px 8px;
                margin-right: 15px;
            }
        """)
        self._similarity_label.hide() # Hidden until set
        self._layout.addWidget(self._similarity_label)
        
        # Create initial legend items
        self._create_legend_items()
    
    def _create_legend_items(self):
        """Create or recreate legend items with current colors."""
        # Clear existing items except the similarity label
        # We process in reverse to safely remove items
        for i in reversed(range(self._layout.count())):
            item = self._layout.itemAt(i)
            if item.widget() == self._similarity_label:
                continue
                
            # Remove item from layout
            self._layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()
        
        self._color_boxes.clear()
        
        # Add legend items with current colors
        self._add_legend_item(self._colors.added_bg, "Added Line")
        self._add_legend_item(self._colors.removed_bg, "Removed Line")
        self._add_legend_item(self._colors.modified_bg, "Modified Line")
        self._add_legend_item(self._colors.intraline_added, "Added Text")
        self._add_legend_item(self._colors.intraline_removed, "Removed Text")
        self._add_legend_item(self._colors.intraline_changed, "Changed Text")
        self._add_legend_item(self._colors.search_match_bg, "Search Match")
        self._add_legend_item(self._colors.search_current_match_bg, "Current Match")
        
        self._layout.addStretch()
    
    def _add_legend_item(self, color, text):
        """Add a single legend item."""
        color_box = QLabel()
        pixmap = QPixmap(16, 16)
        pixmap.fill(color)
        color_box.setPixmap(pixmap)
        self._layout.addWidget(color_box)
        self._color_boxes.append(color_box)
        
        label = QLabel(text)
        self._layout.addWidget(label)
    
    def update_colors(self, colors: DiffColors):
        """Update the legend with new colors."""
        self._colors = colors
        self._create_legend_items()
        
    def set_similarity(self, ratio: float):
        """Set and show the similarity percentage."""
        pct = ratio * 100
        self._similarity_label.setText(f"Match: {pct:.2f}%")
        
        # Change color based on similarity
        if pct == 100:
            color = "#2da44e" # Green
            bg = "#dafbe1"
        elif pct > 80:
            color = "#9a6700" # Yellow/Orange
            bg = "#fff8c5"
        else:
            color = "#cf222e" # Red
            bg = "#ffebe9"
            
        self._similarity_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                color: {color};
                background-color: {bg};
                border: 1px solid {color};
                border-radius: 4px;
                padding: 2px 8px;
                margin-right: 15px;
            }}
        """)
        self._similarity_label.show()
        
    def clear_similarity(self):
        """Hide the similarity percentage."""
        self._similarity_label.hide()
    
    def update(self):
        """Override update to refresh colors from current DiffColors."""
        self._create_legend_items()
        super().update()
