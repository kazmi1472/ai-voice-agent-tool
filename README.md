# AI Voice Agent Tool — Setup Guide

This document provides simple instructions to set up and run the AI Voice Agent Tool. The app lets you configure an AI voice agent, trigger calls, and review transcripts with structured summaries.

Tech: React (frontend), FastAPI (backend), Supabase (database), Retell AI (voice), OpenAI (LLM).

## 1) Clone the Repository
```
git clone <your-repo-url>
cd ai-voice-agent-tool
```

## 2) Run the Backend
```
cd backend
python -m venv .venv
./.venv/Scripts/activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 3) Run the Frontend
```
cd ../frontend
npm install
npm run dev
# open http://localhost:5173
```

## 4) Database Setup (Supabase) — Optional
To persist data, create these tables in Supabase:
```
CREATE TABLE agent_configs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text,
  prompt_template text NOT NULL,
  voice_settings jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_name text NOT NULL,
  phone_number text NOT NULL,
  load_number text,
  agent_config_id uuid REFERENCES agent_configs(id) ON DELETE SET NULL,
  status text CHECK (status IN ('queued','in_progress','completed','failed','processed')) DEFAULT 'queued',
  started_at timestamptz,
  ended_at timestamptz,
  duration_seconds int,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE call_transcripts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id uuid REFERENCES calls(id) ON DELETE CASCADE,
  segment_text text,
  speaker text,
  timestamp timestamptz,
  confidence float,
  is_final boolean DEFAULT true
);

CREATE TABLE call_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id uuid REFERENCES calls(id) ON DELETE CASCADE,
  summary jsonb,
  summary_version text,
  created_at timestamptz DEFAULT now()
);
```
Then set in `backend/.env`:
```
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```
Restart backend.

## 5) Real Calls with Retell — Optional
1. Add your keys to `backend/.env`:
```
RETELL_API_KEY=...
OPENAI_API_KEY=...
SIMULATE_RETELL=false
BACKEND_URL=https://<ngrok-url>
RETELL_WEBHOOK_SECRET=     # optional; leave empty for demo
```
2. Expose backend: `ngrok http 8000`
3. In Retell, set webhook: `https://<ngrok-url>/api/retell/webhook`
4. Restart backend and trigger calls from the UI.

Notes:
- Env files are ignored by Git. Keep keys only in `backend/.env`.
- For a guaranteed demo without phone calls, use the UI’s “Use local simulation” option.

## Security Notice
- DO NOT expose Retell or OpenAI API keys in frontend or in repository history.
- Keep RETELL_API_KEY, OPENAI_API_KEY, and Supabase keys in server-side environment only.
- See env/.env.example for required variables.

## Supabase Setup
1) Create a Supabase project.
2) In SQL editor, run the schema from backend/app/models/db_models.py (or copy the SQL below):

```sql
CREATE TABLE agent_configs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text,
  prompt_template text NOT NULL,
  voice_settings jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_name text NOT NULL,
  phone_number text NOT NULL,
  load_number text,
  agent_config_id uuid REFERENCES agent_configs(id) ON DELETE SET NULL,
  status text CHECK (status IN ('queued','in_progress','completed','failed','processed')) DEFAULT 'queued',
  started_at timestamptz,
  ended_at timestamptz,
  duration_seconds int,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE call_transcripts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id uuid REFERENCES calls(id) ON DELETE CASCADE,
  segment_text text,
  speaker text,
  timestamp timestamptz,
  confidence float,
  is_final boolean DEFAULT true
);

CREATE TABLE call_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id uuid REFERENCES calls(id) ON DELETE CASCADE,
  summary jsonb,
  summary_version text,
  created_at timestamptz DEFAULT now()
);
```

## Environment Variables
Copy env/.env.example to backend/.env (and optionally root .env for compose) and set values:

