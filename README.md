# 🤖 Autonomous Agent Hub

A production-grade, distributed AI Agent Management Hub and Model Context Protocol (MCP) Orchestration Platform built with **Python**, **FastAPI**, **SQLite (SQLAlchemy 2.0)**, **Google Gemini LLM**, and a modern **Tailwind CSS Web Dashboard**.

---

## 🚀 Key Features

- **Autonomous Agent Fleet Management**: Visually deploy, configure, inspect, and toggle AI agents with custom personas, cognitive constraints, and behavioral instructions.
- **Model Context Protocol (MCP) Tool Endpoints**: Seamlessly connect remote SSE/HTTP tool endpoints (e.g., WhatsApp MCP, CAD Mesh Engine, ERP Sync, GitHub MCP) to individual agents.
- **Interactive Live Chat & Testing Drawer**: Test agent responses in real time with system prompt injection, tool awareness context, and streaming task logs.
- **Comprehensive Task History**: Every user directive and agent reasoning cycle is persisted to SQLite with status indicators.
- **Modern Dark UI/UX**: Crafted with a sleek Slate/Zinc theme, Lucide icons, glassmorphism cards, responsive slide-overs, and quick preset templates.

---

## 🏗️ Repository Architecture

```text
agent_hub/
├── app/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # Reads GEMINI_API_KEY, PORT, ENV variables via pydantic-settings
│   │   └── database.py           # SQLite engine, sessionmaker, Base class
│   ├── models/
│   │   ├── __init__.py
│   │   ├── agent.py              # Agent and AgentSkill SQLAlchemy models
│   │   └── task_log.py           # Execution / Chat task history model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── agent.py              # Pydantic schemas for Agent & Skills (Create, Update, Out)
│   │   └── chat.py               # Chat test request and response schemas
│   ├── services/
│   │   ├── __init__.py
│   │   └── llm_service.py        # Gemini client interaction with system instructions & persona injection
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── agents.py             # REST API routes for agents and skills
│   │   └── web.py                # Jinja2 template renderer for the web dashboard (GET /)
│   ├── templates/
│   │   └── index.html            # Complete Tailwind CSS Web Dashboard
│   ├── static/
│   │   ├── css/
│   │   │   └── custom.css        # Minimal animations, glassmorphism, scrollbars
│   │   └── js/
│   │       └── app.js            # Vanilla JS fetching API endpoints, modal management, live chat UI
│   ├── __init__.py
│   └── main.py                   # FastAPI initialization, CORS, StaticFiles, Routers mounting
├── .env.example                  # Environment configuration template
├── requirements.txt              # Production dependencies
└── README.md
```

---

## 🛠️ Quick Start & Setup

### 1. Clone & Setup Virtual Environment

```bash
# Navigate to project directory
cd agent_hub

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Windows (Command Prompt):
.\venv\Scripts\activate.bat
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
PORT=8000
ENV=development
DATABASE_URL=sqlite:///./agent_hub.db
```

> **Note:** If `GEMINI_API_KEY` is omitted or left empty, the application runs seamlessly in **Sandbox Autonomous Simulation Mode**, allowing full UI and API testing with simulated agent cognition.

### 4. Run the Application

```bash
uvicorn app.main:app --reload --port 8000
```

Open your browser and navigate to:
- 🌐 **Web Dashboard:** [http://localhost:8000/](http://localhost:8000/)
- 📖 **Interactive API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- 📊 **ReDoc Documentation:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📡 REST API Reference

### Agents Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/agents/` | List all agents with nested skills and log count |
| `POST` | `/api/agents/` | Register and deploy a new autonomous agent |
| `GET` | `/api/agents/{id}` | Retrieve specific agent details |
| `PUT` | `/api/agents/{id}` | Update agent details (name, role, prompt, status) |
| `DELETE` | `/api/agents/{id}` | Delete agent and cascade delete attached skills/logs |

### MCP Skills Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agents/{id}/skills` | Attach remote MCP tool endpoint (SSE/HTTP) |
| `DELETE` | `/api/agents/{id}/skills/{skill_id}` | Detach MCP skill from agent |
| `PATCH` | `/api/agents/{id}/skills/{skill_id}/toggle` | Toggle enabled status of a skill |

### Chat & Testing Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agents/{id}/chat` | Send test directive to agent with persona & tool injection |
| `GET` | `/api/agents/{id}/logs` | Fetch conversation and execution task logs |

---

## 🧪 Database Schema

- **`agents`**: Stores UUID, name, role, avatar color badge, system prompt, active status, and timestamps.
- **`agent_skills`**: Foreign key to `agents.id`, stores skill name, remote endpoint URL (SSE/REST), and enabled state.
- **`task_logs`**: Foreign key to `agents.id`, stores prompt inputs, LLM outputs, execution status, and timestamps.
