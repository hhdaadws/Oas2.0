# oas-cloud-go

Go cloud backend for OAS runtime linkage.

> Redis is mandatory in this backend. Service startup will fail when Redis is unreachable.

## Frontend framework

- Framework: **Vue 3 + Vite + Element Plus**
- Location: `frontend/`
- Includes full role consoles (independent pages):
  - Login page: `/login` (manager + user auth only)
  - Manager page: `/manager`
  - User page: `/user`
  - Super admin page: `/super-admin` (manual URL access only, no login-page entry)

## Quick start

```bash
go mod tidy
go run ./cmd/server
```

```bash
cd frontend
npm install
npm run dev
```

## Environment variables

- `ADDR` default `:7000`
- `DATABASE_URL` PostgreSQL DSN
- `DATABASE_URL_FILE` read DSN from mounted secret file
- `REDIS_ADDR` default `127.0.0.1:6379`
- `REDIS_PASSWORD` default empty
- `REDIS_PASSWORD_FILE` read redis password from secret file
- `REDIS_DB` default `0`
- `REDIS_KEY_PREFIX` default `oas:cloud`
- `JWT_SECRET` JWT signing secret
- `JWT_SECRET_FILE` read JWT secret from secret file
- `JWT_TTL` default `24h`
- `AGENT_JWT_TTL` default `12h`
- `USER_TOKEN_TTL` default `4320h`
- `DEFAULT_LEASE_SECONDS` default `90`
- `MAX_POLL_LIMIT` default `20`
- `SCHEDULER_ENABLED` default `true`
- `SCHEDULER_INTERVAL` default `10s`
- `SCHEDULER_SCAN_LIMIT` default `500`
- `SCHEDULER_SLOT_TTL` default `90s`

## API prefix

All APIs are under `/api/v1`.

## Cloud task generation scheduler

- Built-in scheduler continuously scans active users and `user_task_configs`.
- `enabled === true` tasks are generated into `task_jobs` automatically.
- Redis schedule slot dedupe prevents duplicate enqueue in the same window.
- Open jobs (`pending/leased/running`) are checked before generating new jobs.
- Task due logic supports:
  - `next_time` full datetime
  - `next_time` daily `HH:MM`
  - no `next_time` fallback rolling generation with dedupe

Scheduler status endpoint:

- `GET /api/v1/scheduler/status`

## One-command deployment example

`docker-compose.yml` is provided for integrated deployment:

- URL: `http://localhost:7000` (frontend + backend in one container)
- Backend API: `http://localhost:7000/api/v1/*`
- Backend health check: `http://localhost:7000/health`
- Pull image from Docker Hub: `miku66/oasbackend`

```bash
cp .env.example .env
docker compose pull
docker compose up -d
```

## Production deployment stack

Production example with HTTPS + secrets + backup + monitoring:

- Compose file: `deploy/production/docker-compose.prod.yml`
- GitHub Actions image:
  - `miku66/oasbackend` (frontend + backend single image)
  - tags: `latest`, `sha-*`, `v*`
- Includes:
  - Caddy automatic HTTPS termination
  - Docker secrets-based credential injection
  - PostgreSQL backup service
  - Prometheus + Grafana + exporters monitoring stack
