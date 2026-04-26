# CollabMind

AI-powered team messaging platform built with FastAPI, PostgreSQL, Redis, and a local LLM copilot. Mirrors the architecture of Microsoft Teams AI Services.

![CI](https://github.com/akshata1710/collabmind/actions/workflows/ci.yml/badge.svg)

---

## What it does

CollabMind is a real-time team chat backend with an AI copilot layer. Users can send messages, reply in threads, and get AI-powered summaries, smart reply suggestions, and urgency classification — all running on a free local LLM.

**Core features:**
- Real-time messaging via WebSockets with Redis Pub/Sub fan-out
- Threaded conversations via self-referential `reply_to_id` foreign key
- JWT authentication with bcrypt password hashing
- Live presence tracking (online/away/offline) with Redis TTL keys
- AI Copilot: thread summarizer, smart replies, message classifier
- LLM evaluation suite measuring F1 score, latency (p50/p99), and faithfulness
- Separate notification microservice subscribing to Redis events
- GitHub Actions CI running 8 automated tests on every push

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         DOCKER COMPOSE           │
                    │                                  │
  Browser/curl ───► │  FastAPI (port 8000)             │
                    │  ├── /auth      JWT login        │
                    │  ├── /channels  chat rooms       │
                    │  ├── /messages  send + threads   │
                    │  ├── /ws        WebSocket        │
                    │  ├── /presence  online status    │
                    │  ├── /ai        AI copilot       │
                    │  └── /eval      LLM eval suite   │
                    │         │              │         │
                    │         ▼              ▼         │
                    │   PostgreSQL        Redis        │
                    │   (messages,     (pub/sub,       │
                    │    users,         presence,      │
                    │    channels)      TTL cache)     │
                    │                                  │
                    │  Notification worker             │
                    │  (subscribes to Redis,           │
                    │   processes async events)        │
                    └─────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │         YOUR MACHINE             │
                    │  Ollama (port 11434)             │
                    │  └── Llama 3.2 (3.2B, free)     │
                    └─────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI + Uvicorn |
| Database | PostgreSQL 16 via SQLAlchemy (async) |
| Cache / Pub-Sub | Redis 7 |
| Real-time | WebSockets |
| Auth | JWT + bcrypt |
| AI runtime | Ollama (Llama 3.2, 3.2B) |
| Containers | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Testing | pytest + pytest-asyncio |

---

## Quick start

### Prerequisites
- Docker Desktop running
- Ollama installed (`brew install ollama`) with Llama 3.2 (`ollama pull llama3.2`)

### Run the full stack
```bash
git clone https://github.com/akshata1710/collabmind.git
cd collabmind
docker compose up --build
```

Wait for:
```
api-1           | Application startup complete.
notification-1  | subscribed to chat:* — listening for messages
```

Open the interactive API docs at **http://localhost:8000/docs**

### Run tests locally
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

Expected output:
```
PASSED tests/test_chat.py::test_register
PASSED tests/test_chat.py::test_duplicate_register
PASSED tests/test_chat.py::test_login_success
PASSED tests/test_chat.py::test_login_wrong_password
PASSED tests/test_chat.py::test_create_channel
PASSED tests/test_chat.py::test_list_channels
PASSED tests/test_chat.py::test_send_message
PASSED tests/test_chat.py::test_threaded_reply
8 passed
```

---

## API reference

### Auth
```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"secret"}'

# Login — returns JWT token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice&password=secret"
```

### Messaging
```bash
# Create channel
curl -X POST http://localhost:8000/channels/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"engineering"}'

# Send message
curl -X POST http://localhost:8000/messages/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Deploy is failing on step 3","channel_id":1}'

# Reply in thread
curl -X POST http://localhost:8000/messages/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Looking into it now","channel_id":1,"reply_to_id":1}'

# Fetch thread
curl http://localhost:8000/messages/thread/1 \
  -H "Authorization: Bearer $TOKEN"
```

### Real-time WebSocket
```
ws://localhost:8000/ws/{channel_id}?token=<jwt>
```
Send: `{"content": "hello", "reply_to_id": null}`  
Receive: full message JSON broadcast to all connected clients in the channel.

### Presence
```bash
# Set status
curl -X PUT "http://localhost:8000/presence/status?status=online" \
  -H "Authorization: Bearer $TOKEN"

# Check status for users
curl "http://localhost:8000/presence/?user_ids=1&user_ids=2" \
  -H "Authorization: Bearer $TOKEN"
# Returns: {"1": "online", "2": "offline"}
```

### AI Copilot
```bash
# Classify message urgency, intent, sentiment
curl -X POST http://localhost:8000/ai/classify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message_id": 1}'
# Returns: {"urgency":"high","intent":"escalation","sentiment":"negative"}

# Summarize a thread
curl -X POST http://localhost:8000/ai/summarize \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"thread_id": 1}'
# Returns: {"summary": "The deploy pipeline failed on step 3..."}

# Get smart reply suggestions
curl -X POST http://localhost:8000/ai/reply \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message_id": 1}'
# Returns: {"suggestions": ["I can take a look", "Which step failed?", "Rolling back now"]}
```

---

## LLM Evaluation suite

Run the eval suite locally (requires Ollama running):
```bash
python run_eval.py
```

Sample results:
```
Classification urgency F1:   1.000
Classification intent F1:    0.567
Classification sentiment F1: 0.508
Summarization concept hit:   1.000
Summarization faithfulness:  0.313
Classify latency p50/p99:    0.66s / 0.76s
Summarize latency p50/p99:   0.92s / 1.05s
Overall: PASS ✓
```

The eval suite measures:
- **F1 score** per classification field against a 8-case golden dataset
- **Faithfulness** — fraction of summary words grounded in source messages (hallucination proxy)
- **Concept hit rate** — whether key facts from source appear in summary
- **Latency percentiles** — p50, p95, p99 per endpoint
- Results saved as timestamped JSON in `eval_results/` for regression tracking

---

## Project structure

```
collabmind/
├── app/
│   ├── main.py                   # FastAPI app entry point
│   ├── core/
│   │   ├── config.py             # Pydantic settings
│   │   ├── security.py           # JWT + bcrypt
│   │   ├── websocket_manager.py  # In-memory WS rooms (Week 2)
│   │   └── redis_manager.py      # Redis pub/sub + presence (Week 3)
│   ├── db/
│   │   └── session.py            # Async SQLAlchemy engine
│   ├── models/
│   │   ├── user.py
│   │   ├── channel.py
│   │   └── message.py            # reply_to_id threading
│   ├── schemas/
│   │   └── schemas.py            # Pydantic v2 models
│   ├── routers/
│   │   ├── auth.py
│   │   ├── channels.py
│   │   ├── messages.py
│   │   ├── websocket.py
│   │   ├── presence.py
│   │   ├── ai.py                 # AI copilot endpoints
│   │   └── eval.py               # Eval trigger + report
│   └── services/
│       ├── ai_copilot.py         # Ollama LLM calls
│       ├── evaluator.py          # F1, latency, faithfulness
│       └── notification_worker.py # Redis subscriber microservice
├── tests/
│   └── test_chat.py              # 8 automated tests
├── .github/
│   └── workflows/
│       └── ci.yml                # GitHub Actions CI
├── docker-compose.yml            # 4 services: db, redis, api, notification
├── Dockerfile
├── run_eval.py                   # Local eval runner
└── requirements.txt
```

---

## Key design decisions

**Why Redis Pub/Sub for WebSockets?**  
The in-memory `ConnectionManager` breaks when running multiple API server instances — Server 1 can't reach WebSocket clients connected to Server 2. Redis Pub/Sub acts as a shared broadcast channel so all servers receive every message and deliver it to their local connections. This enables horizontal scaling.

**Why self-referential FK for threading?**  
`reply_to_id` points to another row in the same `messages` table. A null value means top-level message; a set value creates a reply. `GET /thread/{id}` fetches root + children in two queries — no recursion needed since threads are one level deep, matching the Teams model.

**Why TTL for presence?**  
Redis keys with a 30-second TTL expire automatically when a client disconnects or goes silent. No cleanup job needed. The client sends a heartbeat every 25 seconds to keep the key alive while active.

**Why local Ollama over OpenAI API?**  
Zero cost, no rate limits, no data leaving your machine. Llama 3.2 (3.2B parameters) is fast enough for sub-second classification and under 1 second summarization on Apple Silicon.

---

## CI/CD

Every push to `main` triggers GitHub Actions which:
1. Spins up a clean Ubuntu environment
2. Installs Python 3.12 and all dependencies
3. Runs the full test suite with pytest
4. Reports pass/fail per test

Green badge = all 8 tests passing on every commit.
