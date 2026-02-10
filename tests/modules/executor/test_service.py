import pytest

from app.core.constants import TaskType
from app.modules.executor.service import ExecutorService, PendingBatch
from app.modules.executor.types import TaskIntent


@pytest.mark.asyncio
async def test_dispatchable_index_skips_blocked_head():
    service = ExecutorService()
    service._dispatch_window = 2
    service._pending = [
        PendingBatch(
            account_id=1,
            intents=[TaskIntent(account_id=1, task_type=TaskType.FOSTER)],
            state="dispatching",
        ),
        PendingBatch(
            account_id=2,
            intents=[TaskIntent(account_id=2, task_type=TaskType.DELEGATE)],
            state="queued",
        ),
        PendingBatch(
            account_id=3,
            intents=[TaskIntent(account_id=3, task_type=TaskType.COOP)],
            state="queued",
        ),
    ]

    index = service._pick_dispatchable_index()
    assert index == 1


@pytest.mark.asyncio
async def test_on_task_done_retries_then_fails():
    service = ExecutorService()

    batch = PendingBatch(
        account_id=10,
        intents=[TaskIntent(account_id=10, task_type=TaskType.DELEGATE_HELP)],
        state="running",
        retry_count=0,
    )

    service._running_accounts.add(10)
    service._running_batches[10] = batch

    await service._on_task_done(10, success=False)

    assert len(service._pending) == 1
    assert service._pending[0].retry_count == 1
    assert service._metrics["dispatch_retry"] == 1

    retried_batch = service._pending.pop(0)
    retried_batch.state = "running"
    service._running_accounts.add(10)
    service._running_batches[10] = retried_batch

    await service._on_task_done(10, success=False)

    assert service._metrics["batch_failed"] == 1
    assert len(service._failed_batches) == 1
    assert service._failed_batches[0]["account_id"] == 10
