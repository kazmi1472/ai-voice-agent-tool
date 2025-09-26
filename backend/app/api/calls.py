from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from uuid import UUID
from ..schemas.pydantic_schemas import CallStartRequest, CallRead, CallListResponse
from ..db import get_db
from ..services.retell_client import RetellClient
from ..services.openai_client import OpenAIClient
import os

router = APIRouter()

@router.post("/start", status_code=202)
async def start_call(payload: CallStartRequest, mode: Optional[str] = Query(default=None)):
    db = get_db()
    call = db.create_call(payload)
    simulate = os.getenv("SIMULATE_RETELL", "false").lower() == "true" or (mode == "local")
    if simulate:
        # Simulated enqueue
        db.update_call_status(call["id"], "in_progress")
    else:
        rc = RetellClient()
        try:
            await rc.initiate_call(call_id=str(call["id"]), phone_number=payload.phone_number)
        except Exception:
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
