# CLAUDE.md
中文回答
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**oas-cloud-go** — Go cloud backend for OAS (Onikami Account System) runtime linkage with a Vue 3 SPA frontend. Multi-tenant service managing managers, users, task generation, and agent-based job execution. Redis is mandatory; the service will not start without it.

## Common Commands

### Backend (Go)

```bash
# Run server (requires PostgreSQL + Redis)
go run ./cmd/server

# Run all tests (uses SQLite in-memory + mock Redis, no external deps needed)
go test ./...

# Run a specific test
go test ./internal/server -run TestFunctionName

# Vet/lint
go vet ./...

# Download dependencies
go mod tidy
```

### Frontend (Vue 3)

```bash
cd frontend
npm install
npm run dev      # Dev server at http://0.0.0.0:5173, proxies /api to :7000
npm run build    # Production build to frontend/dist/
```

### Docker

```bash
cp .env.example .env
docker compose up -d          # Full stack: PostgreSQL + Redis + backend (port 7000)
docker build -t myapp .       # Multi-stage build (Node → Go → distroless)
```

### CI

CI runs `go test ./...` and `go vet ./...` on push to main and on PRs (Go 1.25.7).

## Architecture

### Monorepo Layout

- `cmd/server/main.go` — Entry point: loads config, connects DB/Redis, starts server
- `internal/server/` — Gin HTTP handlers, middleware, request/response types, all backend tests
- `internal/models/` — GORM models (11 entities: SuperAdmin, Manager, User, TaskJob, AgentNode, etc.)
- `internal/auth/` — JWT token management, bcrypt password hashing
- `internal/cache/` — Redis `Store` interface and implementation
- `internal/config/` — Configuration from environment variables (supports `_FILE` suffix for Docker secrets)
- `internal/scheduler/` — Background task generator goroutine with Redis slot-based deduplication
- `internal/taskmeta/` — Task template definitions and pool configs per user type
- `frontend/` — Vue 3 + Vite + Element Plus SPA

### API Structure

All endpoints under `/api/v1`. Route groups by role:

- `/api/v1/super/*` — Super admin: manager lifecycle, renewal keys
- `/api/v1/manager/*` — Manager: activation codes, user CRUD, assets, tasks, overview
- `/api/v1/user/*` — User: profile, tasks, code redemption, sessions
- `/api/v1/agent/*` — Agent: job polling, lease management, heartbeats
- Public: `/health`, `/scheduler/status`, `/task-templates`, `/bootstrap/*`

### Authentication

- **Super/Manager/Agent**: JWT tokens (12h–24h TTL) with role-based middleware
- **Users**: Opaque tokens (180-day TTL) stored in `user_tokens` table
- Middleware in `internal/server/middleware.go` enforces role-based access

### Task Scheduler

Background goroutine (`internal/scheduler/generator.go`) that:
- Scans active users and their `user_task_configs` on a configurable interval (default 10s)
- Generates `task_jobs` for enabled tasks with deduplication via Redis slots
- Supports `next_time` as full datetime or daily `HH:MM` pattern

### Key Patterns

- **Server struct** (`internal/server/server.go`): Central object holding config, DB, Redis, scheduler, token manager, and Gin router
- **Response format**: Success `{"data": ...}`, Error `{"detail": "message"}`
- **JSONB fields**: User assets and task configs use `gorm.io/datatypes` JSON columns
- **Job lifecycle**: pending → leased → running → success/failed/timeout_requeued
- **Tests**: SQLite in-memory DB + map-based mock Redis (`test_helpers_test.go`), HTTP tests via `httptest`

### Frontend Routing

Client-side SPA routing in `App.vue` (no Vue Router library). Pages: `/login`, `/manager`, `/user`, `/super-admin-login`, `/super-admin`. Vite dev server proxies `/api` requests to the Go backend at `:7000`.

### User Types

Three user types with separate task pools: `daily`, `duiyi`, `shuaka`. Activation codes are typed to enforce user type on registration. Task templates in `internal/taskmeta/templates.go` define per-type defaults.
