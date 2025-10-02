# AI Voice Agent Tool

A complete voice agent system for dispatch calls with Retell AI integration, featuring both regular check-ins and emergency protocols.

## Features

- **Voice Agent Calls**: Automated dispatch calls using Retell AI
- **Two Scenarios**: Regular logistics check-ins and emergency protocols
- **Real-time Processing**: WebSocket-based custom LLM integration
- **Admin Dashboard**: React frontend for call management and agent configuration
- **Database Integration**: Supabase for call history and agent configs
- **Cloudflare Tunnel**: Secure public access for webhooks

## Quick Start

### 1. Environment Setup

Create `.env` files for both frontend and backend:

**Backend `.env`** (in `backend/` directory):
```env
# Supabase Configuration
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Retell AI Configuration
RETELL_API_KEY=your_retell_api_key
RETELL_FROM_NUMBER=+1234567890
RETELL_AGENT_ID=your_retell_agent_id
RETELL_WEBHOOK_SECRET=your_webhook_secret

# LLM Configuration (choose one)
GROQ_API_KEY=your_groq_api_key
# OR
OPENAI_API_KEY=your_openai_api_key

# Backend URL (update after setting up Cloudflare tunnel)
BACKEND_URL=https://your-tunnel-url.trycloudflare.com

# Slot Memory Configuration (optional)
SLOT_HEURISTICS_ENABLED=false
SLOT_TEXT_TEMPLATES_ENABLED=false
```

**Frontend `.env`** (in `frontend/` directory):
```env
VITE_API_BASE_URL=http://localhost:8000
```

### 2. Database Setup (Supabase)

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Get your project URL and service role key from Settings > API
3. Create the following tables in SQL Editor:

```sql
-- Agent configurations
CREATE TABLE agent_configs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    prompt_template TEXT NOT NULL,
    voice_settings JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Call records
CREATE TABLE calls (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    driver_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    load_number TEXT,
    agent_config_id UUID REFERENCES agent_configs(id),
    status TEXT DEFAULT 'queued',
    retell_call_id TEXT,
    escalation_status TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Call transcripts
CREATE TABLE call_transcripts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    call_id UUID REFERENCES calls(id) ON DELETE CASCADE,
    segment_text TEXT NOT NULL,
    speaker TEXT NOT NULL,
    timestamp TEXT,
    confidence FLOAT DEFAULT 1.0,
    is_final BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Call summaries
CREATE TABLE call_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    call_id UUID REFERENCES calls(id) ON DELETE CASCADE,
    summary JSONB NOT NULL,
    summary_version TEXT DEFAULT 'v1',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 3. Backend Setup

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 5. Cloudflare Tunnel Setup

1. Download Cloudflare Tunnel: [Download cloudflared](https://github.com/cloudflare/cloudflared/releases)
2. Login to Cloudflare:
   ```bash
   cloudflared tunnel login
   ```
3. Create a tunnel:
   ```bash
   cloudflared tunnel create ai-voice-agent
   ```
4. Configure tunnel (create `config.yml`):
   ```yaml
   tunnel: ai-voice-agent
   credentials-file: C:\Users\YourUser\.cloudflared\ai-voice-agent.json
   
   ingress:
     - hostname: your-domain.trycloudflare.com
       service: http://localhost:8000
     - service: http_status:404
   ```
5. Run tunnel:
   ```bash
   cloudflared tunnel run ai-voice-agent
   ```
6. Update `BACKEND_URL` in your `.env` with the tunnel URL

### 6. Retell AI Configuration

1. Create account at [retellai.com](https://retellai.com)
2. Get your API key from dashboard
3. Update webhook URLs in Retell dashboard:
   - **Webhook URL**: `https://your-tunnel-url.trycloudflare.com/api/retell/webhook`
   - **Custom LLM WebSocket**: `wss://your-tunnel-url.trycloudflare.com/api/llm/retell/custom-llm/{call_id}`

### 7. Twilio Phone Number Setup

1. Create Twilio account at [twilio.com](https://twilio.com)
2. Buy a phone number from Twilio Console
3. Configure SIP Trunking in Retell AI:
   - Go to Retell AI > Settings > Phone Numbers
   - Add your Twilio number
   - Configure SIP trunking settings

## Usage

### Starting the Application

1. **Backend**: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
2. **Frontend**: `npm run dev`
3. **Tunnel**: `cloudflared tunnel run ai-voice-agent`

### Making Test Calls

1. Open the admin dashboard at `http://localhost:5173`
2. Go to "Call Triggering"
3. Enter driver details and phone number
4. Click "Trigger Call"

### Call Scenarios

**Regular Check-in**:
- Agent asks for status (Driving/Delayed/Arrived)
- Collects current location
- Gets ETA
- Confirms and ends call

**Emergency Protocol**:
- Detects emergency keywords (accident, blowout, medical, etc.)
- Asks for emergency type, location, and injuries
- Escalates to human dispatcher
- Ends call with escalation flag

## API Endpoints

- `GET /api/calls` - List all calls
- `POST /api/calls/trigger` - Trigger a new call
- `GET /api/calls/{call_id}` - Get call details
- `POST /api/retell/webhook` - Retell webhook endpoint
- `WS /api/llm/retell/custom-llm/{call_id}` - Custom LLM WebSocket

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Yes |
| `RETELL_API_KEY` | Retell AI API key | Yes |
| `RETELL_FROM_NUMBER` | Twilio phone number | Yes |
| `GROQ_API_KEY` | Groq API key (free) | Yes* |
| `OPENAI_API_KEY` | OpenAI API key | Yes* |
| `BACKEND_URL` | Public backend URL | Yes |
| `SLOT_HEURISTICS_ENABLED` | Enable slot extraction | No (default: true) |
| `SLOT_TEXT_TEMPLATES_ENABLED` | Enable templated responses | No (default: true) |

*Use either Groq or OpenAI API key

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**: Check Cloudflare tunnel is running and URL is correct
2. **Database Connection Error**: Verify Supabase credentials and table structure
3. **Call Not Triggering**: Check Retell API key and phone number configuration
4. **Agent Not Responding**: Verify LLM API key and webhook URLs

### Logs

- Backend logs: Check terminal where uvicorn is running
- Frontend logs: Check browser console
- Tunnel logs: Check cloudflared output

## Project Structure

```
ai-voice-agent-tool/
├── backend/
│   ├── app/
│   │   ├── api/           # API endpoints
│   │   ├── services/      # Business logic
│   │   ├── models/        # Database models
│   │   └── schemas/       # Pydantic schemas
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── pages/         # Page components
│   │   └── api/           # API client
│   ├── package.json
│   └── Dockerfile
└── README.md
```

## License

MIT License - see LICENSE file for details