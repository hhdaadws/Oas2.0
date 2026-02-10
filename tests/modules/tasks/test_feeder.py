from datetime import datetime, timedelta
from types import SimpleNamespace

from app.core.constants import TaskType
from app.modules.executor.types import TaskIntent
from app.modules.tasks.feeder import Feeder


def _account(account_id: int):
    return SimpleNamespace(id=account_id)


def test_select_accounts_for_scan_supports_full_and_incremental():
    feeder = Feeder()
    feeder._scan_batch_size = 2
    feeder._min_rescan_seconds = 20

    now_dt = datetime.utcnow()
    accounts = [_account(1), _account(2), _account(3)]

    first = feeder._select_accounts_for_scan(accounts, now_dt)
    assert len(first) == 3

    feeder._last_full_scan_at = now_dt
    feeder._last_scan_by_account[1] = now_dt
    feeder._last_scan_by_account[2] = now_dt - timedelta(seconds=60)
    feeder._last_scan_by_account[3] = now_dt - timedelta(seconds=60)
    feeder._scan_cursor = 0

    second = feeder._select_accounts_for_scan(accounts, now_dt)
    second_ids = [a.id for a in second]
    assert 1 not in second_ids
    assert len(second_ids) <= 2


def test_signature_recent_with_ttl():
    feeder = Feeder()
    now_dt = datetime.utcnow()

    cfg = {
        "寄养": {
            "enabled": True,
            "next_time": "2026-01-01 00:00",
        }
    }
    intents = [TaskIntent(account_id=9, task_type=TaskType.FOSTER)]
    signature = feeder._build_signature(9, cfg, intents)

    feeder._last_enqueued_signature[9] = (signature, now_dt)
    assert feeder._is_signature_recent(9, signature, now_dt + timedelta(seconds=5))

    stale_time = now_dt + timedelta(seconds=feeder._signature_ttl_seconds + 1)
    assert feeder._is_signature_recent(9, signature, stale_time) is False
