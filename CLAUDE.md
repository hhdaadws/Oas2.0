# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Environment Setup
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
venv/bin/pip install fastapi uvicorn pydantic pydantic-settings sqlalchemy alembic apscheduler loguru tenacity opencv-python numpy paddleocr
```

### Running the Application
```bash
# Start the FastAPI server with Uvicorn
PYTHONPATH=src venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9001

# Run with reload for development
PYTHONPATH=src venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 9001
```

### Database Migrations
```bash
# Windows
powershell -ExecutionPolicy Bypass -File scripts/migrate.ps1

# Linux/Mac
bash scripts/migrate

# Using Alembic directly
alembic upgrade head
```

### Testing
```bash
# Run tests with pytest
venv/bin/pytest

# Run with coverage
venv/bin/pytest --cov=src --cov-report=html
```

## Architecture Overview

This is an automation system for the Onmyoji mobile game, designed to manage multiple accounts across different servers with various automated tasks.

### Core System Components

1. **Emulator Integration (MuMu)**
   - Controls MuMu emulator instances via ADB commands
   - Handles multiple emulator instances for parallel execution
   - ADB operations: screenshot capture, tap, swipe, app management

2. **Vision and OCR System**
   - PaddleOCR for Chinese text recognition with ROI optimization
   - OpenCV for template matching and UI element detection
   - Screenshot pipeline optimized for performance

3. **Task Scheduling System**
   - APScheduler for time-based triggers (e.g., every 6 hours)
   - Priority queue for condition-based triggers (e.g., stamina > 1000)
   - Task state machine: pending → running → (succeeded|failed|skipped)

4. **Account Management**
   - Email accounts can have up to 4 game accounts (different servers)
   - Game accounts track: zone, level, stamina, coins, progress state
   - Account initialization handled by executor after email registration

5. **Worker/Executor System**
   - Workers bind to emulators and execute tasks
   - Role-based workers: general, coop (cooperation), init (initialization)
   - Push-based task distribution with concurrency control

### Key Data Models

- **Email**: Primary email accounts
- **GameAccount**: Game accounts (4 per email max), linked via email_fk
- **Task**: Scheduled/conditional tasks with priority and retry logic
- **Worker**: Execution units bound to emulators
- **CoopPool**: Cooperation task pool management
- **TaskRun**: Execution history and artifacts

### Task Types (Plugins)

- Account initialization (起号)
- Foster/Collection (寄养)
- Exploration/Breakthrough (探索/结界突破)
- Card synthesis (结界卡合成)
- Delegation (委托/弥助)
- Cooperation (勾协)
- Friend management (加好友)
- Rest periods (休息策略)

### Important Configuration

Environment variables (.env):
- `DATABASE_URL`: Database connection (default: sqlite:///./data.db)
- `PADDLE_OCR_LANG`: OCR language (ch for Chinese)
- `MUMU_MANAGER_PATH`: Path to MuMu manager executable
- `ADB_PATH`: Path to ADB executable
- `PKG_NAME`: Game package name (com.netease.onmyoji)
- `COOP_TIMES`: Cooperation schedule times (e.g., "18:00,21:00")
- `STAMINA_THRESHOLD`: Stamina threshold for triggers (default: 1000)

### Project Structure (Planned)

```
src/
  app/
    core/            # Configuration, logging, constants
    db/              # ORM models, sessions, migrations
    modules/
      accounts/      # Account service
      tasks/         # Scheduler and queue
      executor/      # Execution engine
      emu/           # MuMu adapter
      vision/        # OpenCV template matching
      ocr/           # PaddleOCR wrapper
      coop/          # Cooperation logic
      web/           # FastAPI routes
    plugins/tasks/   # Task implementations
```

## Important Notes

- The system uses a "big executor" pattern where the scheduler dispatches tasks to workers
- Account creation is lazy - game accounts are created only after successful initialization
- Cooperation tasks have special timing constraints (T-10 minutes before scheduled time)
- Rest strategy includes fixed 0-6 AM sleep plus 2-3 hour random breaks during the day
- All tasks should be idempotent with proper retry and backoff strategies