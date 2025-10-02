from fastapi import APIRouter, Request, HTTPException
from ..db import get_db
from ..services.openai_client import OpenAIClient
from ..services.retell_client import RetellClient
from ..services.escalation import detect_emergency_keywords
from ..services.transcript_processor import process_transcript_and_store
from ..services.slot_memory import extract_slots, get_missing_slots, build_followup_for_missing, polite_end_from_slots
import os, hmac, hashlib, json
import logging

# Set up logger
logger = logging.getLogger(__name__)

router = APIRouter()

def verify_signature(request_body: bytes, signature: str) -> bool:
    secret = os.getenv("RETELL_WEBHOOK_SECRET")
    if not secret:
        return True  # allow in local dev
    digest = hmac.new(secret.encode(), request_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")

@router.post("/webhook")
async def retell_webhook(request: Request):
    logger.info("Received webhook request from Retell AI")
    
    body = await request.body()
    sig = request.headers.get("x-retell-signature", "")
    
    if not verify_signature(body, sig):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        event = json.loads(body.decode("utf-8"))
        # Helpers
        def deep_get(d, path, default=None):
            cur = d
            for key in path:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    return default
            return cur

        def find_first_key(d, keys):
            # DFS search for first occurrence of any key in keys with a truthy value
            if isinstance(d, dict):
                for k, v in d.items():
                    if k in keys and v:
                        return v
                    found = find_first_key(v, keys)
                    if found:
                        return found
            elif isinstance(d, list):
                for item in d:
                    found = find_first_key(item, keys)
                    if found:
                        return found
            return None

        # Retell may send a batch under 'events'
        if isinstance(event, dict) and isinstance(event.get("events"), list):
            results = []
            for ev in event["events"]:
                ev_type = find_first_key(ev, {"event_type", "type"}) or deep_get(ev, ["event", "type"])  # type: ignore
                ev_call_id = find_first_key(ev, {"call_id", "callId"}) or deep_get(ev, ["call", "id"]) or deep_get(ev, ["data", "call", "id"])  # type: ignore
                logger.info(f"Webhook batched event: {ev_type} for call {ev_call_id}")
                # Process each minimal event by reusing handler logic (set and fall through below)
                ev["event_type"] = ev_type
                ev["call_id"] = ev_call_id
                results.append(ev)
            # For simplicity, handle the last event in batch in this request context
            if results:
                event = results[-1]

        raw_event_type = (
            find_first_key(event, {"event_type", "type"})
            or event.get("event")
            or deep_get(event, ["event", "type"]) 
        )
        raw_call_id = (
            find_first_key(event, {"call_id", "callId"})
            or deep_get(event, ["call", "id"])
            or deep_get(event, ["data", "call", "id"]) 
            or deep_get(event, ["metadata", "call_id"]) 
        )
        logger.info(f"Webhook event received: {raw_event_type} for call {raw_call_id}")
        # Reassign normalized values back so rest of handler works
        event["event_type"] = raw_event_type
        event["call_id"] = raw_call_id
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {str(e)}")
        raise HTTPException(status_code=400, detail="Malformed JSON")

    event_type = event.get("event_type")
    call_id = event.get("call_id")
    timestamp = event.get("timestamp")
    payload = event.get("payload") or event.get("data") or {}
    
    if not call_id or not event_type:
        try:
            logger.error(f"Raw webhook payload for debugging: {json.dumps(event)[:1000]}")
        except Exception:
            pass
        logger.error("Webhook missing required fields: call_id or event_type")
        raise HTTPException(status_code=400, detail="Missing call_id or event_type")

    db = get_db()
    if event_type == "call.started":
        logger.info(f"Call {call_id} started")
        # If this is an inbound call and we don't have a record yet, create a minimal call row
        existing = db.get_call(call_id)
        if not existing:
            try:
                # Retell may provide caller info in payload
                caller_number = payload.get("from") or payload.get("caller") or "unknown"
                agent_config_id = payload.get("agent_config_id")
                obj = type("Obj", (), {
                    "driver_name": payload.get("caller_name") or "Unknown",
                    "phone_number": caller_number,
                    "load_number": payload.get("load_number"),
                    "agent_config_id": agent_config_id,
                })
                created = db.create_call(obj)
                logger.info(f"Created inbound call record {created['id']} for webhook call_id {call_id}")
            except Exception:
                logger.warning("Failed to create inbound call record; continuing")
        db.update_call_status(call_id, "in_progress")
        return {"ok": True}

    if event_type in ("speech", "update_only", "transcript_update"):
        text = payload.get("speech_text", "")
        speaker = payload.get("speaker", "driver")
        confidence = payload.get("confidence", 1.0)
        interaction_type = payload.get("interaction_type") or event.get("interaction_type")
        logger.info(f"Speech event for call {call_id}: {speaker} said '{text[:50]}{'...' if len(text) > 50 else ''}' (confidence: {confidence})")
        # Always store the segment for audit trail
        db.append_transcript(call_id, segment_text=text, speaker=speaker, timestamp=timestamp, confidence=confidence)

        # Update slot and conversation state FIRST even for update_only so state is up to date
        try:
            if speaker == "driver" and text:
                slot_updates = extract_slots(text)
                if slot_updates:
                    slots_after = db.update_slot_memory(call_id, slot_updates)
                    logger.info(f"Updated slot memory for {call_id}: {slots_after}")
                # Reset retries when we successfully get a value for the last prompted slot
                state = db.get_conversation_state(call_id)
                last_slot = state.get("last_prompted_slot")
                if last_slot and slot_updates.get(last_slot):
                    db.update_conversation_state(call_id, {"prompt_retries": 0, "last_prompted_slot": None})
        except Exception as e:
            logger.warning(f"Slot extraction failed: {e}")

        # For update_only, do not synthesize speech; just update state and return
        if event_type == "update_only" or interaction_type == "update_only":
            return {"updated": True}

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

        # Drive next response from slot memory: ask only missing slots; end politely when filled
        try:
            slots = db.get_slot_memory(call_id)
            missing = get_missing_slots(slots)
            # If driver indicates bye/arrived, end politely
            lower_text = (text or "").lower()
            if any(k in lower_text for k in ["bye", "goodbye"]) or ("arrived" in lower_text):
                end_text = polite_end_from_slots(slots)
                await RetellClient().speak(call_id, end_text)
                db.update_call_status(call_id, "completed")
                await process_transcript_and_store(call_id)
                return {"ended": True}

            if not missing:
                # Nothing missing -> end politely
                end_text = polite_end_from_slots(slots)
                if not end_text:
                    # Defer closing line to LLM when templates disabled
                    client = OpenAIClient()
                    context = db.get_call_context(call_id)
                    decision = await client.decide_next_action(context=context, last_driver_utterance=text)
                    end_text = decision.get("agent_text") or "Thanks, ending the call."
                await RetellClient().speak(call_id, end_text)
                db.update_call_status(call_id, "completed")
                await process_transcript_and_store(call_id)
                return {"ended": True}

            # Avoid repeating same question too many times; rotate and paraphrase slightly
            state = db.get_conversation_state(call_id)
            next_slot = missing[0]
            retries = state.get("prompt_retries", 0)
            # If we kept asking for status+location together earlier, ensure we move on when they are filled
            prompt = build_followup_for_missing(missing)
            if not prompt:
                # When templates disabled, let the LLM craft the follow-up
                client = OpenAIClient()
                context = db.get_call_context(call_id)
                decision = await client.decide_next_action(context=context, last_driver_utterance=text)
                prompt = decision.get("agent_text") or "Okay."
            if retries == 1:
                if next_slot == "driver_status":
                    prompt = "Thanks. Could you share your current status now?"
                elif next_slot == "current_location":
                    prompt = "And where are you at the moment?"
                elif next_slot == "eta":
                    prompt = "When do you expect to arrive?"
                elif next_slot == "emergency_type":
                    prompt = "What kind of emergency is it?"
                elif next_slot == "emergency_location":
                    prompt = "Where exactly is the emergency happening?"
            elif retries >= 2:
                prompt = "If it's easier, just tell me one thing: your status, location, or ETA."

            await RetellClient().speak(call_id, prompt)
            db.update_conversation_state(call_id, {"last_prompted_slot": next_slot, "prompt_retries": retries + 1, "last_agent_message": prompt})
            return {"ok": True}
        except Exception as e:
            logger.warning(f"Slot-driven response fell back to LLM due to error: {e}")
            client = OpenAIClient()
            context = db.get_call_context(call_id)
            decision = await client.decide_next_action(context=context, last_driver_utterance=text)
            await RetellClient().speak(call_id, decision.get("agent_text") or "Okay.")
            if decision.get("action") in ("end_call", "escalate"):
                if decision.get("action") == "escalate":
                    db.flag_escalation(call_id)
                db.update_call_status(call_id, "completed")
                await process_transcript_and_store(call_id)
            return {"ok": True}

    if event_type == "call.ended":
        logger.info(f"Call {call_id} ended")
        db.update_call_status(call_id, "completed")
        await process_transcript_and_store(call_id)
        return {"ok": True}

    return {"ignored": True}
