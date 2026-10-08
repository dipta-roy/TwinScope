"""
Background search worker threads.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Tuple

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from app.constants.constants import MAX_SEARCH_MATCHES

logger = logging.getLogger(__name__)


class SearchWorkerSignals(QObject):
    """Signals for SearchWorker."""
    finished = pyqtSignal(object)  # Returns list of (start, end, text) tuples
    error = pyqtSignal(str)


class SearchWorker(QRunnable):
    """
    Worker for running regex searches in background thread.
    """

    def __init__(self, text: str, pattern: str, options: Any):
        super().__init__()
        self.text = text
        self.pattern = pattern
        self.options = options
        self.signals = SearchWorkerSignals()

    def run(self) -> None:
        try:
            matches: List[Tuple[int, int, str]] = []
            flags = 0
            if not getattr(self.options, "case_sensitive", False):
                flags |= re.IGNORECASE

            regex = re.compile(self.pattern, flags)
            max_matches = MAX_SEARCH_MATCHES
            count = 0

            for match in regex.finditer(self.text):
                matches.append((match.start(), match.end(), match.group()))
                count += 1
                if count >= max_matches:
                    break

            self.signals.finished.emit(matches)

        except re.error as e:
            logger.debug(f"SearchWorker regex syntax error for pattern '{self.pattern}': {e}")
            self.signals.error.emit(str(e))
        except Exception as e:
            logger.error(f"SearchWorker unexpected error: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class CombinedSearchWorker(QRunnable):
    """Worker to search multiple texts concurrently."""

    def __init__(self, text_data: list, pattern: str, options: Any):
        super().__init__()
        self.text_data = text_data  # [(name, text), ...]
        self.pattern = pattern
        self.options = options
        self.signals = SearchWorkerSignals()

    def run(self) -> None:
        try:
            results = []  # [(name, match_tuples, term, options), ...]
            flags = 0
            if not getattr(self.options, "case_sensitive", False):
                flags |= re.IGNORECASE

            regex = re.compile(self.pattern, flags)
            max_matches = MAX_SEARCH_MATCHES

            for name, text in self.text_data:
                matches: List[Tuple[int, int, str]] = []
                count = 0
                for match in regex.finditer(text):
                    matches.append((match.start(), match.end(), match.group()))
                    count += 1
                    if count >= max_matches:
                        break

                results.append((name, matches, self.pattern, self.options))

            self.signals.finished.emit(results)
        except re.error as e:
            logger.debug(f"CombinedSearchWorker regex syntax error for pattern '{self.pattern}': {e}")
            self.signals.error.emit(str(e))
        except Exception as e:
            logger.error(f"CombinedSearchWorker unexpected error: {e}", exc_info=True)
            self.signals.error.emit(str(e))
