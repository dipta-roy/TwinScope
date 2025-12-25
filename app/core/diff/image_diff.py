"""
Image file diff engine.

Provides visual comparison of images with:
- Pixel-by-pixel comparison
- Difference highlighting
- Multiple visualization modes
- Support for various image formats
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable, Tuple

# Image processing - PIL/Pillow
try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from app.core.models import ImageDiffResult, ImageDiffRegion


class ImageDiffMode(Enum):
    """Image comparison visualization modes."""
    SIDE_BY_SIDE = auto()    # Show images side by side
    OVERLAY = auto()         # Overlay with transparency
    DIFFERENCE = auto()       # Show pixel differences
    HIGHLIGHT = auto()        # Highlight different regions
    SPLIT = auto()           # Split screen slider
    ONION_SKIN = auto()      # Fade between images
    FLICKER = auto()         # Alternate between images


class HighlightStyle(Enum):
    """Style for highlighting differences."""
    BOX = auto()         # Draw boxes around different regions
    FILL = auto()        # Fill different regions with color
    OUTLINE = auto()     # Outline different regions
    HEATMAP = auto()     # Heatmap based on difference intensity
    CIRCLE = auto()      # Draw circles around different regions


@dataclass
class ImageCompareOptions:
    """Options for image comparison."""
    mode: ImageDiffMode = ImageDiffMode.HIGHLIGHT
    highlight_style: HighlightStyle = HighlightStyle.FILL
    highlight_color: Tuple[int, int, int, int] = (255, 0, 0, 128)  # RGBA
    tolerance: int = 0  # Color tolerance (0-255)
    ignore_alpha: bool = False
    ignore_size_difference: bool = False
    resize_to_match: bool = True
    antialias: bool = True
    min_region_size: int = 1  # Minimum pixels for a diff region
    difference_amplification: float = 20.0  # Amplify differences for visibility


@dataclass
class ImageInfo:
    """Information about an image."""
    width: int
    height: int
    mode: str  # PIL mode (RGB, RGBA, L, etc.)
    format: Optional[str]
    file_size: int
    has_alpha: bool
    
    @property
    def dimensions(self) -> Tuple[int, int]:
        return (self.width, self.height)


@dataclass
class PixelDifference:
    """Information about a pixel difference."""
    x: int
    y: int
    left_color: Tuple[int, ...]
    right_color: Tuple[int, ...]
    difference: float  # 0.0 to 1.0


class ImageDiffEngine:
    """
    Engine for comparing image files.
    
    Requires PIL/Pillow for image processing.
    """
    
    def __init__(self, options: Optional[ImageCompareOptions] = None):
        if not PIL_AVAILABLE:
            raise ImportError(
                "PIL/Pillow is required for image comparison. "
                "Install with: pip install Pillow"
            )
        self.options = options or ImageCompareOptions()
    
    
    def _compare_images_visual(
        self,
        left_img: Image.Image,
        right_img: Image.Image,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Tuple[Image.Image, float, list[ImageDiffRegion]]:
        """
        Perform the actual visual comparison logic.
        
        Args:
            left_img: Normalized left image
            right_img: Normalized right image
            progress_callback: Progress callback
            
        Returns:
            Tuple of (difference_image, similarity, regions)
        """
        width = left_img.width
        height = left_img.height
        
        # Calculate difference in chunks to support progress reporting
        # and stay responsive with large images
        diff_img = Image.new('RGB', (width, height))
        chunk_height = 128
        
        for y in range(0, height, chunk_height):
            y_end = min(y + chunk_height, height)
            
            left_crop = left_img.crop((0, y, width, y_end))
            right_crop = right_img.crop((0, y, width, y_end))
            
            # Compute difference for this strip
            if self.options.ignore_alpha and left_img.mode == 'RGBA':
                strip_diff = ImageChops.difference(left_crop.convert('RGB'), right_crop.convert('RGB'))
            else:
                strip_diff = ImageChops.difference(left_crop, right_crop)
                
            # Apply tolerance
            if self.options.tolerance > 0:
                strip_diff = strip_diff.point(lambda p: 0 if p <= self.options.tolerance else p)
                
            diff_img.paste(strip_diff, (0, y))
            
            if progress_callback:
                progress_callback(y_end, height)

        # Calculate similarity using histogram
        similarity = self._calculate_similarity_from_diff(diff_img)
        
        # Find difference regions
        regions = self._find_diff_regions(diff_img)
        
        # Amplify differences for visibility in the diff image if requested
        if self.options.difference_amplification != 1.0:
            enhancer = ImageEnhance.Contrast(diff_img)
            diff_img = enhancer.enhance(self.options.difference_amplification)
            
        return diff_img, similarity, regions

    def _normalize_image(self, img: Image.Image, size: Tuple[int, int]) -> Image.Image:
        """Normalize image mode and size for comparison."""
        target_mode = img.mode
        if img.mode not in ('RGB', 'RGBA', 'L'):
            target_mode = 'RGBA' if 'A' in img.mode else 'RGB'
            img = img.convert(target_mode)
            
        if img.size == size:
            return img
            
        # If sizes differ, we pad instead of stretching to preserve aspect ratio
        new_img = Image.new(target_mode, size, (0, 0, 0, 0) if target_mode == 'RGBA' else 0)
        # Center the image
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        new_img.paste(img, (x, y))
        return new_img

    def _calculate_similarity_from_diff(self, diff_img: Image.Image) -> float:
        """Calculate similarity ratio from a difference image using histogram."""
        hist = diff_img.histogram()
        total_pixels = diff_img.width * diff_img.height
        
        if diff_img.mode in ('RGB', 'RGBA'):
            # In RGB(A), histogram is a list of 256 * channels values
            channels = 3 # We focus on RGB for similarity
            hist_r = hist[0:256]
            hist_g = hist[256:512]
            hist_b = hist[512:768]
            
            diff_sum = 0
            for i in range(256):
                diff_sum += (hist_r[i] + hist_g[i] + hist_b[i]) * i
                
            max_diff = 255 * channels * total_pixels
        else:
            diff_sum = sum(hist[i] * i for i in range(256))
            max_diff = 255 * total_pixels
            
        if max_diff == 0:
            return 1.0
        return 1.0 - (diff_sum / max_diff)

    def compare(
        self,
        left_path: Path | str,
        right_path: Path | str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> ImageDiffResult:
        """
        Compare two image files.
        
        Args:
            left_path: Path to left image
            right_path: Path to right image
            progress_callback: Progress callback (current, total)
            
        Returns:
            ImageDiffResult with comparison details
        """
        left_path = Path(left_path)
        right_path = Path(right_path)
        
        # Load images
        left_exists = left_path.exists() and left_path.is_file()
        right_exists = right_path.exists() and right_path.is_file()
        
        if left_exists:
            left_img = Image.open(left_path)
        else:
            # Create a small blank image if it doesn't exist
            left_img = Image.new('RGB', (1, 1), (0, 0, 0))
            
        if right_exists:
            right_img = Image.open(right_path)
        else:
            # Create a small blank image if it doesn't exist
            right_img = Image.new('RGB', (1, 1), (0, 0, 0))
            
        # Get image info
        left_info = self._get_image_info(left_img, left_path)
        right_info = self._get_image_info(right_img, right_path)
        
        # Handle size differences
        size_match = left_info.dimensions == right_info.dimensions
        
        if not size_match:
            if not self.options.ignore_size_difference:
                if self.options.resize_to_match:
                    # Resize to larger dimensions
                    target_size = (
                        max(left_info.width, right_info.width),
                        max(left_info.height, right_info.height)
                    )
                    resample = Image.LANCZOS if self.options.antialias else Image.NEAREST
                    
                    if left_info.dimensions != target_size:
                        left_img = left_img.resize(target_size, resample)
                    if right_info.dimensions != target_size:
                        right_img = right_img.resize(target_size, resample)
        
        # Normalize modes
        if left_img.mode != right_img.mode:
            # Convert to common mode
            if 'A' in left_img.mode or 'A' in right_img.mode:
                target_mode = 'RGBA'
            else:
                target_mode = 'RGB'
            
            left_img = left_img.convert(target_mode)
            right_img = right_img.convert(target_mode)

        # Ensure same size for pixel-by-pixel comparison and visualization
        width = max(left_img.width, right_img.width)
        height = max(left_img.height, right_img.height)
        
        left_img = self._normalize_image(left_img, (width, height))
        right_img = self._normalize_image(right_img, (width, height))
        
        # Perform comparison using the specialized visual logic
        difference_img, similarity, regions = self._compare_images_visual(
            left_img, right_img, progress_callback
        )
        
        # Generate visualization
        visual_img = self._generate_visualization(
            left_img, right_img, difference_img, regions
        )
        
        return ImageDiffResult(
            left_path=str(left_path) if left_exists else "",
            right_path=str(right_path) if right_exists else "",
            left_info=left_info,
            right_info=right_info,
            is_identical=similarity >= 1.0,
            similarity=similarity,
            left_image=left_img,
            right_image=right_img,
            difference_image=difference_img,
            visualization_image=visual_img,
            regions=regions,
            size_match=size_match
        )
    
    def compare_bytes(
        self,
        left_data: bytes,
        right_data: bytes
    ) -> ImageDiffResult:
        """Compare two images from byte data."""
        left_img = Image.open(io.BytesIO(left_data))
        right_img = Image.open(io.BytesIO(right_data))
        
        left_info = ImageInfo(
            width=left_img.width,
            height=left_img.height,
            mode=left_img.mode,
            format=left_img.format,
            file_size=len(left_data),
            has_alpha='A' in left_img.mode
        )
        
        right_info = ImageInfo(
            width=right_img.width,
            height=right_img.height,
            mode=right_img.mode,
            format=right_img.format,
            file_size=len(right_data),
            has_alpha='A' in right_img.mode
        )
        
        # Handle size/mode differences
        if left_img.size != right_img.size and self.options.resize_to_match:
            target_size = (
                max(left_img.width, right_img.width),
                max(left_img.height, right_img.height)
            )
            left_img = left_img.resize(target_size, Image.LANCZOS)
            right_img = right_img.resize(target_size, Image.LANCZOS)
        
        if left_img.mode != right_img.mode:
            target_mode = 'RGBA' if 'A' in left_img.mode or 'A' in right_img.mode else 'RGB'
            left_img = left_img.convert(target_mode)
            right_img = right_img.convert(target_mode)
        
        # Perform comparison using the specialized visual logic
        difference_img, similarity, regions = self._compare_images_visual(
            left_img, right_img, None
        )
        
        visual_img = self._generate_visualization(
            left_img, right_img, difference_img, regions
        )
        
        return ImageDiffResult(
            left_path="<bytes>",
            right_path="<bytes>",
            left_info=left_info,
            right_info=right_info,
            is_identical=similarity >= 1.0,
            similarity=similarity,
            left_image=left_img,
            right_image=right_img,
            difference_image=difference_img,
            visualization_image=visual_img,
            regions=regions,
            size_match=left_info.dimensions == right_info.dimensions
        )
    
    def create_overlay(
        self,
        left_img: Image.Image,
        right_img: Image.Image,
        opacity: float = 0.5
    ) -> Image.Image:
        """Create an overlay blend of two images."""
        if left_img.size != right_img.size:
            right_img = right_img.resize(left_img.size, Image.LANCZOS)
        
        # Convert to RGBA
        left_rgba = left_img.convert('RGBA')
        right_rgba = right_img.convert('RGBA')
        
        # Blend
        return Image.blend(left_rgba, right_rgba, opacity)
    
    def create_side_by_side(
        self,
        left_img: Image.Image,
        right_img: Image.Image,
        gap: int = 10,
        background: Tuple[int, int, int] = (128, 128, 128)
    ) -> Image.Image:
        """Create a side-by-side comparison image."""
        # Normalize heights
        max_height = max(left_img.height, right_img.height)
        
        if left_img.height != max_height:
            ratio = max_height / left_img.height
            left_img = left_img.resize(
                (int(left_img.width * ratio), max_height),
                Image.LANCZOS
            )
        
        if right_img.height != max_height:
            ratio = max_height / right_img.height
            right_img = right_img.resize(
                (int(right_img.width * ratio), max_height),
                Image.LANCZOS
            )
        
        # Create combined image
        total_width = left_img.width + gap + right_img.width
        result = Image.new('RGB', (total_width, max_height), background)
        
        result.paste(left_img, (0, 0))
        result.paste(right_img, (left_img.width + gap, 0))
        
        return result
    
    def create_split_view(
        self,
        left_img: Image.Image,
        right_img: Image.Image,
        split_position: float = 0.5,
        vertical: bool = True
    ) -> Image.Image:
        """Create a split view (slider-style) comparison."""
        # Ensure same size
        if left_img.size != right_img.size:
            target_size = (
                max(left_img.width, right_img.width),
                max(left_img.height, right_img.height)
            )
            left_img = left_img.resize(target_size, Image.LANCZOS)
            right_img = right_img.resize(target_size, Image.LANCZOS)
        
        result = left_img.copy()
        
        if vertical:
            split_x = int(left_img.width * split_position)
            right_crop = right_img.crop((split_x, 0, right_img.width, right_img.height))
            result.paste(right_crop, (split_x, 0))
        else:
            split_y = int(left_img.height * split_position)
            right_crop = right_img.crop((0, split_y, right_img.width, right_img.height))
            result.paste(right_crop, (0, split_y))
        
        return result
    
    def _get_image_info(self, img: Image.Image, path: Path) -> ImageInfo:
        """Extract information from an image."""
        return ImageInfo(
            width=img.width,
            height=img.height,
            mode=img.mode,
            format=img.format,
            file_size=path.stat().st_size if path.exists() else 0,
            has_alpha='A' in img.mode
        )
    
    def _compute_difference(
        self,
        left_img: Image.Image,
        right_img: Image.Image,
        progress_callback: Optional[Callable[[int, int], None]]
    ) -> Tuple[Image.Image, float, list[ImageDiffRegion]]:
        """Deprecated. Use _compare_images_visual instead."""
        return self._compare_images_visual(left_img, right_img, progress_callback)
    
    def _find_diff_regions(self, diff_img: Image.Image) -> list[ImageDiffRegion]:
        """Find connected regions of differences."""
        regions = []
        
        # Convert to grayscale and threshold immediately (any diff > 0 is a change)
        if diff_img.mode != 'L':
            gray = diff_img.convert('L')
        else:
            gray = diff_img
        
        threshold = gray.point(lambda p: 255 if p > 0 else 0)
        w, h = threshold.size
        
        # Determine scale for performance
        max_dim = max(w, h)
        if max_dim <= 512:
            scale = 1
            small = threshold
        else:
            scale = max_dim // 512
            # Use MaxFilter to ensure tiny differences aren't lost when downscaling
            dilated = threshold.filter(ImageFilter.MaxFilter(scale * 2 - 1))
            small = dilated.resize((w // scale, h // scale), Image.NEAREST)
            
        small_w, small_h = small.size
        pixels = small.load()
        
        visited = set()
        
        for y in range(small_h):
            for x in range(small_w):
                if pixels[x, y] > 0 and (x, y) not in visited:
                    # Start of a new region - flood fill
                    stack = [(x, y)]
                    visited.add((x, y))
                    
                    min_x, min_y = x, y
                    max_x, max_y = x, y
                    diff_blocks = 0
                    
                    while stack:
                        cx, cy = stack.pop()
                        diff_blocks += 1
                        
                        min_x = min(min_x, cx)
                        min_y = min(min_y, cy)
                        max_x = max(max_x, cx)
                        max_y = max(max_y, cy)
                        
                        # Check neighbors (4-connectivity)
                        for nx, ny in [(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)]:
                            if 0 <= nx < small_w and 0 <= ny < small_h:
                                if pixels[nx, ny] > 0 and (nx, ny) not in visited:
                                    visited.add((nx, ny))
                                    stack.append((nx, ny))
                    
                    # Convert back to original coordinates
                    # Multiplying by scale maps the top-left of the small grid cell
                    orig_x = min_x * scale
                    orig_y = min_y * scale
                    
                    # We add scale to the width/height to cover the full range of modified small pixels
                    orig_w = (max_x - min_x + 1) * scale
                    orig_h = (max_y - min_y + 1) * scale
                    
                    # Calculate actual bounds in threshold image
                    x1, y1 = max(0, orig_x), max(0, orig_y)
                    x2, y2 = min(w, x1 + orig_w), min(h, y1 + orig_h)
                    
                    # Refined crop to count actual pixels in the region
                    region_crop = threshold.crop((x1, y1, x2, y2))
                    region_data = list(region_crop.getdata())
                    true_diff_count = sum(1 for p in region_data if p > 0)
                    
                    if true_diff_count >= self.options.min_region_size:
                        regions.append(ImageDiffRegion(
                            x=x1,
                            y=y1,
                            width=x2 - x1,
                            height=y2 - y1,
                            pixel_count=true_diff_count,
                            difference_ratio=true_diff_count / (w * h) if w * h > 0 else 0
                        ))
        
        return regions
    
    def _generate_visualization(
        self,
        left_img: Image.Image,
        right_img: Image.Image,
        diff_img: Image.Image,
        regions: list[ImageDiffRegion]
    ) -> Image.Image:
        """Generate visualization based on selected mode."""
        mode = self.options.mode
        
        if mode == ImageDiffMode.SIDE_BY_SIDE:
            return self.create_side_by_side(left_img, right_img)
        
        elif mode == ImageDiffMode.OVERLAY:
            return self.create_overlay(left_img, right_img, 0.5)
        
        elif mode == ImageDiffMode.DIFFERENCE:
            return diff_img
        
        elif mode == ImageDiffMode.HIGHLIGHT:
            return self._create_highlight_image(left_img, right_img, regions)
        
        elif mode == ImageDiffMode.SPLIT:
            return self.create_split_view(left_img, right_img, 0.5)
        
        elif mode == ImageDiffMode.ONION_SKIN:
            return self.create_overlay(left_img, right_img, 0.5)
        
        else:
            return diff_img
    
    def _create_highlight_image(
        self,
        left_img: Image.Image,
        right_img: Image.Image,
        regions: list[ImageDiffRegion]
    ) -> Image.Image:
        """Create image with difference regions highlighted."""
        # Convert to RGBA for transparency support
        result = left_img.convert('RGBA')
        
        # Create highlight overlay
        overlay = Image.new('RGBA', result.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        color = self.options.highlight_color
        style = self.options.highlight_style
        
        # For Spotlight mode, dim the background to make highlights pop
        if style == HighlightStyle.CIRCLE:
            enhancer = ImageEnhance.Brightness(result)
            result = enhancer.enhance(0.4)  # 60% darker
        
        for region in regions:
            bbox = (region.x, region.y, 
                   region.x + region.width, region.y + region.height)
            
            if style == HighlightStyle.FILL:
                draw.rectangle(bbox, fill=color)
            elif style == HighlightStyle.BOX:
                draw.rectangle(bbox, outline=color[:3], width=2)
            elif style == HighlightStyle.OUTLINE:
                draw.rectangle(bbox, outline=color[:3], width=1)
            elif style == HighlightStyle.HEATMAP:
                # Intensity based on difference ratio
                intensity = int(region.difference_ratio * 255)
                heat_color = (intensity, 0, 255 - intensity, 128)
                draw.rectangle(bbox, fill=heat_color)
            elif style == HighlightStyle.CIRCLE:
                # Draw a circle around the region
                center_x = region.x + region.width // 2
                center_y = region.y + region.height // 2
                # Calculate radius to cover the entire rectangle plus some padding
                radius = int(((region.width / 2)**2 + (region.height / 2)**2)**0.5) + 5
                
                circle_bbox = (center_x - radius, center_y - radius,
                               center_x + radius, center_y + radius)
                
                # Draw circle outline
                draw.ellipse(circle_bbox, outline=color[:3], width=3)
                
                # Paste modified pixels from right_img inside the circle
                # Create a circular mask for this region
                mask = Image.new('L', result.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse(circle_bbox, fill=255)
                
                # Combine right_img content into the result
                result.paste(right_img.convert('RGBA'), (0, 0), mask)
        
        # Composite the highlights on top
        result = Image.alpha_composite(result, overlay)
        
        return result
    
    def get_pixel_info(
        self,
        img: Image.Image,
        x: int,
        y: int
    ) -> dict:
        """Get detailed information about a pixel."""
        if x < 0 or x >= img.width or y < 0 or y >= img.height:
            return {'error': 'Coordinates out of bounds'}
        
        pixel = img.getpixel((x, y))
        
        info = {
            'x': x,
            'y': y,
            'raw': pixel
        }
        
        if img.mode == 'RGB':
            info['red'] = pixel[0]
            info['green'] = pixel[1]
            info['blue'] = pixel[2]
            info['hex'] = f'#{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}'
        elif img.mode == 'RGBA':
            info['red'] = pixel[0]
            info['green'] = pixel[1]
            info['blue'] = pixel[2]
            info['alpha'] = pixel[3]
            info['hex'] = f'#{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}{pixel[3]:02x}'
        elif img.mode == 'L':
            info['gray'] = pixel
            info['hex'] = f'#{pixel:02x}{pixel:02x}{pixel:02x}'
        
        return info


def check_image_support() -> dict:
    """Check which image formats are supported."""
    if not PIL_AVAILABLE:
        return {'available': False, 'formats': []}
    
    # Get supported formats
    formats = []
    
    # Common formats to check
    test_formats = ['PNG', 'JPEG', 'GIF', 'BMP', 'TIFF', 'WEBP', 'ICO']
    
    for fmt in test_formats:
        try:
            if fmt in Image.SAVE or fmt in Image.OPEN:
                formats.append(fmt.lower())
        except Exception:
            pass
    
    return {
        'available': True,
        'formats': formats,
        'pillow_version': Image.__version__ if hasattr(Image, '__version__') else 'unknown'
    }