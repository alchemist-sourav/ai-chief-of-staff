# Homingo AI – Personal Chief of Staff
**Track:** A3 – A Personal Staff for Everyone | **Hackathon:** Homingo Hack Days 2026

An AI-powered Chief of Staff that helps users organize their lives, manage everyday tasks, retain personal memory/preferences, and execute routine work with intelligent agent assistance and human-in-the-loop safety approvals.

---

## Current Status: Phase 2 Complete (Foundational Backend Architecture)

- **AI Engine:** Groq API using `openai/gpt-oss-120b` (configurable via `GROQ_MODEL`).
- **Backend Framework:** FastAPI (modular architecture with versioned `/api/v1` routers).
- **Database:** SQLAlchemy 2.0 async engine supporting PostgreSQL (`asyncpg`) and SQLite async (`aiosqlite`).
- **Core Entities:** `User`, `Conversation`, `Message`, `Task`, `UserMemory`.
- **Memory Service:** Structured context engine that stores personal preferences and injects relevant memories into the agent prompt.
- **Persistent Conversation:** Multi-turn conversational session history stored in the database.
- **Task Management:** Full CRUD task tracking with priority, status, and due dates.
- **Health Checks:** Comprehensive `/api/health` and `/api/v1/health` with live DB connectivity check (`SELECT 1`).
- **Automated Tests:** 100% passing test suite across models, services, memory, and endpoints.

---

## Architecture Layout

```
ai-chief-of-staff/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py              # Dependencies: get_db, get_current_user
│   │   │   └── v1/
│   │   │       ├── router.py        # Aggregated v1 API router
│   │   │       ├── health.py        # System & DB health checks
│   │   │       ├── ai.py            # AI verification & multi-turn chat
│   │   │       ├── conversations.py # Conversation threads & message history
│   │   │       ├── tasks.py         # Task CRUD endpoints
│   │   │       └── memory.py        # Personal memory vault endpoints
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic Settings
│   │   │   └── database.py          # SQLAlchemy 2.0 async engine & sessionmaker
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   │   ├── base.py              # DeclarativeBase, UUID generator, TimestampMixin
│   │   │   ├── user.py              # User model
│   │   │   ├── conversation.py      # Conversation session model
│   │   │   ├── message.py           # Multi-turn Message model
│   │   │   ├── task.py              # Task management model
│   │   │   └── memory.py            # Structured user memory model
│   │   ├── schemas/                 # Pydantic v2 schemas
│   │   └── services/                # Business logic services
│   │       ├── ai_service.py        # Modular Groq LLM client & chat orchestrator
│   │       ├── memory_service.py    # Memory retrieval & prompt formatting
│   │       ├── conversation_service.py # Message persistence & thread manager
│   │       └── task_service.py      # Task CRUD logic
│   ├── tests/                       # Automated pytest suite
│   ├── .env.example
│   ├── requirements.txt
│   └── verify_live_chat.py          # Live end-to-end verification script
```

---

## API Endpoints (v1)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | System health check (backward-compatible) |
| `POST` | `/api/ai/test` | Direct Groq test completion (backward-compatible) |
| `GET` | `/api/v1/health` | System and Database connectivity check |
| `POST` | `/api/v1/ai/chat` | Multi-turn conversational chat with memory injection & history persistence |
| `GET` | `/api/v1/conversations` | List user conversation threads |
| `GET` | `/api/v1/conversations/{id}/messages` | Get message history for a conversation |
| `GET` | `/api/v1/tasks` | List tasks (optional `status` and `priority` query filters) |
| `POST` | `/api/v1/tasks` | Create a new task |
| `GET` | `/api/v1/tasks/{id}` | Get single task details |
| `PATCH` | `/api/v1/tasks/{id}` | Update task details or status |
| `DELETE` | `/api/v1/tasks/{id}` | Delete task |
| `GET` | `/api/v1/memory` | List user memories and preferences |
| `POST` | `/api/v1/memory` | Create or update a personal preference/memory item |

---

## Quickstart & Local Setup

### 1. Environment Setup
```powershell
# Navigate to backend
cd backend

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Set your `GROQ_API_KEY`:
```ini
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=openai/gpt-oss-120b
DATABASE_URL=sqlite+aiosqlite:///./chief_of_staff.db
# Or PostgreSQL:
# DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/chief_of_staff
```

### 3. Run the Development Server
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Interactive API documentation will be available at: `http://127.0.0.1:8000/docs`

### 4. Run Automated Tests
```powershell
pytest tests -v
```

### 5. Run Live End-to-End Chat & Memory Verification
```powershell
python verify_live_chat.py
```
