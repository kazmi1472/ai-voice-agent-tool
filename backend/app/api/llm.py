from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
import asyncio
from ..db import get_db
from ..services.openai_client import OpenAIClient
from ..services.slot_memory import extract_slots, get_missing_slots, build_followup_for_missing, polite_end_from_slots
import json
import logging
from datetime import datetime
from typing import Dict, Any


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/retell/custom-llm")
async def retell_custom_llm(request: Request):
    try:
        # Track per-connection simple state to avoid repeating lines
        last_response_id_handled = None
        last_agent_text_sent = ""
        opening_sent = False
        db_call_id: str = ""
        # Lightweight slot tracking to determine natural end
        captured: dict = {"status": False, "location": False, "eta": False}
        awaiting_confirmation: bool = False
        # In-memory per-connection slot memory text values
        slot_values: Dict[str, Any] = {"status": None, "location": None, "eta": None}
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON")

    # Expected minimal shape from Retell
    conversation = body.get("conversation") or []
    metadata = body.get("metadata") or {}
    call_id = body.get("call_id") or metadata.get("call_id")
    agent_config_id = metadata.get("agent_config_id")

    # Build context from our DB and most recent user message
    db = get_db()
    context = {}
    if call_id:
        try:
            context = db.get_call_context(call_id)
        except Exception:
            context = {}
    if (not context) and agent_config_id:
        # fallback: pull prompt from agent config directly
        try:
            cfg = db.get_agent_config(agent_config_id) or {}
            context["prompt_template"] = cfg.get("prompt_template", "")
        except Exception:
            pass

    last_user = None
    for msg in reversed(conversation):
        if msg.get("role") == "user":
            last_user = msg.get("content")
            break

    # Decide next action / text using our existing OpenAIClient logic
    client = OpenAIClient()
    if not last_user:
        # Ask OpenAIClient to produce the opening line based on prompt_template and context
        decision = await client.decide_next_action(context=context, last_driver_utterance="")
        agent_text = decision.get("agent_text") or "Hello, how can I help you today?"
        return {"role": "assistant", "content": agent_text}

    decision = await client.decide_next_action(context=context, last_driver_utterance=last_user)
    agent_text = decision.get("agent_text") or "Okay."
    return {"role": "assistant", "content": agent_text}


