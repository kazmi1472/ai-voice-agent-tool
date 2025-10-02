from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from uuid import UUID
from ..schemas.pydantic_schemas import CallStartRequest, CallRead, CallListResponse
from ..db import get_db
from ..services.retell_client import RetellClient
from ..services.openai_client import OpenAIClient
import os
import logging

# Set up logger
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/start", status_code=202)
async def start_call(payload: CallStartRequest, mode: Optional[str] = Query(default=None)):
    logger.info(f"Starting call for driver {payload.driver_name} to {payload.phone_number}")
    
    db = get_db()
    call = db.create_call(payload)
    logger.info(f"Created call record with ID: {call['id']}")
    
    simulate = os.getenv("SIMULATE_RETELL", "false").lower() == "true" or (mode == "local")
    logger.info(f"Simulation mode: {simulate}")
    
    if simulate:
        # Simulated enqueue
        logger.info(f"Simulating call for {call['id']}")
        db.update_call_status(call["id"], "in_progress")
    else:
        rc = RetellClient()
        try:
            logger.info(f"Calling Retell API to initiate call {call['id']}")
            # Fetch full agent config to forward voice settings and optional retell agent id
            resolved_cfg = None
            try:
                resolved_cfg = db.get_agent_config(payload.agent_config_id)
            except Exception:
                resolved_cfg = None
            voice_settings = (resolved_cfg or {}).get("voice_settings") if isinstance(resolved_cfg, dict) else None
            # Resolve the agent id bound to the provisioned phone number (static agent approach)
            from_number_env = os.getenv("RETELL_FROM_NUMBER")
            retell_agent_id = None
            if from_number_env:
                try:
                    retell_agent_id = await rc.resolve_agent_id_for_from_number(from_number_env)
                except Exception:
                    retell_agent_id = None
            # Allow explicit override from config if present
            if not retell_agent_id and isinstance(voice_settings, dict):
                retell_agent_id = voice_settings.get("retell_agent_id") or voice_settings.get("agent_id")
            agent_cfg = {
                "voice_settings": voice_settings,
                "agent_config_id": payload.agent_config_id,
                "driver_name": payload.driver_name,
                "load_number": payload.load_number,
            }
            if retell_agent_id:
                agent_cfg["agent_id"] = retell_agent_id
            await rc.initiate_call(call_id=str(call["id"]), phone_number=payload.phone_number, agent_config=agent_cfg)
            logger.info(f"Call {call['id']} successfully initiated with Retell")
        except Exception as e:
            logger.error(f"Failed to initiate call {call['id']} with Retell: {str(e)}")
            db.update_call_status(call["id"], "failed")
            raise HTTPException(status_code=502, detail="Failed to initiate call")
    
    return {"call_id": str(call["id"]), "status": "queued"}

@router.get("/", response_model=CallListResponse)
async def list_calls(status: Optional[str] = None, driver_name: Optional[str] = None, page: int = 1, page_size: int = 20):
    db = get_db()
    items, total = db.list_calls(status=status, driver_name=driver_name, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@router.get("/{call_id}", response_model=CallRead)
async def get_call(call_id: UUID):
    db = get_db()
    call = db.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call

@router.post("/{call_id}/process")
async def process_call(call_id: UUID):
    from ..services.transcript_processor import process_transcript_and_store
    db = get_db()
    if not db.get_call(call_id):
        raise HTTPException(status_code=404, detail="Call not found")
    await process_transcript_and_store(call_id)
    return {"processed": True}
