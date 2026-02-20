import asyncio
import threading
import time

import pytest

from app.core.thread_pool import (
    get_emulator_io_pool,
    run_in_emulator_io,
    shutdown_pools,
)


@pytest.fixture(autouse=True)
def _reset_pools():
    shutdown_pools()
    yield
    shutdown_pools()


@pytest.mark.asyncio
async def test_same_io_key_runs_serially_and_on_same_thread():
    events = []

    def _job(idx: int, delay: float):
        thread_id = threading.get_ident()
        events.append(("start", idx))
        time.sleep(delay)
        events.append(("end", idx))
        return thread_id

    t1, t2, t3 = await asyncio.gather(
        run_in_emulator_io("emu-1", _job, 1, 0.05),
        run_in_emulator_io("emu-1", _job, 2, 0.01),
        run_in_emulator_io("emu-1", _job, 3, 0.0),
    )

    assert t1 == t2 == t3
    assert [item for item in events if item[0] == "end"] == [
        ("end", 1),
        ("end", 2),
        ("end", 3),
    ]


@pytest.mark.asyncio
async def test_different_io_keys_can_run_in_parallel():
    def _sleep_job(delay: float):
        time.sleep(delay)
        return True

    started = time.perf_counter()
    await asyncio.gather(
        run_in_emulator_io("emu-a", _sleep_job, 0.25),
        run_in_emulator_io("emu-b", _sleep_job, 0.25),
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.45


def test_shutdown_pools_recreates_emulator_pool():
    pool1 = get_emulator_io_pool("emu-recreate")
    shutdown_pools()
    pool2 = get_emulator_io_pool("emu-recreate")

    assert pool1 is not pool2
