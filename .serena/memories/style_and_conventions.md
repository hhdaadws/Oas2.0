# Style and conventions
- Python: 4-space indentation, PEP 8, snake_case for modules/functions, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Prefer type hints for public functions.
- Vue components use PascalCase filenames.
- API modules in frontend use business-oriented lowercase naming.
- Avoid introducing behavior that re-enables disabled tasks; follow strict config merge semantics and strict enable checks (`enabled is True`).
- Keep changes focused and avoid mixing unrelated backend/frontend/docs edits in one change.