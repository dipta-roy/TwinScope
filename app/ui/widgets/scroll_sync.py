"""
Scroll synchronization helper for diff text editors.
"""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QAbstractScrollArea


class ScrollSync(QObject):
    """
    Coordinates synchronized scrolling between multiple text editor panels.
    Prevents recursive scroll event feedback loops.
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._enabled: bool = True
        self._syncing: bool = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def sync_to(self, target: QAbstractScrollArea, h: int, v: int) -> None:
        """Synchronize scrollbar positions to target."""
        if not self._enabled or self._syncing:
            return

        self._syncing = True
        try:
            h_bar = target.horizontalScrollBar()
            if h_bar is not None and h_bar.value() != h:
                h_bar.setValue(h)

            v_bar = target.verticalScrollBar()
            if v_bar is not None and v_bar.value() != v:
                v_bar.setValue(v)
        finally:
            self._syncing = False

    def sync_between(self, source: QAbstractScrollArea, target: QAbstractScrollArea) -> None:
        """Synchronize vertical and horizontal scrollbars from source to target."""
        if not self._enabled or self._syncing:
            return

        src_h = source.horizontalScrollBar()
        src_v = source.verticalScrollBar()
        h_val = src_h.value() if src_h is not None else 0
        v_val = src_v.value() if src_v is not None else 0
        self.sync_to(target, h_val, v_val)
