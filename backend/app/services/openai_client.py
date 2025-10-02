import os
import json
from typing import Dict, Any
from tenacity import retry, wait_exponential, stop_after_attempt
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


REALTIME_SYSTEM_PROMPT = (
    "You are an adaptive telephony dispatch agent. Use the admin-provided prompt template {prompt_template} "
    "(inserted here with variables populated: {driver_name}, {load_number}, {call_history}, {last_driver_utterance}). "
    "Speak concisely, use backchanneling but avoid long monologues. If the driver gives an emergency signal, immediately "
    "switch to Emergency Protocol (see Emergency Protocol template below). Always produce a JSON object exactly like:\n\n"
    "{{\n  \"agent_text\": \"<text the agent should say out loud>\",\n  \"action\": \"continue\" | \"ask_followup\" | \"escalate\" | \"end_call\",\n  \"followup_question\": \"<optional question for driver>\",\n  \"notes_for_logging\": \"<any brief notes>\"\n}}\n"
)

EMERGENCY_SYSTEM_PROMPT = (
    "Emergency detected. Switch to Emergency Protocol.\n"
    "Ask directly for and attempt to extract:\n"
    "- emergency_type: Accident | Breakdown | Medical | Other\n"
    "- emergency_location: (free text; be specific)\n"
    "- immediate danger or injuries: yes/no\n"
    "- whether truck is blocking road: yes/no\n"
    "End by clearly stating: \"A human dispatcher will call you back immediately.\" Then set \"action\":\"escalate\" and return JSON:\n"
    "{\n  \"agent_text\": \"<spoken text>\",\n  \"action\": \"escalate\",\n  \"structured_emergency\": {\n     \"emergency_type\": \"<...>\",\n     \"emergency_location\": \"<...>\",\n     \"injuries\": \"<yes/no/unknown>\",\n     \"notes\": \"<raw extracted text>\"\n  }\n}\n"
)

POSTCALL_SYSTEM_PROMPT = (
    "You are a post-call summarization assistant. Given the full final transcript, produce one JSON object with keys below exactly as shown.\n\n"
    "PRODUCE:\n{\n  \"call_outcome\": \"In-Transit Update\" | \"Arrival Confirmation\" | \"Emergency Detected\" | \"No Response\" | \"Unknown\",\n  \"driver_status\": \"Driving\" | \"Delayed\" | \"Arrived\" | null,\n  \"current_location\": \"<string|null>\",\n  \"eta\": \"<string|null>\",\n  \"emergency_type\": \"Accident\" | \"Breakdown\" | \"Medical\" | \"Other\" | null,\n  \"emergency_location\": \"<string|null>\",\n  \"escalation_status\": \"Escalation Flagged\" | null,\n  \"extraction_notes\": \"<brief text>\"\n}\n\n"
    "Use the evidence from the transcript. If the call involved an emergency, set call_outcome to \"Emergency Detected\" and populate emergency_* fields. If unknown, set fields to null. Keep the JSON minimal and machine-readable: no explanations outside the JSON."
)


