from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / "src" / "app"


def _read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_legacy_scheduler_modules_removed():
    assert not (SRC_DIR / "modules" / "tasks" / "simple_scheduler.py").exists()
    assert not (SRC_DIR / "modules" / "tasks" / "scheduler.py").exists()


def test_tasks_router_has_no_legacy_scheduler_endpoints_or_fields():
    content = _read_utf8(SRC_DIR / "modules" / "web" / "routers" / "tasks.py")
    banned_tokens = [
        "/simple-scheduler/",
        "trigger-foster",
        "load-pending",
        "check-time-tasks",
        "check-conditions",
        "legacy_simple_scheduler_deprecated",
        "legacy_simple_scheduler_running",
    ]
    for token in banned_tokens:
        assert token not in content


def test_dashboard_router_has_no_legacy_scheduler_fallback():
    content = _read_utf8(SRC_DIR / "modules" / "web" / "routers" / "dashboard.py")
    banned_tokens = [
        "simple_scheduler",
        "ENABLE_LEGACY_DASHBOARD_FALLBACK",
    ]
    for token in banned_tokens:
        assert token not in content
