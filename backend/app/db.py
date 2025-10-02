from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4, UUID
import os
from datetime import datetime

# Lightweight adapter over Supabase client. For demo, keep an in-memory fallback when SUPABASE_URL is missing.
from supabase import create_client, Client


class InMemoryDB:
    def __init__(self) -> None:
        self.agent_configs: Dict[str, Dict[str, Any]] = {}
        self.calls: Dict[str, Dict[str, Any]] = {}
        self.transcripts: List[Dict[str, Any]] = []
        self.summaries: Dict[str, Dict[str, Any]] = {}
        self.noisy_counter: Dict[str, int] = {}
        self.short_counter: Dict[str, int] = {}
        # Volatile per-call slot memory
        self.slot_memory: Dict[str, Dict[str, Any]] = {}
        # Volatile per-call conversation state (prompting, retries, last agent text)
        self.conversation_state: Dict[str, Dict[str, Any]] = {}

    # Agent configs
    def list_agent_configs(self) -> List[Dict[str, Any]]:
        return list(self.agent_configs.values())

    def get_agent_config(self, rid: str) -> Optional[Dict[str, Any]]:
        return self.agent_configs.get(str(rid))

    def create_agent_config(self, body) -> Dict[str, Any]:
        rid = str(uuid4())
        obj = {
            "id": rid,
            "name": body.name,
            "description": body.description,
            "prompt_template": body.prompt_template,
            "voice_settings": body.voice_settings or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.agent_configs[rid] = obj
        return obj

    def update_agent_config(self, rid: UUID, body) -> Optional[Dict[str, Any]]:
        rid = str(rid)
        if rid not in self.agent_configs:
            return None
        obj = self.agent_configs[rid]
        for k in ["name", "description", "prompt_template", "voice_settings"]:
            v = getattr(body, k, None)
            if v is not None:
                obj[k] = v
        obj["updated_at"] = datetime.utcnow().isoformat()
        return obj

    def delete_agent_config(self, rid: UUID) -> bool:
        return self.agent_configs.pop(str(rid), None) is not None

    # Calls
    def create_call(self, payload) -> Dict[str, Any]:
        cid = str(uuid4())
        obj = {
            "id": cid,
            "driver_name": payload.driver_name,
            "phone_number": payload.phone_number,
            "load_number": payload.load_number,
            "agent_config_id": payload.agent_config_id,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
            "events": [],
            "full_transcript": [],
            "structured_summary": None,
        }
        self.calls[cid] = obj
        return obj

    def update_call_status(self, call_id: str, status: str) -> None:
        if call_id in self.calls:
            self.calls[call_id]["status"] = status

    def list_calls(self, status: Optional[str], driver_name: Optional[str], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        items = list(self.calls.values())
        if status:
            items = [c for c in items if c.get("status") == status]
        if driver_name:
            items = [c for c in items if driver_name.lower() in c.get("driver_name", "").lower()]
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def get_call(self, call_id: UUID) -> Optional[Dict[str, Any]]:
        return self.calls.get(str(call_id))

    def append_transcript(self, call_id: str, segment_text: str, speaker: str, timestamp: str, confidence: float) -> None:
        self.transcripts.append({
            "call_id": call_id,
            "segment_text": segment_text,
            "speaker": speaker,
            "timestamp": timestamp,
            "confidence": confidence,
            "is_final": True,
        })
        self.calls[call_id]["full_transcript"].append({
            "text": segment_text,
            "speaker": speaker,
            "timestamp": timestamp,
            "confidence": confidence,
        })

    def increment_noisy_counter(self, call_id: str) -> int:
        self.noisy_counter[call_id] = self.noisy_counter.get(call_id, 0) + 1
        return self.noisy_counter[call_id]

    def increment_short_utterances(self, call_id: str) -> int:
        self.short_counter[call_id] = self.short_counter.get(call_id, 0) + 1
        return self.short_counter[call_id]

    def flag_escalation(self, call_id: str) -> None:
        self.calls[call_id]["escalation_status"] = "Escalation Flagged"

    def get_call_context(self, call_id: str) -> Dict[str, Any]:
        call = self.calls[call_id]
        cfg = self.agent_configs.get(call.get("agent_config_id"))
        return {
            "driver_name": call.get("driver_name"),
            "load_number": call.get("load_number"),
            "call_history": " ".join([seg["text"] for seg in call.get("full_transcript", [])]),
            "prompt_template": cfg.get("prompt_template") if cfg else "",
            "voice_settings": (cfg or {}).get("voice_settings"),
        }

    def save_summary(self, call_id: str, summary: Dict[str, Any]) -> None:
        self.summaries[call_id] = {
            "id": str(uuid4()),
            "call_id": call_id,
            "summary": summary,
            "summary_version": "v1",
            "created_at": datetime.utcnow().isoformat(),
        }
        self.calls[call_id]["structured_summary"] = summary
        self.calls[call_id]["status"] = "processed"

    # Slot memory helpers
    def get_slot_memory(self, call_id: str) -> Dict[str, Any]:
        return self.slot_memory.get(call_id, {
            "driver_status": None,
            "current_location": None,
            "eta": None,
            "emergency_type": None,
            "emergency_location": None,
        })

    def update_slot_memory(self, call_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_slot_memory(call_id)
        merged = dict(current)
        for k, v in (updates or {}).items():
            if v is not None and v != "":
                merged[k] = v
        self.slot_memory[call_id] = merged
        return merged

    # Conversation state helpers
    def get_conversation_state(self, call_id: str) -> Dict[str, Any]:
        return self.conversation_state.get(call_id, {
            "last_prompted_slot": None,
            "prompt_retries": 0,
            "last_agent_message": None,
        })

    def update_conversation_state(self, call_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_conversation_state(call_id)
        merged = dict(current)
        for k, v in (updates or {}).items():
            merged[k] = v
        self.conversation_state[call_id] = merged
        return merged


class SupabaseDB:
    def __init__(self, client: Client) -> None:
        self.client = client
        # Non-persistent counters for noisy/uncooperative tracking
        self.noisy_counter: Dict[str, int] = {}
        self.short_counter: Dict[str, int] = {}
        # In-memory slot memory cache for runtime conversation state
        self.slot_memory: Dict[str, Dict[str, Any]] = {}
        # In-memory conversation state for prompting
        self.conversation_state: Dict[str, Dict[str, Any]] = {}

    # Agent configs
    def list_agent_configs(self) -> List[Dict[str, Any]]:
        res = self.client.table("agent_configs").select("*").order("created_at", desc=False).execute()
        return res.data or []

    def get_agent_config(self, rid: str) -> Optional[Dict[str, Any]]:
        res = self.client.table("agent_configs").select("*").eq("id", str(rid)).single().execute()
        return res.data

    def create_agent_config(self, body) -> Dict[str, Any]:
        payload = {
            "name": body.name,
            "description": body.description,
            "prompt_template": body.prompt_template,
            "voice_settings": body.voice_settings or {},
        }
        res = self.client.table("agent_configs").insert(payload).execute()
        return (res.data or [])[0]

    def update_agent_config(self, rid: UUID, body) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {}
        for k in ["name", "description", "prompt_template", "voice_settings"]:
            v = getattr(body, k, None)
            if v is not None:
                payload[k] = v
        if not payload:
            res = self.client.table("agent_configs").select("*").eq("id", str(rid)).single().execute()
            return res.data
        res = self.client.table("agent_configs").update(payload).eq("id", str(rid)).execute()
        return (res.data or [None])[0]

    def delete_agent_config(self, rid: UUID) -> bool:
        res = self.client.table("agent_configs").delete().eq("id", str(rid)).execute()
        return bool(res.count) if hasattr(res, "count") else True

    # Calls
    def create_call(self, payload) -> Dict[str, Any]:
        row = {
            "driver_name": payload.driver_name,
            "phone_number": payload.phone_number,
            "load_number": payload.load_number,
            "agent_config_id": payload.agent_config_id,
            "status": "queued",
            "started_at": None,
            "ended_at": None,
            "duration_seconds": None,
        }
        res = self.client.table("calls").insert(row).execute()
        data = (res.data or [])[0]
        data["events"] = []
        data["full_transcript"] = []
        data["structured_summary"] = None
        return data

    def update_call_status(self, call_id: str, status: str) -> None:
        self.client.table("calls").update({"status": status}).eq("id", call_id).execute()

    def update_retell_call_id(self, call_id: str, retell_call_id: str) -> None:
        """Update the Retell call_id for a database call record"""
        try:
            self.client.table("calls").update({"retell_call_id": retell_call_id}).eq("id", call_id).execute()
        except Exception as e:
            # Column doesn't exist yet, just log and continue
            print(f"Warning: Could not update retell_call_id (column may not exist): {e}")

    def get_call_by_retell_id(self, retell_call_id: str) -> Optional[Dict[str, Any]]:
        """Get call record by Retell call_id"""
        call_res = self.client.table("calls").select("*").eq("retell_call_id", retell_call_id).single().execute()
        return call_res.data

    def list_calls(self, status: Optional[str], driver_name: Optional[str], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        query = self.client.table("calls").select("*")
        if status:
            query = query.eq("status", status)
        if driver_name:
            query = query.ilike("driver_name", f"%{driver_name}%")
        # total count
        count_res = query.execute()
        total = len(count_res.data or [])
        # pagination
        start = (page - 1) * page_size
        end = start + page_size - 1
        page_res = query.order("created_at", desc=True).range(start, end).execute()
        items = page_res.data or []
        return items, total

    def get_call(self, call_id: UUID) -> Optional[Dict[str, Any]]:
        cid = str(call_id)
        call_res = self.client.table("calls").select("*").eq("id", cid).single().execute()
        call = call_res.data
        if not call:
            return None
        # transcript
        tr_res = self.client.table("call_transcripts").select("segment_text,speaker,timestamp,confidence").eq("call_id", cid).order("timestamp", desc=False).execute()
        segments = [{"text": r["segment_text"], "speaker": r["speaker"], "timestamp": r.get("timestamp"), "confidence": r.get("confidence")} for r in (tr_res.data or [])]
        # latest summary
        sum_res = self.client.table("call_summaries").select("summary").eq("call_id", cid).order("created_at", desc=True).limit(1).execute()
        summary = (sum_res.data[0]["summary"] if sum_res.data else None)
        # Some drivers/clients may return summary as a JSON string instead of JSONB
        if isinstance(summary, str):
            try:
                import json as _json
                summary = _json.loads(summary)
            except Exception:
                pass
        call["events"] = []
        call["full_transcript"] = segments
        call["structured_summary"] = summary
        return call

    def append_transcript(self, call_id: str, segment_text: str, speaker: str, timestamp: str, confidence: float) -> None:
        self.client.table("call_transcripts").insert({
            "call_id": call_id,
            "segment_text": segment_text,
            "speaker": speaker,
            "timestamp": timestamp,
            "confidence": confidence,
            "is_final": True,
        }).execute()

    def increment_noisy_counter(self, call_id: str) -> int:
        self.noisy_counter[call_id] = self.noisy_counter.get(call_id, 0) + 1
        return self.noisy_counter[call_id]

    def increment_short_utterances(self, call_id: str) -> int:
        self.short_counter[call_id] = self.short_counter.get(call_id, 0) + 1
        return self.short_counter[call_id]

    def flag_escalation(self, call_id: str) -> None:
        # Not persisted in schema; could be added to summaries or calls via an extra column.
        pass

    def get_call_context(self, call_id: str) -> Dict[str, Any]:
        # Try to get call by database ID first, then by Retell call_id
        call_res = self.client.table("calls").select("driver_name,load_number,agent_config_id,id").eq("id", call_id).single().execute()
        call = call_res.data or {}
        
        # If not found by database ID, try Retell call_id (if column exists)
        if not call:
            try:
                call_res = self.client.table("calls").select("driver_name,load_number,agent_config_id,id").eq("retell_call_id", call_id).single().execute()
                call = call_res.data or {}
                # Use the database ID for transcript queries
                if call:
                    call_id = call["id"]
            except Exception:
                # Column doesn't exist yet, fall back to empty context
                call = {}
        
        cfg = None
        if call.get("agent_config_id"):
            cfg_res = self.client.table("agent_configs").select("prompt_template").eq("id", call["agent_config_id"]).single().execute()
            cfg = cfg_res.data
        tr_res = self.client.table("call_transcripts").select("segment_text").eq("call_id", call_id).order("timestamp", desc=False).execute()
        history = " ".join([r["segment_text"] for r in (tr_res.data or [])])
        return {
            "driver_name": call.get("driver_name"),
            "load_number": call.get("load_number"),
            "call_history": history,
            "prompt_template": (cfg or {}).get("prompt_template", ""),
        }

    def save_summary(self, call_id: str, summary: Dict[str, Any]) -> None:
        self.client.table("call_summaries").insert({
            "call_id": call_id,
            "summary": summary,
            "summary_version": "v1",
        }).execute()
        self.client.table("calls").update({"status": "processed"}).eq("id", call_id).execute()

    # Slot memory helpers (kept in-process; can be persisted later if schema allows)
    def get_slot_memory(self, call_id: str) -> Dict[str, Any]:
        return self.slot_memory.get(call_id, {
            "driver_status": None,
            "current_location": None,
            "eta": None,
            "emergency_type": None,
            "emergency_location": None,
        })

    def update_slot_memory(self, call_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_slot_memory(call_id)
        merged = dict(current)
        for k, v in (updates or {}).items():
            if v is not None and v != "":
                merged[k] = v
        self.slot_memory[call_id] = merged
        return merged

    # Conversation state helpers (kept in process)
    def get_conversation_state(self, call_id: str) -> Dict[str, Any]:
        return self.conversation_state.get(call_id, {
            "last_prompted_slot": None,
            "prompt_retries": 0,
            "last_agent_message": None,
        })

    def update_conversation_state(self, call_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_conversation_state(call_id)
        merged = dict(current)
        for k, v in (updates or {}).items():
            merged[k] = v
        self.conversation_state[call_id] = merged
        return merged


_client: Optional[Client] = None
_db_instance: Optional[Any] = None


def get_db():
    global _client, _db_instance
    
    # Ensure environment variables are loaded
    from dotenv import load_dotenv
    load_dotenv()
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        if _client is None:
            _client = create_client(url, key)
        if _db_instance is None or not isinstance(_db_instance, SupabaseDB):
            _db_instance = SupabaseDB(_client)
        return _db_instance
    if _db_instance is None or not isinstance(_db_instance, InMemoryDB):
        _db_instance = InMemoryDB()
    return _db_instance
