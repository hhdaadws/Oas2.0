from types import SimpleNamespace

import pytest

from app.core.constants import TaskType
from app.modules.emu.async_adapter import AsyncEmulatorAdapter
from app.modules.executor.types import TaskIntent
import app.modules.executor.worker as worker_module
from app.modules.executor.worker import WorkerActor
from app.modules.ui.manager import CangbaogeListedException
from app.modules.ui.popups import JihaoPopupException


class _DummySyncAdapter:
    def __init__(self):
        self.cfg = SimpleNamespace(
            adb_addr="127.0.0.1:16384",
            pkg_name="com.test.game",
        )
        self.adb = SimpleNamespace()
        self.ipc = object()
        self.mumu = None


def _build_worker():
    emulator = SimpleNamespace(id=1, name="emu-1", adb_addr="127.0.0.1:16384")
    syscfg = SimpleNamespace(save_fail_screenshot=False, capture_method="adb")
    return WorkerActor(emulator, system_config=syscfg, on_done=None)


@pytest.mark.asyncio
async def test_final_cleanup_uses_async_adapter_adb_helpers():
    worker = _build_worker()
    adapter = AsyncEmulatorAdapter(_DummySyncAdapter())
    calls = []

    async def _fake_force_stop(pkg):
        calls.append(("force_stop", pkg))

    async def _fake_root():
        calls.append(("root", None))
        return True

    async def _fake_shell(cmd, timeout=None):
        calls.append(("shell", cmd, timeout))
        return 0, "ok"

    adapter.adb_force_stop = _fake_force_stop
    adapter.adb_root = _fake_root
    adapter.adb_shell = _fake_shell

    await worker._final_cleanup(adapter)

    assert ("force_stop", worker._PKG_NAME) in calls
    assert ("root", None) in calls
    assert any(item[0] == "shell" for item in calls)


@pytest.mark.asyncio
async def test_execute_batch_tasks_flushes_next_time_once():
    worker = _build_worker()
    flush_calls = []

    async def _fast_wait(task, timeout):
        return await task

    results = iter([True, False])

    async def _fake_run_intent(*args, **kwargs):
        return next(results)

    async def _fake_save_fail(*args, **kwargs):
        return None

    async def _fake_flush(account_id, ops):
        flush_calls.append((account_id, list(ops)))

    worker._wait_with_stale_timeout = _fast_wait
    worker._run_intent = _fake_run_intent
    worker._save_fail_screenshot = _fake_save_fail
    worker._flush_next_time_updates = _fake_flush

    batch = [
        TaskIntent(account_id=1, task_type=TaskType.COOP),
        TaskIntent(account_id=1, task_type=TaskType.XUANSHANG),
    ]
    account = SimpleNamespace(id=1)

    success, _shared_adapter, _shared_ui, abort = await worker._execute_batch_tasks(
        batch,
        account,
        shared_adapter=None,
        shared_ui=None,
    )

    assert success is False
    assert abort is False
    assert len(flush_calls) == 1
    assert flush_calls[0][0] == 1
    actions = [op[0] for op in flush_calls[0][1]]
    assert actions == ["set", "delay"]


@pytest.mark.asyncio
async def test_run_forever_prewarms_emulator_io_pool(monkeypatch):
    worker = _build_worker()
    calls = []

    def _fake_get_emulator_io_pool(adb_addr):
        calls.append(adb_addr)
        return object()

    monkeypatch.setattr(
        worker_module,
        "get_emulator_io_pool",
        _fake_get_emulator_io_pool,
    )

    await worker.stop()
    await worker.run_forever()

    assert calls == [worker.emulator.adb_addr]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raised_exc", "delay_called", "mark_called"),
    [
        (JihaoPopupException("jihao"), True, False),
        (CangbaogeListedException("cangbaoge"), False, True),
    ],
)
async def test_execute_batch_tasks_force_stop_on_abort_exceptions(
    raised_exc, delay_called, mark_called
):
    worker = _build_worker()
    force_stop_calls = {"count": 0}
    delay_calls = {"count": 0}
    mark_calls = {"count": 0}

    async def _fast_wait(task, timeout):
        return await task

    async def _raise_intent(*args, **kwargs):
        raise raised_exc

    async def _fake_save_fail(*args, **kwargs):
        return None

    async def _fake_force_stop(*args, **kwargs):
        force_stop_calls["count"] += 1

    async def _fake_delay(*args, **kwargs):
        delay_calls["count"] += 1

    async def _fake_mark(*args, **kwargs):
        mark_calls["count"] += 1

    worker._wait_with_stale_timeout = _fast_wait
    worker._run_intent = _raise_intent
    worker._save_fail_screenshot = _fake_save_fail
    worker._force_stop_game = _fake_force_stop
    worker._delay_all_tasks_on_jihao = _fake_delay
    worker._mark_account_cangbaoge = _fake_mark

    batch = [TaskIntent(account_id=1, task_type=TaskType.ADD_FRIEND)]
    account = SimpleNamespace(id=1)

    success, _shared_adapter, _shared_ui, abort = await worker._execute_batch_tasks(
        batch,
        account,
        shared_adapter=object(),
        shared_ui=None,
    )

    assert success is False
    assert abort is True
    assert force_stop_calls["count"] == 1
    assert (delay_calls["count"] == 1) is delay_called
    assert (mark_calls["count"] == 1) is mark_called
