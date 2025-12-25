"""
Widget for displaying image comparison results.
Supports multiple visualization modes: side-by-side, overlay, split view, and difference.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QSlider, QComboBox, QScrollArea, QFrame, 
    QPushButton, QButtonGroup, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QBrush, QPen

import io
from PIL import Image

from app.core.models import ImageDiffResult

class ImageCompareWidget(QWidget):
    """
    Advanced widget for comparing two images visually.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._diff_result: ImageDiffResult | None = None
        self._mode = "Side-by-Side"
        self._overlay_opacity = 0.5
        self._split_pos = 0.5
        self._show_highlights = True
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar for image controls
        toolbar = QFrame()
        toolbar.setObjectName("ImageToolbar")
        toolbar.setStyleSheet("""
            #ImageToolbar {
                background-color: #f6f8fa;
                border-bottom: 1px solid #e1e4e8;
                padding: 5px;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        
        # Mode selector
        toolbar_layout.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Side-by-Side", "Overlay", "Split View", "Difference", "Spotlight"])
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        toolbar_layout.addWidget(self._mode_combo)
        
        toolbar_layout.addSpacing(20)
        
        # Opacity/Split slider
        self._control_label = QLabel("Opacity:")
        toolbar_layout.addWidget(self._control_label)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(50)
        self._slider.setFixedWidth(150)
        self._slider.valueChanged.connect(self._on_slider_changed)
        toolbar_layout.addWidget(self._slider)
        
        toolbar_layout.addStretch()
        
        # Stats label
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("font-weight: bold; color: #586069;")
        toolbar_layout.addWidget(self._stats_label)
        
        layout.addWidget(toolbar)
        
        # Main display area (Scrollable)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll_area.setStyleSheet("background-color: #f1f3f5; border: none;")
        
        self._display = ImageDisplay(self)
        self._scroll_area.setWidget(self._display)
        
        layout.addWidget(self._scroll_area, 1)
        
    def set_diff_result(self, result: ImageDiffResult):
        self._diff_result = result
        
        # Update stats
        similarity_pct = result.similarity * 100
        left_info = f"{result.left_info.width}x{result.left_info.height}" if result.left_path else "Missing"
        right_info = f"{result.right_info.width}x{result.right_info.height}" if result.right_path else "Missing"
        
        self._stats_label.setText(f"Similarity: {similarity_pct:.2f}% | L: {left_info} | R: {right_info}")
        
        # Convert PIL images to QPixmap
        self._left_pixmap = self._pil_to_pixmap(result.left_image)
        self._right_pixmap = self._pil_to_pixmap(result.right_image)
        self._diff_pixmap = self._pil_to_pixmap(result.difference_image)
        self._vis_pixmap = self._pil_to_pixmap(result.visualization_image)
        
        # Generate spotlight version as well
        self._spotlight_pixmap = self._generate_spotlight_pixmap(result)
        
        self._update_display()
        
    def _pil_to_pixmap(self, pil_img):
        if pil_img is None:
            return QPixmap()
        
        # Convert to PNG in memory then to QPixmap
        # This is robust across various PIL modes
        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        qimg = QImage.fromData(buffer.getvalue())
        return QPixmap.fromImage(qimg)
        
    def _on_mode_changed(self, mode):
        self._mode = mode
        if mode == "Overlay":
            self._control_label.setText("Opacity:")
            self._slider.show()
            self._control_label.show()
        elif mode == "Split View":
            self._control_label.setText("Position:")
            self._slider.show()
            self._control_label.show()
        else:
            self._slider.hide()
            self._control_label.hide()
            
        self._update_display()

    def _generate_spotlight_pixmap(self, result: ImageDiffResult):
        """Generate a pixmap using the new CIRCLE highlight style."""
        if not result:
            return QPixmap()
            
        from app.core.diff.image_diff import ImageDiffEngine, ImageCompareOptions, ImageDiffMode, HighlightStyle
        
        options = ImageCompareOptions(
            mode=ImageDiffMode.HIGHLIGHT,
            highlight_style=HighlightStyle.CIRCLE,
            highlight_color=(255, 0, 0, 128)
        )
        engine = ImageDiffEngine(options)
        
        # We need both images. PIL images are already in result.
        vis_img = engine._create_highlight_image(
            result.left_image, 
            result.right_image, 
            result.regions
        )
        
        return self._pil_to_pixmap(vis_img)
        
    def _on_slider_changed(self, value):
        if self._mode == "Overlay":
            self._overlay_opacity = value / 100.0
        elif self._mode == "Split View":
            self._split_pos = value / 100.0
        self._update_display()
        
    def _update_display(self):
        if not self._diff_result:
            return
            
        self._display.set_content(
            self._mode,
            self._left_pixmap,
            self._right_pixmap,
            self._diff_pixmap,
            self._spotlight_pixmap if self._mode == "Spotlight" else self._vis_pixmap,
            self._overlay_opacity,
            self._split_pos
        )

class ImageDisplay(QWidget):
    """Internal widget for custom image drawing."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "Side-by-Side"
        self._left_pix = QPixmap()
        self._right_pix = QPixmap()
        self._diff_pix = QPixmap()
        self._vis_pix = QPixmap()
        self._spotlight_pix = QPixmap()
        self._opacity = 0.5
        self._split_pos = 0.5
        
    def set_content(self, mode, left, right, diff, vis, opacity, split):
        self._mode = mode
        self._left_pix = left
        self._right_pix = right
        self._diff_pix = diff
        self._vis_pix = vis
        self._opacity = opacity
        self._split_pos = split
        
        # Adjust size to fit images
        if mode == "Side-by-Side":
            w = left.width() + 20 + right.width()
            h = max(left.height(), right.height())
        else:
            w = max(left.width(), right.width())
            h = max(left.height(), right.height())
            
        self.setFixedSize(w + 40, h + 40)
        self.update()
        
    def paintEvent(self, event):
        if self._left_pix.isNull():
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Center point
        cx = self.width() // 2
        cy = self.height() // 2
        
        if self._mode == "Side-by-Side":
            # Side-by-side with a gap
            lx = cx - (self._left_pix.width() + self._right_pix.width() + 20) // 2
            ly = cy - self._left_pix.height() // 2
            painter.drawPixmap(lx, ly, self._left_pix)
            
            rx = lx + self._left_pix.width() + 20
            ry = cy - self._right_pix.height() // 2
            painter.drawPixmap(rx, ry, self._right_pix)
            
        elif self._mode == "Overlay":
            # Overlay with transparency
            x = cx - self._left_pix.width() // 2
            y = cy - self._left_pix.height() // 2
            
            painter.drawPixmap(x, y, self._left_pix)
            painter.setOpacity(self._opacity)
            painter.drawPixmap(x, y, self._right_pix)
            
        elif self._mode == "Split View":
            # Split view slider
            x = cx - self._left_pix.width() // 2
            y = cy - self._left_pix.height() // 2
            
            painter.drawPixmap(x, y, self._left_pix)
            
            split_x = int(self._left_pix.width() * self._split_pos)
            painter.drawPixmap(x + split_x, y, self._right_pix, split_x, 0, -1, -1)
            
            # Draw slider line
            painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
            painter.drawLine(x + split_x, y, x + split_x, y + self._left_pix.height())
            
        elif self._mode == "Difference":
            # Show the absolute difference image
            x = cx - self._diff_pix.width() // 2
            y = cy - self._diff_pix.height() // 2
            painter.drawPixmap(x, y, self._diff_pix)
            
        elif self._mode == "Spotlight":
            # Show the circular spotlight visualization
            x = cx - self._vis_pix.width() // 2
            y = cy - self._vis_pix.height() // 2
            painter.drawPixmap(x, y, self._vis_pix)
