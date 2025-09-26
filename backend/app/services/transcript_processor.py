from typing import Optional, Dict, Any
from ..db import get_db
from .openai_client import OpenAIClient


async def process_transcript_and_store(call_id: str, emergency_info: Optional[Dict[str, Any]] = None, noisy: bool = False, no_response: bool = False) -> None:
    db = get_db()
    call = db.get_call(call_id)
    if not call:
        return
    transcript_text = "\n".join([f"{seg['timestamp']} {seg['speaker']}: {seg['text']}" for seg in call.get("full_transcript", [])])
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

    db.save_summary(call_id, summary)
