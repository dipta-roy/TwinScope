"""
Background workers for non-blocking operations.

Provides QThread-based workers for:
- File comparison
- Folder comparison and scanning
- Synchronization
- Hashing
- General long-running tasks

All workers use Qt signals for thread-safe communication
with the UI thread.
"""

from app.workers.base_worker import (
    BaseWorker,
    WorkerSignals,
    WorkerState,
    CancellableWorker,
)
from app.workers.compare_worker import (
    TextCompareWorker,
    BinaryCompareWorker,
    ImageCompareWorker,
    FolderCompareWorker,
)
from app.workers.scan_worker import (
    FolderScanWorker,
    BatchScanWorker,
)
from app.workers.sync_worker import (
    SyncWorker,
    SyncPlanWorker,
)
from app.workers.hash_worker import (
    HashWorker,
    BatchHashWorker,
)
from app.workers.merge_worker import (
    MergeWorker,
)
from app.workers.thread_pool import (
    WorkerPool,
    TaskQueue,
)

__all__ = [
    # Base
    'BaseWorker',
    'WorkerSignals',
    'WorkerState',
    'CancellableWorker',
    # Compare
    'TextCompareWorker',
    'BinaryCompareWorker',
    'ImageCompareWorker',
    'FolderCompareWorker',
    # Scan
    'FolderScanWorker',
    'BatchScanWorker',
    # Sync
    'SyncWorker',
    'SyncPlanWorker',
    # Hash
    'HashWorker',
    'BatchHashWorker',
    # Merge
    'MergeWorker',
    # Pool
    'WorkerPool',
    'TaskQueue',
]