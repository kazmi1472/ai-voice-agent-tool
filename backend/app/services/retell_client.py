import os
import httpx
from typing import Dict, Any, Optional
import json


class RetellClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("RETELL_API_KEY")
        self.base_url = "https://api.retellai.com"
        self.simulated = not self.api_key or len(self.api_key.strip()) == 0

    async def initiate_call(self, call_id: str, phone_number: str, agent_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Initiate a call through Retell AI"""
        if self.simulated:
            # Simulated call initiation
            return {
                "call_id": call_id,
                "status": "queued",
                "message": "Simulated call queued (SIMULATE_RETELL=true)"
            }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "phone_number": phone_number,
            "call_id": call_id,
            "webhook_url": f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/api/retell/webhook",
            "agent_config": agent_config or self._get_default_agent_config()
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v2/create-phone-call",
                headers=headers,
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def speak(self, call_id: str, text: str) -> None:
        """Send text to be spoken by the agent during the call"""
        if self.simulated:
            print(f"[SIMULATED] Agent speaking: {text}")
            return
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "call_id": call_id,
            "text": text
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v2/speak",
                headers=headers,
                json=payload,
                timeout=10.0
            )
            response.raise_for_status()

    async def end_call(self, call_id: str) -> None:
        """End the call"""
        if self.simulated:
            print(f"[SIMULATED] Ending call: {call_id}")
            return
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v2/end-call",
                headers=headers,
                json={"call_id": call_id},
                timeout=10.0
            )
            response.raise_for_status()

    def _get_default_agent_config(self) -> Dict[str, Any]:
        """Get default agent configuration for Retell AI"""
        return {
            "voice_id": "sarah",  # Default voice
            "voice_settings": {
                "speed": 1.0,
                "volume": 1.0,
                "pitch": 1.0
            },
            "advanced_settings": {
                "backchanneling": True,
                "filler_words_allowed": False,
                "interruption_sensitivity": "medium"
            }
        }


