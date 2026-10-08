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
    CancellableWorker,
    WorkerSignals,
    WorkerState,
)
from app.workers.compare_worker import (
    BinaryCompareWorker,
    FolderCompareWorker,
    ImageCompareWorker,
    TextCompareWorker,
)
from app.workers.hash_worker import (
    BatchHashWorker,
    HashWorker,
)
from app.workers.merge_worker import (
    MergeWorker,
)
from app.workers.scan_worker import (
    BatchScanWorker,
    FolderScanWorker,
)
from app.workers.search_worker import (
    CombinedSearchWorker,
    SearchWorker,
    SearchWorkerSignals,
)
from app.workers.sync_worker import (
    SyncPlanWorker,
    SyncWorker,
)
from app.workers.thread_pool import (
    TaskQueue,
    WorkerPool,
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
    # Search
    'SearchWorker',
    'SearchWorkerSignals',
    'CombinedSearchWorker',
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
