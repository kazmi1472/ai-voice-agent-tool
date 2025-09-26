from fastapi import APIRouter, Request, HTTPException
from ..db import get_db
from ..services.openai_client import OpenAIClient
from ..services.retell_client import RetellClient
from ..services.escalation import detect_emergency_keywords
from ..services.transcript_processor import process_transcript_and_store
import os, hmac, hashlib, json

router = APIRouter()

def verify_signature(request_body: bytes, signature: str) -> bool:
    secret = os.getenv("RETELL_WEBHOOK_SECRET")
    if not secret:
        return True  # allow in local dev
    digest = hmac.new(secret.encode(), request_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")

@router.post("/webhook")
async def retell_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("x-retell-signature", "")
    if not verify_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        event = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON")

    event_type = event.get("event_type")
    call_id = event.get("call_id")
    timestamp = event.get("timestamp")
    payload = event.get("payload", {})
    if not call_id or not event_type:
        raise HTTPException(status_code=400, detail="Missing call_id or event_type")

    db = get_db()
    if event_type == "call.started":
        db.update_call_status(call_id, "in_progress")
        return {"ok": True}

    if event_type == "speech":
        text = payload.get("speech_text", "")
        speaker = payload.get("speaker", "driver")
        confidence = payload.get("confidence", 1.0)
        db.append_transcript(call_id, segment_text=text, speaker=speaker, timestamp=timestamp, confidence=confidence)

        # Noisy environment handling
        if (confidence is not None and confidence < 0.5) or ("[inaudible]" in text.lower()):
            low_count = db.increment_noisy_counter(call_id)
            if low_count <= 2:
                agent_text = "I didn't catch that, could you please repeat?"
                await RetellClient().speak(call_id, agent_text)
                return {"continued": True}
            else:
                agent_text = "I am having trouble hearing you, please wait for a human dispatcher to call."
                await RetellClient().speak(call_id, agent_text)
                db.update_call_status(call_id, "completed")
                await process_transcript_and_store(call_id, noisy=True)
                return {"ended": True}

        # Uncooperative handling
        if speaker == "driver" and len(text.split()) < 3:
            short_count = db.increment_short_utterances(call_id)
            if short_count in (1, 2):
                agent_text = "Could you clarify your status or location?"
                await RetellClient().speak(call_id, agent_text)
                return {"followup": True}
            if short_count >= 3:
                agent_text = "I'll have dispatch follow up shortly. Thank you."
                await RetellClient().speak(call_id, agent_text)
                db.update_call_status(call_id, "completed")
                await process_transcript_and_store(call_id, no_response=True)
                return {"ended": True}

        # Emergency keyword detection
        if detect_emergency_keywords(text):
            client = OpenAIClient()
            response = await client.emergency_protocol()
            await RetellClient().speak(call_id, response["agent_text"])
            db.flag_escalation(call_id)
            db.update_call_status(call_id, "completed")
            await process_transcript_and_store(call_id, emergency_info=response.get("structured_emergency"))
            return {"escalated": True}

        # Normal decision
        client = OpenAIClient()
        context = db.get_call_context(call_id)
        decision = await client.decide_next_action(context=context, last_driver_utterance=text)
        await RetellClient().speak(call_id, decision["agent_text"])
        if decision.get("action") in ("end_call", "escalate"):
            if decision.get("action") == "escalate":
                db.flag_escalation(call_id)
            db.update_call_status(call_id, "completed")
            await process_transcript_and_store(call_id)
        return {"ok": True}

    if event_type == "call.ended":
        db.update_call_status(call_id, "completed")
        await process_transcript_and_store(call_id)
        return {"ok": True}

    return {"ignored": True}
