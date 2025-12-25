"""
Base worker classes for background operations.

Provides common functionality for all workers:
- Progress reporting
- Cancellation
- Error handling
- State management
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Generic, Optional, TypeVar

from PyQt6.QtCore import QObject, QThread, QRunnable, pyqtSignal, pyqtSlot, QMutex, QMutexLocker


class WorkerState(Enum):
    """State of a worker."""
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    CANCELLING = auto()
    CANCELLED = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class ProgressInfo:
    """Progress information from a worker."""
    current: int
    total: int
    message: str = ""
    detail: str = ""
    
    @property
    def percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100
    
    @property
    def is_indeterminate(self) -> bool:
        return self.total == 0


class WorkerSignals(QObject):
    """
    Signals for worker communication.
    
    These signals are used to communicate between
    the worker thread and the UI thread.
    """
    # Progress update: (current, total, message)
    progress = pyqtSignal(int, int, str)
    
    # Detailed progress: ProgressInfo object
    progress_detail = pyqtSignal(object)
    
    # Status message
    status = pyqtSignal(str)
    
    # Worker started
    started = pyqtSignal()
    
    # Worker finished successfully with result
    finished = pyqtSignal(object)
    
    # Worker failed with error
    error = pyqtSignal(str, str)  # (error_type, message)
    
    # Worker was cancelled
    cancelled = pyqtSignal()
    
    # State changed
    state_changed = pyqtSignal(object)  # WorkerState


T = TypeVar('T')



class WorkerMeta(type(QObject), type(ABC)):
    pass


class BaseWorker(QObject, ABC, metaclass=WorkerMeta):
    """
    Base class for workers that run in a QThread.
    
    Subclass and implement the `run` method.
    
    Usage:
        worker = MyWorker(args)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.start()
    """
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.signals = WorkerSignals()
        self._state = WorkerState.PENDING
        self._cancelled = False
        self._mutex = QMutex()
        self._result: Any = None
        self._error: Optional[tuple[str, str]] = None
    
    @property
    def state(self) -> WorkerState:
        """Current worker state."""
        with QMutexLocker(self._mutex):
            return self._state
    
    @state.setter
    def state(self, value: WorkerState) -> None:
        with QMutexLocker(self._mutex):
            self._state = value
        self.signals.state_changed.emit(value)
    
    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        with QMutexLocker(self._mutex):
            return self._cancelled
    
    @property
    def result(self) -> Any:
        """Get the result (after completion)."""
        return self._result
    
    @property
    def error(self) -> Optional[tuple[str, str]]:
        """Get error info (after failure)."""
        return self._error
    
    def cancel(self) -> None:
        """Request cancellation."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
            if self._state == WorkerState.RUNNING:
                self._state = WorkerState.CANCELLING
        self.signals.state_changed.emit(WorkerState.CANCELLING)
    
    @pyqtSlot()
    def run(self) -> None:
        """
        Main worker execution method.
        
        This is called when the thread starts.
        Subclasses should not override this directly,
        instead override `do_work`.
        """
        self.state = WorkerState.RUNNING
        self.signals.started.emit()
        
        try:
            result = self.do_work()
            
            if self.is_cancelled:
                self.state = WorkerState.CANCELLED
                self.signals.cancelled.emit()
            else:
                self._result = result
                self.state = WorkerState.COMPLETED
                self.signals.finished.emit(result)
                
        except Exception as e:
            self._error = (type(e).__name__, str(e))
            self.state = WorkerState.FAILED
            self.signals.error.emit(type(e).__name__, str(e))
    
    @abstractmethod
    def do_work(self) -> Any:
        """
        Perform the actual work.
        
        Subclasses must implement this method.
        Should check `is_cancelled` periodically and return early if True.
        
        Returns:
            The result of the work.
        """
        pass
    
    def report_progress(
        self,
        current: int,
        total: int,
        message: str = ""
    ) -> None:
        """Report progress to the UI thread."""
        self.signals.progress.emit(current, total, message)
    
    def report_progress_detail(self, info: ProgressInfo) -> None:
        """Report detailed progress."""
        self.signals.progress_detail.emit(info)
    
    def report_status(self, message: str) -> None:
        """Report a status message."""
        self.signals.status.emit(message)
    
    def check_cancelled(self) -> bool:
        """
        Check if cancelled and raise if so.
        
        Convenience method for cleaner cancellation handling.
        """
        if self.is_cancelled:
            raise CancelledException("Operation cancelled")
        return False


class CancelledException(Exception):
    """Raised when a worker is cancelled."""
    pass


class CancellableWorker(BaseWorker):
    """
    Base class for workers with enhanced cancellation support.
    
    Provides helper methods for periodic cancellation checks.
    """
    
    def __init__(self, check_interval: int = 100, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._check_interval = check_interval
        self._operation_count = 0
    
    def maybe_check_cancelled(self) -> bool:
        """
        Periodically check for cancellation.
        
        Only actually checks every `check_interval` calls
        to reduce overhead.
        """
        self._operation_count += 1
        if self._operation_count >= self._check_interval:
            self._operation_count = 0
            return self.is_cancelled
        return False


class RunnableWorker(QRunnable):
    """
    Worker that can be submitted to QThreadPool.
    
    More lightweight than QThread-based workers,
    suitable for many small tasks.
    """
    
    def __init__(
        self,
        func: Callable[..., T],
        *args,
        **kwargs
    ):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancelled = False
        self.setAutoDelete(True)
    
    @pyqtSlot()
    def run(self) -> None:
        """Execute the function."""
        try:
            result = self.func(*self.args, **self.kwargs)
            if not self._cancelled:
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(type(e).__name__, str(e))
    
    def cancel(self) -> None:
        """Request cancellation."""
        self._cancelled = True


class WorkerThread(QThread):
    """
    Convenience class for running a worker in its own thread.
    
    Usage:
        thread = WorkerThread(my_worker)
        thread.start()
        # Worker runs in thread
        thread.wait()  # Wait for completion
    """
    
    def __init__(
        self,
        worker: BaseWorker,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.worker = worker
        self.worker.moveToThread(self)
        
        # Connect signals
        self.started.connect(self.worker.run)
        self.worker.signals.finished.connect(self.quit)
        self.worker.signals.error.connect(self.quit)
        self.worker.signals.cancelled.connect(self.quit)
    
    def cancel(self) -> None:
        """Cancel the worker."""
        self.worker.cancel()
    
    @property
    def result(self) -> Any:
        """Get the worker's result."""
        return self.worker.result
    
    @property
    def error(self) -> Optional[tuple[str, str]]:
        """Get error info if failed."""
        return self.worker.error


class ChainedWorker(BaseWorker):
    """
    Worker that chains multiple workers together.
    
    Executes workers in sequence, passing results between them.
    """
    
    def __init__(
        self,
        workers: list[BaseWorker],
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.workers = workers
        self._current_worker_index = 0
    
    def do_work(self) -> list[Any]:
        """Execute all workers in sequence."""
        results = []
        
        for i, worker in enumerate(self.workers):
            if self.is_cancelled:
                break
            
            self._current_worker_index = i
            self.report_status(f"Step {i + 1}/{len(self.workers)}")
            
            # Run worker synchronously
            result = worker.do_work()
            results.append(result)
            
            if worker.is_cancelled:
                self.cancel()
                break
        
        return results
    
    def cancel(self) -> None:
        """Cancel current and pending workers."""
        super().cancel()
        if self._current_worker_index < len(self.workers):
            self.workers[self._current_worker_index].cancel()