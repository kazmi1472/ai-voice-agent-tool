from typing import Optional, Dict, Any
from ..db import get_db
from .openai_client import OpenAIClient


async def process_transcript_and_store(call_id: str, emergency_info: Optional[Dict[str, Any]] = None, noisy: bool = False, no_response: bool = False) -> None:
    db = get_db()
    call = db.get_call(call_id)
    if not call:
        return
    # Build transcript from existing in-memory or fetch from DB when not present
    try:
        full = call.get("full_transcript", [])
        if not full:
            # Fallback: fetch from DB adapter
            db_call = db.get_call(call_id)
            full = (db_call or {}).get("full_transcript", [])
    except Exception:
        full = call.get("full_transcript", [])
    transcript_text = "\n".join([f"{seg.get('timestamp')} {seg.get('speaker')}: {seg.get('text')}" for seg in full])
    client = OpenAIClient()
    if noisy:
        summary = {
            "call_outcome": "Unknown",
            "driver_status": None,
            "current_location": None,
            "eta": None,
            "emergency_type": None,
            "emergency_location": None,
            "escalation_status": None,
            "extraction_notes": "Noisy - transcript low confidence",
        }
    elif no_response:
        summary = {
            "call_outcome": "No Response",
            "driver_status": None,
            "current_location": None,
            "eta": None,
            "emergency_type": None,
            "emergency_location": None,
            "escalation_status": None,
            "extraction_notes": "Driver did not provide substantive responses",
        }
    else:
        summary = await client.summarize(transcript_text)
        if emergency_info:
            summary["call_outcome"] = "Emergency Detected"
            summary["escalation_status"] = "Escalation Flagged"
            if emergency_info.get("emergency_type"):
                summary["emergency_type"] = emergency_info.get("emergency_type")
            if emergency_info.get("emergency_location"):
                summary["emergency_location"] = emergency_info.get("emergency_location")
    # Merge latest slot memory into summary to reflect last filled values
    try:
        slots = db.get_slot_memory(call_id)
        if slots:
            # Only overwrite when slot has a value
            if slots.get("driver_status") is not None:
                summary["driver_status"] = slots.get("driver_status")
            if slots.get("current_location") is not None:
                summary["current_location"] = slots.get("current_location")
            if slots.get("eta") is not None:
                summary["eta"] = slots.get("eta")
            if slots.get("emergency_type") is not None:
                summary["emergency_type"] = slots.get("emergency_type")
            if slots.get("emergency_location") is not None:
                summary["emergency_location"] = slots.get("emergency_location")
    except Exception:
        pass

    db.save_summary(call_id, summary)
