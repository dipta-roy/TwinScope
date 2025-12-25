"""
Thread pool management for worker tasks.

Provides a managed pool of worker threads for
executing multiple tasks efficiently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from queue import Queue, Empty
from threading import Lock
from typing import Any, Callable, Generic, Optional, TypeVar
from collections import deque

from PyQt6.QtCore import QObject, QThread, QThreadPool, QRunnable, pyqtSignal, QMutex, QMutexLocker

from app.workers.base_worker import BaseWorker, WorkerSignals, RunnableWorker


T = TypeVar('T')


class TaskPriority(Enum):
    """Priority levels for tasks."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Task:
    """A task to be executed by the pool."""
    id: str
    func: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    callback: Optional[Callable[[Any], None]] = None
    error_callback: Optional[Callable[[Exception], None]] = None
    
    def __lt__(self, other: 'Task') -> bool:
        """Compare by priority for heap ordering."""
        return self.priority.value > other.priority.value


class WorkerPool(QObject):
    """
    Managed pool of worker threads.
    
    Uses Qt's QThreadPool for efficient thread management.
    
    Usage:
        pool = WorkerPool()
        pool.submit(my_function, arg1, arg2, callback=on_complete)
        pool.wait_all()
    """
    
    # Signal when all tasks complete
    all_complete = pyqtSignal()
    
    # Signal for task completion
    task_complete = pyqtSignal(str, object)  # (task_id, result)
    
    # Signal for task error
    task_error = pyqtSignal(str, str)  # (task_id, error)
    
    def __init__(
        self,
        max_workers: Optional[int] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        
        self._pool = QThreadPool.globalInstance()
        if max_workers is not None:
            self._pool.setMaxThreadCount(max_workers)
        
        self._pending_count = 0
        self._mutex = QMutex()
        self._task_counter = 0
    
    @property
    def max_workers(self) -> int:
        """Maximum number of worker threads."""
        return self._pool.maxThreadCount()
    
    @max_workers.setter
    def max_workers(self, value: int) -> None:
        self._pool.setMaxThreadCount(value)
    
    @property
    def active_count(self) -> int:
        """Number of currently active threads."""
        return self._pool.activeThreadCount()
    
    @property
    def pending_count(self) -> int:
        """Number of pending tasks."""
        with QMutexLocker(self._mutex):
            return self._pending_count
    
    def submit(
        self,
        func: Callable[..., T],
        *args,
        callback: Optional[Callable[[T], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        **kwargs
    ) -> str:
        """
        Submit a function to be executed in the pool.
        
        Args:
            func: Function to execute
            *args: Arguments to pass to function
            callback: Called with result on success
            error_callback: Called with exception on error
            priority: Task priority
            **kwargs: Keyword arguments to pass to function
            
        Returns:
            Task ID that can be used to track the task
        """
        with QMutexLocker(self._mutex):
            self._task_counter += 1
            task_id = f"task_{self._task_counter}"
            self._pending_count += 1
        
        # Create runnable
        runnable = _PoolRunnable(
            task_id,
            func,
            args,
            kwargs,
            self._on_task_complete,
            self._on_task_error,
            callback,
            error_callback
        )
        
        # Set priority
        qt_priority = {
            TaskPriority.LOW: 0,
            TaskPriority.NORMAL: 1,
            TaskPriority.HIGH: 2,
            TaskPriority.CRITICAL: 3,
        }.get(priority, 1)
        
        # Submit to pool
        self._pool.start(runnable, qt_priority)
        
        return task_id
    
    def submit_worker(
        self,
        worker: BaseWorker,
        callback: Optional[Callable[[Any], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None
    ) -> str:
        """
        Submit a BaseWorker to the pool.
        
        The worker's do_work method will be executed.
        """
        return self.submit(
            worker.do_work,
            callback=callback,
            error_callback=error_callback
        )
    
    def map(
        self,
        func: Callable[[T], Any],
        items: list[T],
        callback: Optional[Callable[[list[Any]], None]] = None
    ) -> list[str]:
        """
        Apply function to all items in parallel.
        
        Args:
            func: Function to apply to each item
            items: Items to process
            callback: Called with all results when complete
            
        Returns:
            List of task IDs
        """
        task_ids = []
        results: list[Any] = [None] * len(items)
        completed = [0]
        lock = Lock()
        
        def on_complete(index: int, result: Any) -> None:
            with lock:
                results[index] = result
                completed[0] += 1
                if completed[0] == len(items) and callback:
                    callback(results)
        
        for i, item in enumerate(items):
            task_id = self.submit(
                func,
                item,
                callback=lambda r, idx=i: on_complete(idx, r)
            )
            task_ids.append(task_id)
        
        return task_ids
    
    def wait_all(self, timeout: int = -1) -> bool:
        """
        Wait for all tasks to complete.
        
        Args:
            timeout: Timeout in milliseconds (-1 for infinite)
            
        Returns:
            True if all tasks completed, False if timeout
        """
        return self._pool.waitForDone(timeout)
    
    def clear(self) -> None:
        """Clear pending tasks (already running tasks will complete)."""
        self._pool.clear()
        with QMutexLocker(self._mutex):
            self._pending_count = 0
    
    def _on_task_complete(self, task_id: str, result: Any) -> None:
        """Handle task completion."""
        with QMutexLocker(self._mutex):
            self._pending_count -= 1
            pending = self._pending_count
        
        self.task_complete.emit(task_id, result)
        
        if pending == 0:
            self.all_complete.emit()
    
    def _on_task_error(self, task_id: str, error: str) -> None:
        """Handle task error."""
        with QMutexLocker(self._mutex):
            self._pending_count -= 1
            pending = self._pending_count
        
        self.task_error.emit(task_id, error)
        
        if pending == 0:
            self.all_complete.emit()


class _PoolRunnable(QRunnable):
    """Internal runnable for pool execution."""
    
    def __init__(
        self,
        task_id: str,
        func: Callable,
        args: tuple,
        kwargs: dict,
        on_complete: Callable,
        on_error: Callable,
        user_callback: Optional[Callable],
        user_error_callback: Optional[Callable]
    ):
        super().__init__()
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.on_complete = on_complete
        self.on_error = on_error
        self.user_callback = user_callback
        self.user_error_callback = user_error_callback
        self.setAutoDelete(True)
    
    def run(self) -> None:
        """Execute the task."""
        try:
            result = self.func(*self.args, **self.kwargs)
            
            if self.user_callback:
                self.user_callback(result)
            
            self.on_complete(self.task_id, result)
            
        except Exception as e:
            if self.user_error_callback:
                self.user_error_callback(e)
            
            self.on_error(self.task_id, str(e))


class TaskQueue(QObject):
    """
    Sequential task queue.
    
    Executes tasks one at a time in order.
    Useful for operations that must not run concurrently.
    """
    
    # Signal when queue becomes empty
    queue_empty = pyqtSignal()
    
    # Signal for task completion
    task_complete = pyqtSignal(object)  # result
    
    # Signal for task error
    task_error = pyqtSignal(str)  # error message
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        
        self._queue: deque[Task] = deque()
        self._running = False
        self._current_thread: Optional[QThread] = None
        self._current_worker: Optional[BaseWorker] = None
        self._mutex = QMutex()
    
    @property
    def is_running(self) -> bool:
        """Check if a task is currently running."""
        with QMutexLocker(self._mutex):
            return self._running
    
    @property
    def queue_length(self) -> int:
        """Number of pending tasks."""
        with QMutexLocker(self._mutex):
            return len(self._queue)
    
    def enqueue(
        self,
        func: Callable[..., Any],
        *args,
        callback: Optional[Callable[[Any], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None,
        **kwargs
    ) -> None:
        """Add a task to the queue."""
        task = Task(
            id=f"task_{len(self._queue)}",
            func=func,
            args=args,
            kwargs=kwargs,
            callback=callback,
            error_callback=error_callback
        )
        
        with QMutexLocker(self._mutex):
            self._queue.append(task)
        
        self._process_next()
    
    def enqueue_worker(
        self,
        worker: BaseWorker,
        callback: Optional[Callable[[Any], None]] = None
    ) -> None:
        """Add a worker to the queue."""
        self.enqueue(worker.do_work, callback=callback)
    
    def clear(self) -> None:
        """Clear pending tasks."""
        with QMutexLocker(self._mutex):
            self._queue.clear()
    
    def cancel_current(self) -> None:
        """Cancel the currently running task."""
        with QMutexLocker(self._mutex):
            if self._current_worker:
                self._current_worker.cancel()
    
    def _process_next(self) -> None:
        """Process the next task in queue."""
        with QMutexLocker(self._mutex):
            if self._running or not self._queue:
                return
            
            self._running = True
            task = self._queue.popleft()
        
        # Create worker for task
        worker = _TaskWorker(task)
        thread = QThread()
        
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.signals.finished.connect(lambda r: self._on_task_complete(task, r))
        worker.signals.error.connect(lambda t, m: self._on_task_error(task, m))
        worker.signals.finished.connect(thread.quit)
        worker.signals.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        
        with QMutexLocker(self._mutex):
            self._current_thread = thread
            self._current_worker = worker
        
        thread.start()
    
    def _on_task_complete(self, task: Task, result: Any) -> None:
        """Handle task completion."""
        if task.callback:
            task.callback(result)
        
        self.task_complete.emit(result)
        
        with QMutexLocker(self._mutex):
            self._running = False
            self._current_thread = None
            self._current_worker = None
            has_more = len(self._queue) > 0
        
        if has_more:
            self._process_next()
        else:
            self.queue_empty.emit()
    
    def _on_task_error(self, task: Task, error: str) -> None:
        """Handle task error."""
        if task.error_callback:
            task.error_callback(Exception(error))
        
        self.task_error.emit(error)
        
        with QMutexLocker(self._mutex):
            self._running = False
            self._current_thread = None
            self._current_worker = None
            has_more = len(self._queue) > 0
        
        if has_more:
            self._process_next()
        else:
            self.queue_empty.emit()


class _TaskWorker(BaseWorker):
    """Internal worker for queue tasks."""
    
    def __init__(self, task: Task):
        super().__init__()
        self.task = task
    
    def do_work(self) -> Any:
        """Execute the task."""
        return self.task.func(*self.task.args, **self.task.kwargs)


class BatchProcessor(QObject):
    """
    Batch processor for processing items with progress.
    
    Processes items in batches to allow for UI updates.
    """
    
    # Progress signal: (processed, total, current_item)
    progress = pyqtSignal(int, int, object)
    
    # Completion signal
    complete = pyqtSignal(list)  # results
    
    # Error signal
    error = pyqtSignal(str)
    
    def __init__(
        self,
        batch_size: int = 100,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.batch_size = batch_size
        self._cancelled = False
    
    def process(
        self,
        items: list[T],
        processor: Callable[[T], Any],
        use_thread: bool = True
    ) -> None:
        """
        Process items.
        
        Args:
            items: Items to process
            processor: Function to apply to each item
            use_thread: Whether to run in background thread
        """
        self._cancelled = False
        
        if use_thread:
            from functools import partial
            worker = RunnableWorker(
                partial(self._do_process, items, processor)
            )
            worker.signals.finished.connect(self.complete.emit)
            worker.signals.error.connect(lambda t, m: self.error.emit(m))
            QThreadPool.globalInstance().start(worker)
        else:
            try:
                results = self._do_process(items, processor)
                self.complete.emit(results)
            except Exception as e:
                self.error.emit(str(e))
    
    def cancel(self) -> None:
        """Cancel processing."""
        self._cancelled = True
    
    def _do_process(
        self,
        items: list[T],
        processor: Callable[[T], Any]
    ) -> list[Any]:
        """Process items with progress reporting."""
        results = []
        total = len(items)
        
        for i, item in enumerate(items):
            if self._cancelled:
                break
            
            result = processor(item)
            results.append(result)
            
            # Emit progress periodically
            if i % self.batch_size == 0 or i == total - 1:
                self.progress.emit(i + 1, total, item)
        
        return results