# Optional WebSocket mode for Retell Custom LLM streaming
@router.websocket("/retell/custom-llm/{call_id}")
async def retell_custom_llm_ws(websocket: WebSocket, call_id: str):
    await websocket.accept()
    db = get_db()
    client = OpenAIClient()
    try:
        # Initialize per-connection state to avoid UnboundLocalError and repetition loops
        last_response_id_handled = None
        last_agent_text_sent = ""
        opening_sent = False
        awaiting_confirmation = False
        db_call_id: str = ""
        captured: dict = {"status": False, "location": False, "eta": False}
        slot_values: Dict[str, Any] = {"status": None, "location": None, "eta": None}
        # Heartbeat keepalive to avoid 1006 disconnects
        async def _keepalive():
            try:
                while True:
                    await asyncio.sleep(20)
                    try:
                        await websocket.send_text(json.dumps({"response_type": "ping_pong", "timestamp": datetime.utcnow().isoformat()}))
                    except Exception:
                        break
            except Exception:
                pass

        ka_task = asyncio.create_task(_keepalive())
        # Optional: Send config per Retell WS docs so Retell knows our preferences
        # See: https://docs.retellai.com/api-references/llm-websocket
        config_event = {
            "response_type": "config",
            "config": {
                "auto_reconnect": True,
                "call_details": False,
                "transcript_with_tool_calls": False,
                # Encourage Retell to request responses/reminders if user is silent
                "reminder_trigger_ms": 10000,
                "reminder_max_count": 1,
            },
        }
        try:
            await websocket.send_text(json.dumps(config_event))
        except Exception:
            pass

        # Per docs, send a begin message so agent can speak without waiting
        # Build minimal context from DB using Retell call_id
        try:
            open_context = {}
            try:
                db_call = db.get_call_by_retell_id(call_id)
                if db_call:
                    open_context = db.get_call_context(db_call["id"]) or {}
            except Exception:
                open_context = {}
            greeting_decision = await client.decide_next_action(context=open_context, last_driver_utterance="")
            opening_text = greeting_decision.get("agent_text") or "Hello, this is Dispatch. Can you give me a quick status update?"
            begin_event = {
                "response_type": "response",
                # response_id intentionally omitted for begin message per docs flow
                "content": opening_text,
                "content_complete": True,
            }
            await websocket.send_text(json.dumps(begin_event))

            # Proactively interrupt so the agent speaks immediately if Retell hasn't yielded turn yet
            try:
                interrupt_event = {
                    "response_type": "agent_interrupt",
                    "interrupt_id": 1,
                    "content": opening_text,
                    "content_complete": True,
                    "no_interruption_allowed": True,
                }
                await websocket.send_text(json.dumps(interrupt_event))
            except Exception:
                pass
            last_agent_text_sent = opening_text
            opening_sent = True
        except Exception:
            # Non-fatal if begin fails; will still respond on response_required
            pass

        # Wait for Retell to request a response instead of sending immediately
        print("WebSocket connected, waiting for Retell to request response...")

        while True:
            try:
                raw = await websocket.receive()
                print(f"Received WebSocket message: {raw}")
                if "text" not in raw:
                    # ignore non-text frames (pings, etc.)
                    print("Ignoring non-text frame")
                    continue
                message = raw["text"]
                print(f"Processing text message: {message}")
                try:
                    body = json.loads(message)
                    print(f"Parsed message body: {body}")
                except Exception as e:
                    print(f"Error parsing message: {e}")
                    await websocket.send_text(json.dumps({"role": "assistant", "content": ""}))
                    continue
            except Exception as e:
                print(f"Error receiving WebSocket message: {e}")
                break

            # Handle different Retell interaction types
            interaction_type = body.get("interaction_type")
            turntaking = body.get("turntaking")
            response_id = body.get("response_id")
            
            print(f"Interaction type: {interaction_type}, Turn taking: {turntaking}, Response ID: {response_id}")

            # Respond to ping_pong to keep the socket alive when requested
            if interaction_type == "ping_pong":
                try:
                    pong = {"response_type": "ping_pong", "timestamp": body.get("timestamp")}
                    await websocket.send_text(json.dumps(pong))
                except Exception:
                    pass
                continue

            # Update-only or other non-speaking messages should still update slot memory/state
            if interaction_type not in ("response_required", "reminder_required"):
                # Try to capture any transcript update to refresh slot memory
                try:
                    transcript = body.get("transcript", []) or []
                    for msg in transcript[-3:]:
                        if (msg.get("role") or msg.get("speaker")) in ("user", "driver"):
                            text = msg.get("content") or msg.get("text") or ""
                            updates = extract_slots(text)
                            if updates and db_call_id:
                                db.update_slot_memory(db_call_id, updates)
                except Exception:
                    pass
                print(f"Skipping response for interaction_type: {interaction_type}")
                continue

            # Avoid duplicate replies for the same response_id
            try:
                if response_id and response_id == last_response_id_handled:
                    print(f"Duplicate response_id received, ignoring: {response_id}")
                    continue
            except Exception:
                pass

            conversation = body.get("conversation") or body.get("messages") or []
            transcript = body.get("transcript", [])
            metadata = body.get("metadata") or {}
            # Prefer WS path call_id; fall back to metadata
            call_ref = call_id or body.get("call_id") or metadata.get("call_id")

            # Build context
            context = {}
            if call_ref:
                try:
                    print(f"Getting call context for call_ref: {call_ref}")
                    
                    # If this is a Retell call_id, try to find the database call_id first
                    if call_ref.startswith("call_"):
                        # This is a Retell call_id, try to find the database call_id
                        try:
                            db_call = db.get_call_by_retell_id(call_ref)
                            if db_call:
                                # Use the database call_id for context retrieval
                                context = db.get_call_context(db_call["id"])
                                print(f"Found database call_id: {db_call['id']}")
                                db_call_id = db_call["id"]
                            else:
                                # Fallback to metadata
                                context = {
                                    "driver_name": metadata.get("driver_name", ""),
                                    "load_number": metadata.get("load_number", ""),
                                    "call_history": "",
                                    "prompt_template": ""
                                }
                                # Try to get prompt template from agent_config_id
                                agent_config_id = metadata.get("agent_config_id")
                                if agent_config_id:
                                    try:
                                        cfg = db.get_agent_config(agent_config_id)
                                        if cfg:
                                            context["prompt_template"] = cfg.get("prompt_template", "")
                                    except Exception:
                                        pass
                        except Exception as e:
                            print(f"Error finding database call_id: {e}")
                            # Fallback to metadata
                            context = {
                                "driver_name": metadata.get("driver_name", ""),
                                "load_number": metadata.get("load_number", ""),
                                "call_history": "",
                                "prompt_template": ""
                            }
                    else:
                        # This is a database call_id, use normal context retrieval
                        context = db.get_call_context(call_ref)
                    
                    print(f"Retrieved context: {context}")
                except Exception as e:
                    print(f"Error getting call context: {e}")
                    context = {}

            # Extract user input from transcript and build brief history
            last_user = None
            history_chunks = []
            if transcript:
                # Get the last user message from transcript
                for msg in reversed(transcript):
                    if msg.get("role") == "user" or msg.get("speaker") == "user":
                        last_user = msg.get("content") or msg.get("text")
                        break
                # Persist the newest user utterance to DB transcript if possible
                try:
                    if db_call_id and last_user:
                        db.append_transcript(
                            db_call_id,
                            segment_text=last_user,
                            speaker="driver",
                            timestamp=datetime.utcnow().isoformat(),
                            confidence=1.0,
                        )
                except Exception as _:
                    pass
                # Build call_history from last few utterances for better context
                try:
                    for msg in transcript[-8:]:
                        role = msg.get("role") or msg.get("speaker") or "user"
                        text = (msg.get("content") or msg.get("text") or "").strip()
                        if text:
                            history_chunks.append(f"{role}: {text}")
                except Exception:
                    pass
                # Recompute slot capture from the entire transcript window to avoid misses
                try:
                    import re as _re
                    for msg in transcript:
                        if (msg.get("role") or msg.get("speaker")) not in ("user",):
                            continue
                        t = (msg.get("content") or msg.get("text") or "").lower()
                        if any(w in t for w in ["driving", "delayed", "arrived", "dispatched"]):
                            captured["status"] = True
                        if _re.search(r"(?i)\b(?:my\s+location\s+is|location\s+is|currently\s+in|in|at|near|around|by|on)\s+([A-Za-z][\w\-\s,]{2,})\b", t):
                            captured["location"] = True
                        if _re.search(r"(?i)\b(\d{1,2}\s?(am|pm))\b|\b\d{1,2}:\d{2}\b|\bnoon\b|\bmidnight\b|\bETA\b|\b(in\s+\d+\s+(hours?|hrs?|minutes?|mins?))\b|\b(today|tonight|tomorrow)\b", t):
                            captured["eta"] = True
                except Exception:
                    pass
            
            # Fallback to conversation array
            if not last_user:
                for msg in reversed(conversation):
                    if msg.get("role") == "user":
                        last_user = msg.get("content")
                        break

            # Inject recent history into context to reduce repetition
            if history_chunks:
                context = dict(context or {})
                context["call_history"] = " \n".join(history_chunks[-8:])

            print(f"Last user input: {last_user}")

            # Generate response (slot-first strategy with lightweight fallbacks)
            try:
                # Ensure locals exist to avoid UnboundLocalError
                agent_text = ""
                end_now_affirm = False
                decision_current: Dict[str, Any] = {}

                if last_user:
                    lower_text = (last_user or "").lower()
                    # Update shared slot memory BEFORE deciding next response
                    try:
                        if db_call_id:
                            updates = extract_slots(last_user)
                            if updates:
                                db.update_slot_memory(db_call_id, updates)
                    except Exception:
                        pass
                    # If we are awaiting a yes/no confirmation, handle it first
                    if awaiting_confirmation:
                        if any(w in lower_text for w in ["yes", "yeah", "yep", "correct", "right", "confirm", "confirmed"]):
                            agent_text = "Thanks for confirming. Drive safe — ending the call."
                            end_now_affirm = True
                            awaiting_confirmation = False
                            # fall through to send
                        elif any(w in lower_text for w in ["no", "nope", "incorrect", "not correct", "wrong"]):
                            # Reset and re-collect, starting from status succinctly
                            captured = {"status": False, "location": False, "eta": False}
                            agent_text = "No problem. What is your current status?"
                            awaiting_confirmation = False
                            # fall through to send
                        # If confirmation words not detected, continue to normal extraction below
                    # Emergency heuristic - use the same detection as webhook
                    from ..services.escalation import detect_emergency_keywords
                    if detect_emergency_keywords(last_user):
                        decision_current = await client.emergency_protocol()
                        agent_text = decision_current.get("agent_text") or "A human dispatcher will call you back immediately."
                        # Store emergency info in slot memory for summary
                        if decision_current.get("structured_emergency"):
                            emergency_info = decision_current.get("structured_emergency")
                            if db_call_id:
                                db.update_slot_memory(db_call_id, {
                                    "emergency_type": emergency_info.get("emergency_type"),
                                    "emergency_location": emergency_info.get("emergency_location")
                                })
                        # Set end_call if emergency protocol triggered
                        if decision_current.get("action") == "escalate":
                            end_now = True
                            # Flag escalation in the database
                            if db_call_id:
                                db.flag_escalation(db_call_id)
                    else:
                        # Status / location quick extraction
                        import re
                        # Capture common phrasings for location (in/at/near/by/on ... , "my location is", "location is", "currently in")
                        location_match = re.search(r"(?i)\b(?:my\s+location\s+is|location\s+is|currently\s+in|in|at|near|around|by|on)\s+([A-Za-z][\w\-\s,]{2,})\b", last_user)
                        # Normalize common city spellings
                        if location_match:
                            loc_raw = location_match.group(1).strip().rstrip('.')
                            loc_norm = loc_raw
                            for a, b in [("moutan", "Multan"), ("mudan", "Multan"), ("muzan", "Multan"), ("muntan", "Multan"), ("muntaan", "Multan"), ("lahar", "Lahore")]:
                                if a.lower() in loc_norm.lower():
                                    loc_norm = b
                            # Remove trailing filler like "right now", "currently", "for now"
                            try:
                                import re as _re
                                loc_norm = _re.sub(r"(?i)\b(right\s+now|currently|for\s+now)\b\.?$", "", loc_norm).strip()
                                # Trim residual trailing commas or periods
                                loc_norm = loc_norm.rstrip(" ,.")
                            except Exception:
                                pass
                            # Use the normalized value directly
                            normalized_location = loc_norm
                        # Update captured slots from last_user
                        if any(w in lower_text for w in ["driving", "delayed", "arrived", "dispatched"]):
                            captured["status"] = True
                            if not slot_values.get("status"):
                                for w in ["Driving", "Delayed", "Arrived", "Dispatched"]:
                                    if w.lower() in lower_text:
                                        slot_values["status"] = w
                                        break
                        if location_match:
                            captured["location"] = True
                            if 'normalized_location' in locals():
                                loc = normalized_location
                            else:
                                loc = location_match.group(1).strip().rstrip('.')
                                for a, b in [("moutan", "Multan"), ("mudan", "Multan"), ("muzan", "Multan"), ("muntan", "Multan"), ("muntaan", "Multan"), ("lahar", "Lahore")]:
                                    if a.lower() in loc.lower():
                                        loc = b
                            slot_values["location"] = loc
                        # ETA detection: digits (5 pm, 12:30), words (five pm), relative (in 2 hours), and day words
                        eta_digit = re.search(r"(?i)\b(\d{1,2}\s?(am|pm))\b|\b\d{1,2}:\d{2}\b", lower_text)
                        eta_word = re.search(r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s?(am|pm)\b", lower_text)
                        eta_rel  = re.search(r"(?i)\b(in\s+\d+\s+(hours?|hrs?|minutes?|mins?))\b", lower_text)
                        eta_day  = re.search(r"(?i)\b(today|tonight|tomorrow)\b", lower_text)
                        eta_token = re.search(r"(?i)\beta\b|\beta\s+is\b", lower_text)
                        if eta_digit or eta_word or eta_rel or (eta_day and (eta_digit or eta_word)) or eta_token:
                            captured["eta"] = True
                            if not slot_values.get("eta"):
                                # Compose a simple ETA text from tokens present
                                if eta_digit:
                                    slot_values["eta"] = eta_digit.group(0)
                                elif eta_word and eta_day:
                                    slot_values["eta"] = f"{eta_day.group(0)} {eta_word.group(0)}"
                                elif eta_word:
                                    slot_values["eta"] = eta_word.group(0)
                                elif eta_rel:
                                    slot_values["eta"] = eta_rel.group(0)
                        # Slot-driven questioning based on shared memory
                        try:
                            # Map local heuristic captures into shared slot model for continuity
                            shared_slots = db.get_slot_memory(db_call_id) if db_call_id else {}
                            # Reconcile simple captured flags into shared slots if we have values
                            if captured.get("status") and slot_values.get("status") and not shared_slots.get("driver_status"):
                                db.update_slot_memory(db_call_id, {"driver_status": slot_values.get("status")})
                                shared_slots = db.get_slot_memory(db_call_id)
                            if captured.get("location") and slot_values.get("location") and not shared_slots.get("current_location"):
                                db.update_slot_memory(db_call_id, {"current_location": slot_values.get("location")})
                                shared_slots = db.get_slot_memory(db_call_id)
                            if captured.get("eta") and slot_values.get("eta") and not shared_slots.get("eta"):
                                db.update_slot_memory(db_call_id, {"eta": slot_values.get("eta")})
                                shared_slots = db.get_slot_memory(db_call_id)
                            missing = get_missing_slots(shared_slots)
                            if not missing:
                                agent_text = polite_end_from_slots(shared_slots)
                                end_now_affirm = True
                            else:
                                agent_text = build_followup_for_missing(missing)
                        except Exception:
                            # Fallback to original heuristic prompts
                            slots_done = captured.get("status") and captured.get("location") and captured.get("eta")
                            if not slots_done:
                                if not captured.get("status"):
                                    agent_text = "Got it. What is your current status?"
                                elif not captured.get("location"):
                                    agent_text = "Thanks. Where are you right now?"
                                elif not captured.get("eta"):
                                    agent_text = "Noted. What's your ETA?"
                            else:
                                if not awaiting_confirmation:
                                    status_txt = slot_values.get("status") or "your status"
                                    loc_txt = slot_values.get("location") or "your location"
                                    eta_txt = slot_values.get("eta") or "your ETA"
                                    agent_text = f"Just to confirm, status {status_txt}, location {loc_txt}, ETA {eta_txt}. Is that correct?"
                                    awaiting_confirmation = True
                                else:
                                    agent_text = "Please say yes or no to confirm."
                        # Out-of-scope guard: if we still have no clear slot progress and no emergency cue
                        try:
                            if not agent_text or agent_text.strip() == "Okay.":
                                # Defer to LLM to decide next best utterance given current context
                                llm_context = context or {}
                                try:
                                    if db_call_id:
                                        shared_slots = db.get_slot_memory(db_call_id)
                                        # Provide missing slots as a hint in call_history to keep schema unchanged
                                        missing_now = get_missing_slots(shared_slots)
                                        if missing_now:
                                            hint = "Missing fields: " + ", ".join(missing_now)
                                            llm_context = dict(llm_context)
                                            llm_context["call_history"] = (llm_context.get("call_history") or "") + f"\n[HINT] {hint}"
                                except Exception:
                                    pass
                                decision_current = await client.decide_next_action(context=llm_context, last_driver_utterance=last_user)
                                agent_text = decision_current.get("agent_text") or agent_text or "Okay."
                        except Exception:
                            pass
                else:
                    # No new user text; avoid repeating the opening
                    if opening_sent:
                        agent_text = "Could you share your current status: Driving, Delayed, or Arrived?"
                    else:
                        decision = await client.decide_next_action(context=context, last_driver_utterance="")
                        agent_text = decision.get("agent_text") or "Hello, how can I help you today?"
            except Exception as e:
                logger.error(f"Response generation error: {str(e)}")
                agent_text = "I understand."

            # Avoid sending identical text back-to-back
            if agent_text.strip() == (last_agent_text_sent or "").strip():
                # Defer to LLM to paraphrase to avoid repetition
                try:
                    decision_current = await client.decide_next_action(context=context, last_driver_utterance=last_user)
                    alt_text = (decision_current or {}).get("agent_text")
                    if alt_text and alt_text.strip() != agent_text.strip():
                        agent_text = alt_text
                    else:
                        # As a last resort, nudge LLM with a variation hint
                        varied_ctx = dict(context or {})
                        varied_ctx["call_history"] = (varied_ctx.get("call_history") or "") + "\n[HINT] Please avoid repeating the last sentence; rephrase succinctly."
                        decision_current = await client.decide_next_action(context=varied_ctx, last_driver_utterance=last_user)
                        agent_text = (decision_current or {}).get("agent_text") or agent_text
                except Exception:
                    pass

            print(f"Sending response message: {agent_text}")

            # Retell documented response event shape
            # https://docs.retellai.com/api-references/llm-websocket
            response_event = {
                "response_type": "response",
                "response_id": response_id,
                "content": agent_text,
                "content_complete": True,
            }
            # End conditions
            try:
                lower_text = (last_user or "").lower()
                end_now = any(k in lower_text for k in ["bye", "goodbye"]) or ("arrived" in lower_text)
            except Exception:
                end_now = False
            # Respect LLM action only for this turn's decision
            try:
                if isinstance(decision_current, dict):
                    if decision_current.get("action") in ("end_call", "escalate"):
                        end_now = True
            except Exception:
                pass

            try:
                slots_done = bool(captured.get("status") and captured.get("location") and captured.get("eta"))
            except Exception:
                slots_done = False

            if end_now or end_now_affirm or slots_done:
                response_event["end_call"] = True
            await websocket.send_text(json.dumps(response_event))
            # Store agent utterance to transcript
            try:
                if db_call_id and agent_text:
                    db.append_transcript(
                        db_call_id,
                        segment_text=agent_text,
                        speaker="agent",
                        timestamp=datetime.utcnow().isoformat(),
                        confidence=1.0,
                    )
            except Exception:
                pass
            last_response_id_handled = response_id
            last_agent_text_sent = agent_text

            # If we signaled end_call, mark completed and trigger summarization
            try:
                if response_event.get("end_call") and db_call_id:
                    db.update_call_status(db_call_id, "completed")
                    from ..services.transcript_processor import process_transcript_and_store
                    # Ensure latest slot memory is represented in transcript for summary
                    try:
                        shared_slots = db.get_slot_memory(db_call_id)
                        memo_line = (
                            f"[SLOTS] driver_status={shared_slots.get('driver_status')}, "
                            f"current_location={shared_slots.get('current_location')}, "
                            f"eta={shared_slots.get('eta')}, "
                            f"emergency_type={shared_slots.get('emergency_type')}, "
                            f"emergency_location={shared_slots.get('emergency_location')}"
                        )
                        db.append_transcript(db_call_id, memo_line, "agent", datetime.utcnow().isoformat(), 1.0)
                    except Exception:
                        pass
                    await process_transcript_and_store(db_call_id)
                    # Politely close the socket to prevent lingering 1006
                    try:
                        await websocket.close(code=1000)
                    except Exception:
                        pass
            except Exception as _:
                pass
    except WebSocketDisconnect:
        logger.info(f"Retell Custom LLM WS disconnected for call {call_id}")
    except Exception as e:
        logger.error(f"Retell Custom LLM WS error: {str(e)}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        # Stop keepalive if running
        try:
            ka_task.cancel()
        except Exception:
            pass