class OpenAIClient:
    def __init__(self) -> None:
        # Try Groq first (free), fallback to OpenAI
        groq_key = os.getenv("GROQ_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        
        # Debug: Check API keys (remove in production)
        if groq_key:
            print(f"OpenAIClient: Using Groq API")
        elif openai_key:
            print(f"OpenAIClient: Using OpenAI API")
        else:
            print(f"OpenAIClient: Using simulated responses")
        
        if groq_key and len(groq_key.strip()) > 0:
            # Use Groq (free alternative)
            self.client = AsyncOpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1"
            )
            self.model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
            self.simulated = False
            print("Using Groq LLM (free)")
        elif openai_key and len(openai_key.strip()) > 0:
            # Use OpenAI
            self.client = AsyncOpenAI(api_key=openai_key)
            self.model = "gpt-4o-mini"
            self.simulated = False
            print("Using OpenAI")
        else:
            # No API keys, use simulation
            self.client = None
            self.model = None
            self.simulated = True
            print("Using simulated responses (no API keys)")

    @retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
    async def decide_next_action(self, context: Dict[str, Any], last_driver_utterance: str) -> Dict[str, Any]:
        # Normalize context to avoid KeyError in string formatting
        safe_context = {
            "prompt_template": (context or {}).get("prompt_template", ""),
            "driver_name": (context or {}).get("driver_name", ""),
            "load_number": (context or {}).get("load_number", ""),
            "call_history": (context or {}).get("call_history", ""),
        }
        if self.simulated:
            # Simple rule-based simulated response
            text = last_driver_utterance.lower()
            if "arrived" in text:
                return {"agent_text": "Thanks for the update. Ending the call.", "action": "end_call"}
            return {"agent_text": "Got it. Any delays or ETA?", "action": "ask_followup"}
        messages = [
            {"role": "system", "content": REALTIME_SYSTEM_PROMPT.format(**safe_context, last_driver_utterance=last_driver_utterance)},
            {"role": "user", "content": f"Call context:\n- driver_name: {context.get('driver_name')}\n- load_number: {context.get('load_number')}\n- last_driver_utterance: \"{last_driver_utterance}\"\n- call_history: \"{context.get('call_history')}\"\nNow respond with the JSON only."},
        ]
        
        try:
            chat = await self.client.chat.completions.create(
                model=self.model, 
                messages=messages, 
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=500
            )
        except Exception as e:
            print(f"API call failed: {type(e).__name__}: {str(e)}")
            raise
        # Some SDKs put JSON under .content as a string, ensure dict
        content = getattr(chat.choices[0].message, "parsed", None) or chat.choices[0].message.content
        if isinstance(content, str):
            try:
                return json.loads(content)
            except Exception:
                return {"agent_text": content, "action": "continue"}
        return content

    async def emergency_protocol(self) -> Dict[str, Any]:
        if self.simulated:
            return {
                "agent_text": "Emergency noted. A human dispatcher will call you back immediately.",
                "action": "escalate",
                "structured_emergency": {
                    "emergency_type": "Breakdown",
                    "emergency_location": None,
                    "injuries": "unknown",
                    "notes": "Simulated emergency",
                },
            }
        chat = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": EMERGENCY_SYSTEM_PROMPT}],
            response_format={"type": "json_object"},
        )
        return chat.choices[0].message.parsed if hasattr(chat.choices[0].message, "parsed") else chat.choices[0].message.content  # type: ignore

    @retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
    async def summarize(self, transcript_text: str) -> Dict[str, Any]:
        if self.simulated:
            # Heuristic simulated summarizer
            text = transcript_text.lower()
            if "blowout" in text or "accident" in text:
                return {
                    "call_outcome": "Emergency Detected",
                    "driver_status": None,
                    "current_location": None,
                    "eta": None,
                    "emergency_type": "Breakdown",
                    "emergency_location": "I-15 North, Mile Marker 123" if "123" in text else None,
                    "escalation_status": "Escalation Flagged",
                    "extraction_notes": "Driver reported blowout and pulled over, no injuries.",
                }
            if "indio" in text or "i-10" in text:
                return {
                    "call_outcome": "In-Transit Update",
                    "driver_status": "Driving",
                    "current_location": "I-10 near Indio, CA",
                    "eta": "Tomorrow, 8:00 AM",
                    "emergency_type": None,
                    "emergency_location": None,
                    "escalation_status": None,
                    "extraction_notes": "Clear in-transit update.",
                }
            return {
                "call_outcome": "Unknown",
                "driver_status": None,
                "current_location": None,
                "eta": None,
                "emergency_type": None,
                "emergency_location": None,
                "escalation_status": None,
                "extraction_notes": "Simulated summarizer could not determine.",
            }
        chat = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": POSTCALL_SYSTEM_PROMPT}, {"role": "user", "content": transcript_text}],
            response_format={"type": "json_object"},
        )
        return chat.choices[0].message.parsed if hasattr(chat.choices[0].message, "parsed") else chat.choices[0].message.content  # type: ignore
