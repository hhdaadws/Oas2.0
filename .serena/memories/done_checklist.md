# When a task is completed
- Run focused regression tests for touched behavior.
- If needed, run `.venv\Scripts\pytest` for broader validation.
- Ensure formatting/lint compatibility with `black src` and `flake8 src`.
- Confirm API behavior aligns with 2026-02 execution agreements (executor-first, strict enabled semantics, merge strategy for task-config).
- Summarize changed files and why behavior is now correct.