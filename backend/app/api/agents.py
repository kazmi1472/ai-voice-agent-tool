from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from ..db import get_db
from ..services.retell_client import RetellClient
import os


router = APIRouter()


class AgentFromTaskRequest(BaseModel):
    task_description: str
    name: Optional[str] = None
    description: Optional[str] = None
    prompt_template: Optional[str] = None
    voice_settings: Optional[Dict[str, Any]] = None
    # Optional immediate outbound test call
    start_test_call: Optional[bool] = False
    driver_name: Optional[str] = None
    phone_number: Optional[str] = None
    load_number: Optional[str] = None


@router.post("/from-task")
async def create_agent_from_task(body: AgentFromTaskRequest):
    db = get_db()

    # Use values provided by the app; only fall back to a minimal default
    name = body.name or "Dispatch Voice Agent"
    description = body.description or body.task_description[:140]
    prompt_template = body.prompt_template or (
        "You are a calm, professional, human-sounding dispatch agent calling {driver_name} about load {load_number}.\n"
        "Speak naturally in short turns. Briefly acknowledge (\\\"okay\\\", \\\"got it\\\") then move forward. Never repeat the same sentence twice.\n\n"
        "Goals to fill (one-by-one, acknowledge once each):\n"
        "- driver_status: Driving | Delayed | Arrived\n"
        "- current_location: concise city/road/landmark (e.g., \\\"I-10 near Indio, CA\\\")\n"
        "- eta: concise time (e.g., \\\"Today 5 PM\\\", \\\"12:30\\\", \\\"in 2 hours\\\")\n\n"
        "Conversation rules:\n"
        "- One short sentence or question per turn; never ask two things at once.\n"
        "- Use call_history to avoid re-asking what’s already given.\n"
        "- If the driver gives partial info, briefly acknowledge it and ask for the next missing item.\n"
        "- If unclear: rephrase once; if still unclear after 2 tries, move on to the next missing item or close politely.\n"
        "- If interrupted, adapt to what they said.\n\n"
        "Emergency protocol (accident/blowout/crash/medical/emergency):\n"
        "- Immediately switch to: emergency_type → emergency_location (specific) → any injuries (yes/no).\n"
        "- Say: \\\"A human dispatcher will call you back immediately.\\\" Then end.\n\n"
        "Opening line (first turn only):\n"
        "\\\"Hi {driver_name}, this is Dispatch regarding load {load_number}. Can you give me an update on your status?\\\"\n\n"
        "Ending lines (when all info collected):\n"
        "1. Confirmation: \\\"Just to confirm, we have your status, location, and ETA — is that correct?\\\"\n"
        "2. If yes: \\\"Thanks for the update. Drive safe.\\\"\n"
        "3. If no: \\\"No problem. What's your current status?\\\" (then re-collect)\n"
        "4. If driver says \\\"arrived\\\": \\\"Thanks for confirming arrival. Have a great day.\\\"\n"
        "5. If driver says \\\"bye/goodbye\\\": \\\"Thanks for the update. Take care.\\\"\n\n"
        "Context:\n"
        "- driver_name: {driver_name}\n"
        "- load_number: {load_number}\n"
        "- call_history (recent): {call_history}\n\n"
        "Output (STRICT JSON):\n"
        "{\n  \\\"agent_text\\\": \\\"<one short, natural sentence you will speak next>\\\",\n  \\\"action\\\": \\\"ask_followup\\\" | \\\"end_call\\\" | \\\"escalate\\\"\n}\n\n"
        "Action policy:\n"
        "- Use \\\"ask_followup\\\" while collecting status, location, eta.\n"
        "- After the single yes/no confirmation and a brief closing line, set \\\"end_call\\\".\n"
        "- If emergency protocol completes (and you said the dispatcher line), set \\\"escalate\\\".\n\n"
        "Examples:\n"
        "- Opening: \\\"Hi Mike, this is Dispatch regarding load #7891-B. Can you give me an update on your status?\\\"\n"
        "- Follow-up: \\\"Got it. Where are you right now?\\\"\n"
        "- Confirmation: \\\"Just to confirm, we have your status, location, and ETA — is that correct?\\\"\n"
        "- Closing: \\\"Thanks for the update. Drive safe.\\\""
    )
    voice_settings = body.voice_settings or {
        "voice_id": "sarah",
        "advanced_settings": {
            "backchanneling": True,
            "filler_words_allowed": False,
            "interruption_sensitivity": "medium",
        },
    }

    created = db.create_agent_config(type("Obj", (), {  # simple dot-access shim
        "name": name,
        "description": description,
        "prompt_template": prompt_template,
        "voice_settings": voice_settings,
    }))

    # Create a Retell agent now and store its id back into this config's voice_settings
    rc = RetellClient()
    retell = await rc.create_or_update_agent(name=name, prompt_template=prompt_template, voice_settings=voice_settings)
    retell_agent_id = retell.get("agent_id") or retell.get("id")
    if retell_agent_id:
        # merge back into DB config
        vs = dict(created.get("voice_settings") or {})
        vs["retell_agent_id"] = retell_agent_id
        _ = db.update_agent_config(created["id"], type("Obj", (), {"voice_settings": vs}))
        created["voice_settings"] = vs
        # Auto-assign phone number to this agent for outbound
        from_number = os.getenv("RETELL_FROM_NUMBER")
        if from_number:
            try:
                await rc.assign_number_to_agent(from_number=from_number, agent_id=retell_agent_id)
            except Exception:
                pass

    # Optionally kick off a test outbound call using this config
    if body.start_test_call and body.phone_number:
        call_payload = type("Obj", (), {
            "driver_name": body.driver_name or "Test Driver",
            "phone_number": body.phone_number,
            "load_number": body.load_number or "TEST-LOAD",
            "agent_config_id": created["id"],
        })
        call = db.create_call(call_payload)
        rc = RetellClient()
        cfg = db.get_agent_config(created["id"]) or {}
        vs = cfg.get("voice_settings") or {}
        agent_cfg: Dict[str, Any] = {"voice_settings": vs}
        if vs.get("retell_agent_id"):
            agent_cfg["agent_id"] = vs.get("retell_agent_id")
        await rc.initiate_call(call_id=str(call["id"]), phone_number=call_payload.phone_number, agent_config=agent_cfg)
        return {"agent_config": created, "test_call": {"call_id": call["id"], "status": "queued"}}

    return created


class AgentSyncRequest(BaseModel):
    agent_config_id: str


@router.post("/sync-retell")
async def sync_agent_to_retell(body: AgentSyncRequest):
    db = get_db()
    cfg = db.get_agent_config(body.agent_config_id)
    if not cfg:
        return {"error": "agent_config not found"}
    rc = RetellClient()
    vs = cfg.get("voice_settings") or {}
    retell_agent_id = vs.get("retell_agent_id") or vs.get("agent_id")
    created = await rc.create_or_update_agent(
        name=cfg.get("name"),
        prompt_template=cfg.get("prompt_template"),
        voice_settings=vs,
        agent_id=retell_agent_id,
    )
    rid = created.get("agent_id") or created.get("id")
    if rid and rid != retell_agent_id:
        vs["retell_agent_id"] = rid
        db.update_agent_config(body.agent_config_id, type("Obj", (), {"voice_settings": vs}))
    # Assign number after ensure we have agent id
    from_number = os.getenv("RETELL_FROM_NUMBER")
    if from_number and rid:
        try:
            await rc.assign_number_to_agent(from_number=from_number, agent_id=rid)
        except Exception:
            pass
    return {"retell_agent": created}