```env
# Supabase
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=

# OpenAI
OPENAI_API_KEY=

# Retell (server only)
RETELL_API_KEY=
RETELL_WEBHOOK_SECRET=

# App
FASTAPI_SECRET_KEY=
DATABASE_URL=

# Deployment
SENTRY_DSN=

# Local simulation
SIMULATE_RETELL=true
```

## Running Locally (Docker Compose)
```bash
docker-compose up --build
```
Frontend: http://localhost:5173  Backend: http://localhost:8000

## Running Locally (No Docker)
Backend
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Frontend
```bash
cd frontend
npm install
npm run dev -- --host
```

## API Endpoints (summary)
- GET /api/agent-configs, POST /api/agent-configs, PUT /api/agent-configs/{id}, DELETE /api/agent-configs/{id}
- POST /api/calls/start?mode=local
- GET /api/calls, GET /api/calls/{call_id}, POST /api/calls/{call_id}/process
- POST /api/retell/webhook

## Curl Examples
Trigger call
```bash
curl -X POST http://localhost:8000/api/calls/start \
  -H "Content-Type: application/json" \
  -d '{"driver_name":"Mike","phone_number":"+15551234567","load_number":"7891-B","agent_config_id":"00000000-0000-0000-0000-000000000000"}'
```

Webhook simulation
```bash
curl -X POST http://localhost:8000/api/retell/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event_type":"speech",
    "call_id":"<call_id>",
    "timestamp":"2025-09-24T12:34:56Z",
    "payload":{"speech_text":"I just had a blowout on I-15 North mile 123","stable":true,"confidence":0.92,"speaker":"driver"}
  }'
```

## Tests
```bash
cd backend
pytest -q
```

## Retell Webhook
Configure Retell to POST to: https://<backend>/api/retell/webhook
Validate signatures with RETELL_WEBHOOK_SECRET.

## Security
- RETELL API: DO NOT EXPOSE OR YOUR CANDIDACY WILL NOT BE CONSIDERED.
- Never commit RETELL_API_KEY or OPENAI_API_KEY. Frontend build includes guard to prevent bundling these names.

## 🎯 Implemented Scenarios

### Scenario 1: Driver Check-in ("Dispatch")
- Agent calls driver (e.g., Mike, Load #7891-B) for status update
- Dynamically adapts follow-up questions based on driver response
- **Structured Summary Fields**:
  - `call_outcome`: "In-Transit Update" or "Arrival Confirmation"
  - `driver_status`: "Driving", "Delayed", or "Arrived"
  - `current_location`: "I-10 near Indio, CA"
  - `eta`: "Tomorrow, 8:00 AM"

### Scenario 2: Emergency Protocol ("Dispatch")
- During routine call, driver reports emergency (e.g., "I just had a blowout")
- Agent immediately switches to emergency protocol
- Gathers critical details and escalates to human dispatcher
- **Structured Summary Fields**:
  - `call_outcome`: "Emergency Detected"
  - `emergency_type`: "Accident", "Breakdown", "Medical", or "Other"
  - `emergency_location`: "I-15 North, Mile Marker 123"
  - `escalation_status`: "Escalation Flagged"

### Dynamic Response Handling
- **Uncooperative Driver**: Probes for more info after one-word answers; ends call if still unresponsive
- **Noisy Environment**: Asks driver to repeat limited times; ends call gracefully if still unclear

## 🚀 Quick Start

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed setup instructions.

### Prerequisites
- Node.js (v16+)
- Python 3.8+
- Supabase account
- OpenAI API key
- Retell AI API key (optional for local development)

### Quick Setup
```bash
# Clone and setup
git clone <your-repo-url>
cd ai-voice-agent-tool

# Install dependencies
cd backend && pip install -r requirements.txt
cd ../frontend && npm install

# Configure environment (see SETUP_GUIDE.md)
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

# Run the application
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend  
cd frontend && npm run dev
```

Access the application at http://localhost:5173

## Demo
See demo/demo_script.md and docs/how_to_record_demo.md for a 45–120s walkthrough.
