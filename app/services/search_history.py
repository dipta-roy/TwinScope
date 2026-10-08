"""
Search history persistence service.
"""

from __future__ import annotations

import logging
from typing import List

from PyQt6.QtCore import QSettings

from app.constants.constants import MAX_SEARCH_HISTORY

logger = logging.getLogger(__name__)


class SearchHistory:
    """Manages search history persisted via QSettings."""

    MAX_HISTORY: int = MAX_SEARCH_HISTORY

    def __init__(self, settings_key: str = "search_history"):
        self._history: List[str] = []
        self._settings_key = settings_key
        self._load()

    def add(self, term: str) -> None:
        """Add a term to history."""
        if not term:
            return

        # Remove if already exists
        if term in self._history:
            self._history.remove(term)

        # Add to front
        self._history.insert(0, term)

        # Trim to max
        self._history = self._history[:self.MAX_HISTORY]

        self._save()

    def get_all(self) -> List[str]:
        """Get all history items."""
        return self._history.copy()

    def clear(self) -> None:
        """Clear history."""
        self._history.clear()
        self._save()

    def _load(self) -> None:
        """Load history from settings."""
        try:
            settings = QSettings()
            self._history = settings.value(self._settings_key, [], type=list)
        except Exception as e:
            logger.warning(f"Failed to load search history from settings: {e}")
            self._history = []

    def _save(self) -> None:
        """Save history to settings."""
        try:
            settings = QSettings()
            settings.setValue(self._settings_key, self._history)
        except Exception as e:
            logger.warning(f"Failed to save search history to settings: {e}")
