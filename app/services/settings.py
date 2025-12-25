"""
Application settings management.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
from enum import Enum, auto


class Theme(Enum):
    """UI theme options."""
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"
    CUSTOM = "custom"

    @classmethod
    def from_string(cls, value: str) -> 'Theme':
        """Create from string value."""
        try:
            # Try to match by value
            for theme in cls:
                if theme.value == value.lower():
                    return theme
            # Try to match by name
            return cls[value.upper()]
        except (KeyError, AttributeError):
            return cls.SYSTEM


class DiffStyle(Enum):
    """Diff display style."""
    SIDE_BY_SIDE = auto()
    UNIFIED = auto()
    INLINE = auto()


@dataclass
class ComparisonSettings:
    """Settings for file comparison."""
    ignore_whitespace: bool = False
    ignore_case: bool = False
    ignore_blank_lines: bool = False
    ignore_line_endings: bool = True
    context_lines: int = 3
    diff_style: DiffStyle = DiffStyle.SIDE_BY_SIDE
    show_line_numbers: bool = True
    word_wrap: bool = False
    tab_size: int = 4
    
    # Folder comparison
    recursive: bool = True
    follow_symlinks: bool = False
    compare_file_contents: bool = True
    quick_compare_by_size: bool = True
    
    # File filters
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=lambda: [
        '*.pyc', '__pycache__', '.git', '.svn', '.hg',
        'node_modules', '.DS_Store', 'Thumbs.db'
    ])


@dataclass
class UISettings:
    """User interface settings."""
    theme: Theme = Theme.LIGHT
    font_family: str = "Consolas"
    font_size: int = 10
    window_width: int = 1200
    window_height: int = 800
    window_maximized: bool = False
    splitter_position: int = 500
    show_toolbar: bool = True
    show_statusbar: bool = True
    recent_files_limit: int = 5
    recent_history_limit: int = 10


@dataclass 
class ColorSettings:
    """Color settings for diff highlighting."""
    added_background: str = "#e6ffe6"
    removed_background: str = "#ffe6e6"
    modified_background: str = "#fffde6"
    identical_background: str = "#ffffff"
    conflict_background: str = "#fff0f0"
    
    added_text: str = "#006600"
    removed_text: str = "#660000"
    modified_text: str = "#666600"
    
    line_number_color: str = "#999999"
    line_number_background: str = "#f5f5f5"
    
    # Folder comparison colors
    folder_identical_color: str = "#e0e0e0" # Light gray
    folder_modified_color: str = "#fffacd"  # Lemon chiffon
    folder_left_only_color: str = "#e6f7ff" # Light blue
    folder_right_only_color: str = "#ffe6e6" # Light red
    folder_conflict_color: str = "#ffcccc"  # Light red for conflicts
    
    # Dark theme overrides
    dark_added_background: str = "#1e3a1e"
    dark_removed_background: str = "#3a1e1e"
    dark_modified_background: str = "#3a3a1e"


@dataclass
class MergeSettings:
    """Settings for merge operations."""
    auto_resolve_identical: bool = True
    auto_resolve_whitespace: bool = True
    show_base_in_conflicts: bool = True
    conflict_marker_style: str = "git"
    create_backup: bool = True
    backup_extension: str = ".orig"


@dataclass
class ApplicationSettings:
    """Main application settings container."""
    comparison: ComparisonSettings = field(default_factory=ComparisonSettings)
    ui: UISettings = field(default_factory=UISettings)
    colors: ColorSettings = field(default_factory=ColorSettings)
    merge: MergeSettings = field(default_factory=MergeSettings)
    
    recent_left_paths: list[str] = field(default_factory=list)
    recent_right_paths: list[str] = field(default_factory=list)
    recent_comparisons: list[tuple[str, str]] = field(default_factory=list)
    last_directory: str = ""


class SettingsManager:
    """Manager for loading/saving application settings."""
    
    def __init__(self, settings_path: Optional[Path] = None):
        self.settings_path = settings_path or self._get_default_path()
        self._settings: Optional[ApplicationSettings] = None
        self._observers: list[callable] = []
    
    @staticmethod
    def _get_default_path() -> Path:
        """Get the default settings file path."""
        if os.name == 'nt':
            # Windows
            app_data = os.environ.get('APPDATA', os.path.expanduser('~'))
            return Path(app_data) / 'FileCompare' / 'settings.json'
        else:
            # Linux/Mac
            config_home = os.environ.get('XDG_CONFIG_HOME', 
                                         os.path.expanduser('~/.config'))
            return Path(config_home) / 'filecompare' / 'settings.json'
    
    @property
    def settings(self) -> ApplicationSettings:
        """Get current settings, loading from disk if needed."""
        if self._settings is None:
            self._settings = self.load()
        return self._settings
    
    def load(self) -> ApplicationSettings:
        """Load settings from disk."""
        if not self.settings_path.exists():
            return ApplicationSettings()
        
        try:
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            loaded_settings = self._from_dict(data)

            return loaded_settings
        except Exception:
            return ApplicationSettings()
    
    def save(self, settings: Optional[ApplicationSettings] = None) -> bool:
        """Save settings to disk."""
        settings = settings or self._settings
        if settings is None:
            return False
        
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = self._to_dict(settings)
            
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self._settings = settings
            self._notify_observers()
            return True
            
        except Exception:
            return False
    
    def reset(self) -> ApplicationSettings:
        """Reset to default settings."""
        self._settings = ApplicationSettings()
        self.save()
        return self._settings
    
    def add_observer(self, callback: callable) -> None:
        """Add a callback to be notified of settings changes."""
        self._observers.append(callback)
    
    def remove_observer(self, callback: callable) -> None:
        """Remove a settings change observer."""
        if callback in self._observers:
            self._observers.remove(callback)
    
    def _notify_observers(self) -> None:
        """Notify all observers of settings change."""
        for callback in self._observers:
            try:
                callback(self._settings)
            except Exception:
                pass
    
    def add_recent_path(self, path: str, is_left: bool) -> None:
        """Add a path to recent files list."""
        settings = self.settings
        
        if is_left:
            recent = settings.recent_left_paths
        else:
            recent = settings.recent_right_paths
        
        # Remove if already exists
        if path in recent:
            recent.remove(path)
        
        # Add to front
        recent.insert(0, path)
        
        # Trim to limit
        limit = settings.ui.recent_files_limit
        if is_left:
            settings.recent_left_paths = recent[:limit]
        else:
            settings.recent_right_paths = recent[:limit]
        
        self.save()
    
    def _to_dict(self, settings: ApplicationSettings) -> dict:
        """Convert settings to dictionary for JSON serialization."""
        def convert(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.name
            elif hasattr(obj, '__dataclass_fields__'):
                return {k: convert(v) for k, v in asdict(obj).items()}
            elif isinstance(obj, list):
                return [convert(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            else:
                return obj
        
        return convert(settings)
    
    def _from_dict(self, data: dict) -> ApplicationSettings:
        """Convert dictionary back to settings objects."""
        def get_enum(enum_class: type, value: Any) -> Enum:
            if isinstance(value, str):
                try:
                    return enum_class[value]
                except KeyError:
                    return list(enum_class)[0]
            return value
        
        comparison = ComparisonSettings(
            ignore_whitespace=data.get('comparison', {}).get('ignore_whitespace', False),
            ignore_case=data.get('comparison', {}).get('ignore_case', False),
            ignore_blank_lines=data.get('comparison', {}).get('ignore_blank_lines', False),
            ignore_line_endings=data.get('comparison', {}).get('ignore_line_endings', True),
            context_lines=data.get('comparison', {}).get('context_lines', 3),
            diff_style=get_enum(DiffStyle, data.get('comparison', {}).get('diff_style', 'SIDE_BY_SIDE')),
            show_line_numbers=data.get('comparison', {}).get('show_line_numbers', True),
            word_wrap=data.get('comparison', {}).get('word_wrap', False),
            tab_size=data.get('comparison', {}).get('tab_size', 4),
            recursive=data.get('comparison', {}).get('recursive', True),
            follow_symlinks=data.get('comparison', {}).get('follow_symlinks', False),
            compare_file_contents=data.get('comparison', {}).get('compare_file_contents', True),
            quick_compare_by_size=data.get('comparison', {}).get('quick_compare_by_size', True),
            include_patterns=data.get('comparison', {}).get('include_patterns', []),
            exclude_patterns=data.get('comparison', {}).get('exclude_patterns', 
                ComparisonSettings().exclude_patterns),
        )
        
        ui = UISettings(
            theme=get_enum(Theme, data.get('ui', {}).get('theme', 'SYSTEM')),
            font_family=data.get('ui', {}).get('font_family', 'Consolas'),
            font_size=data.get('ui', {}).get('font_size', 10),
            window_width=data.get('ui', {}).get('window_width', 1200),
            window_height=data.get('ui', {}).get('window_height', 800),
            window_maximized=data.get('ui', {}).get('window_maximized', False),
            splitter_position=data.get('ui', {}).get('splitter_position', 500),
            show_toolbar=data.get('ui', {}).get('show_toolbar', True),
            show_statusbar=data.get('ui', {}).get('show_statusbar', True),
            recent_files_limit=data.get('ui', {}).get('recent_files_limit', 5),
            recent_history_limit=data.get('ui', {}).get('recent_history_limit', 10),
        )
        
        colors_data = data.get('colors', {})
        colors = ColorSettings(
            added_background=colors_data.get('added_background', ColorSettings().added_background),
            removed_background=colors_data.get('removed_background', ColorSettings().removed_background),
            modified_background=colors_data.get('modified_background', ColorSettings().modified_background),
            identical_background=colors_data.get('identical_background', ColorSettings().identical_background),
            conflict_background=colors_data.get('conflict_background', ColorSettings().conflict_background),
            added_text=colors_data.get('added_text', ColorSettings().added_text),
            removed_text=colors_data.get('removed_text', ColorSettings().removed_text),
            modified_text=colors_data.get('modified_text', ColorSettings().modified_text),
            line_number_color=colors_data.get('line_number_color', ColorSettings().line_number_color),
            line_number_background=colors_data.get('line_number_background', ColorSettings().line_number_background),
            folder_identical_color=colors_data.get('folder_identical_color', ColorSettings().folder_identical_color),
            folder_modified_color=colors_data.get('folder_modified_color', ColorSettings().folder_modified_color),
            folder_left_only_color=colors_data.get('folder_left_only_color', ColorSettings().folder_left_only_color),
            folder_right_only_color=colors_data.get('folder_right_only_color', ColorSettings().folder_right_only_color),
            folder_conflict_color=colors_data.get('folder_conflict_color', ColorSettings().folder_conflict_color),
        )
        
        merge = MergeSettings(
            auto_resolve_identical=data.get('merge', {}).get('auto_resolve_identical', True),
            auto_resolve_whitespace=data.get('merge', {}).get('auto_resolve_whitespace', True),
            show_base_in_conflicts=data.get('merge', {}).get('show_base_in_conflicts', True),
            conflict_marker_style=data.get('merge', {}).get('conflict_marker_style', 'git'),
            create_backup=data.get('merge', {}).get('create_backup', True),
            backup_extension=data.get('merge', {}).get('backup_extension', '.orig'),
        )
        
        return ApplicationSettings(
            comparison=comparison,
            ui=ui,
            colors=colors,
            merge=merge,
            recent_left_paths=data.get('recent_left_paths', []),
            recent_right_paths=data.get('recent_right_paths', []),
            recent_comparisons=data.get('recent_comparisons', []),
            last_directory=data.get('last_directory', ''),
        )