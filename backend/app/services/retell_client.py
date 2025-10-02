import os
import httpx
from typing import Dict, Any, Optional
import json
import logging

# Set up logger
logger = logging.getLogger(__name__)


class RetellClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("RETELL_API_KEY")
        self.base_url = "https://api.retellai.com"
        self.simulated = not self.api_key or len(self.api_key.strip()) == 0
        
        if self.simulated:
            logger.info("RetellClient initialized in simulation mode (no API key provided)")
        else:
            logger.info("RetellClient initialized with API key")

    async def initiate_call(self, call_id: str, phone_number: str, agent_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Initiate a call through Retell AI"""
        logger.info(f"Attempting to initiate call {call_id} to {phone_number}")
        
        if self.simulated:
            # Simulated call initiation
            logger.info(f"Simulated call queued for {call_id} (SIMULATE_RETELL=true)")
            return {
                "call_id": call_id,
                "status": "queued",
                "message": "Simulated call queued (SIMULATE_RETELL=true)"
            }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        backend_url_env = os.getenv('BACKEND_URL', 'https://helpful-parliamentary-knowledgestorm-coordination.trycloudflare.com').rstrip('/')
        # If the env already includes the webhook path, use it as-is; otherwise append exactly once
        if backend_url_env.endswith('/api/retell/webhook'):
            webhook_url = backend_url_env
        else:
            webhook_url = f"{backend_url_env}/api/retell/webhook"

        from_number = os.getenv('RETELL_FROM_NUMBER')
        # Validate from_number early to avoid opaque Retell 400s
        if not from_number or not isinstance(from_number, str) or len(from_number.strip()) == 0:
            logger.error("RETELL_FROM_NUMBER is missing or empty. Set it to your Retell-assigned E.164 number (e.g., +14155550123)")
            raise ValueError("RETELL_FROM_NUMBER missing. Set backend env RETELL_FROM_NUMBER to your Retell phone number (E.164)")
        from_number = from_number.strip()

        payload = {
            "to_number": phone_number,     # destination number per Retell API
            "from_number": from_number,    # required by Retell API
            "call_id": call_id,
            "webhook_url": webhook_url,
            "agent_config": agent_config or self._get_default_agent_config()
        }

        # If a specific Retell agent is desired, attach it. Precedence: provided config > env
        agent_id_from_cfg = None
        try:
            if isinstance(agent_config, dict):
                agent_id_from_cfg = agent_config.get("agent_id") or agent_config.get("retell_agent_id")
        except Exception:
            agent_id_from_cfg = None
        agent_id_env = os.getenv("RETELL_AGENT_ID")
        agent_id = agent_id_from_cfg or agent_id_env
        if agent_id:
            payload["agent_id"] = agent_id

        # Include metadata to assist Custom LLM handler
        if isinstance(agent_config, dict):
            meta: Dict[str, Any] = {}
            if agent_config.get("agent_config_id"):
                meta["agent_config_id"] = agent_config.get("agent_config_id")
            if agent_config.get("driver_name"):
                meta["driver_name"] = agent_config.get("driver_name")
            if agent_config.get("load_number"):
                meta["load_number"] = agent_config.get("load_number")
            if meta:
                payload["metadata"] = meta
        
        logger.info(f"Calling Retell API with webhook URL: {webhook_url}")
        logger.debug(f"Retell API payload: {json.dumps(payload, indent=2)}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v2/create-phone-call",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                logger.info(f"Retell API response: {response.status_code}")
                response.raise_for_status()
                result = response.json()
                logger.info(f"Call initiated successfully: {result}")
                
                # Store the Retell call_id mapping
                retell_call_id = result.get("call_id")
                if retell_call_id:
                    from ..db import get_db
                    db = get_db()
                    db.update_retell_call_id(call_id, retell_call_id)
                    logger.info(f"Stored Retell call_id mapping: {call_id} -> {retell_call_id}")
                
                return result
        except httpx.HTTPStatusError as e:
            logger.error(f"Retell API HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Retell API request error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Retell API: {str(e)}")
            raise

    async def speak(self, call_id: str, text: str) -> None:
        """Send text to be spoken by the agent during the call"""
        logger.info(f"Agent speaking to call {call_id}: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        if self.simulated:
            logger.info(f"[SIMULATED] Agent speaking: {text}")
            return
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "call_id": call_id,
            "text": text
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v2/speak",
                    headers=headers,
                    json=payload,
                    timeout=10.0
                )
                logger.info(f"Speak API response: {response.status_code}")
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Error sending speak command: {str(e)}")
            raise

    async def end_call(self, call_id: str) -> None:
        """End the call"""
        logger.info(f"Ending call: {call_id}")
        
        if self.simulated:
            logger.info(f"[SIMULATED] Ending call: {call_id}")
            return
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v2/end-call",
                    headers=headers,
                    json={"call_id": call_id},
                    timeout=10.0
                )
                logger.info(f"End call API response: {response.status_code}")
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Error ending call: {str(e)}")
            raise

    async def create_or_update_agent(self, name: str, prompt_template: str, voice_settings: Dict[str, Any], agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a Retell agent (or update if agent_id provided) and return its details."""
        if self.simulated:
            return {"agent_id": "agent_simulated", "name": name}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload: Dict[str, Any] = {
            "name": name,
            "prompt": prompt_template,
        }
        # Map our voice_settings into Retell fields when available
        if voice_settings:
            payload["voice_settings"] = voice_settings
        
        # Add custom LLM WebSocket URL for dynamic responses
        backend_url_env = os.getenv('BACKEND_URL', 'https://engaging-termination-posing-win.trycloudflare.com').rstrip('/')
        websocket_url = backend_url_env.replace('https://', 'wss://').replace('http://', 'ws://')
        websocket_url = f"{websocket_url}/api/llm/retell/custom-llm"
        payload["custom_llm_dynamic_websocket_url"] = websocket_url

        url = f"{self.base_url}/v1/agents" if not agent_id else f"{self.base_url}/v1/agents/{agent_id}"
        method = "post" if not agent_id else "patch"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=headers, json=payload, timeout=20.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error creating/updating Retell agent: {str(e)}")
            raise

    async def assign_number_to_agent(self, from_number: str, agent_id: str) -> None:
        """Assign a provisioned phone number to a Retell agent for outbound calls.
        Tries common endpoints; logs details for debugging if provider shape differs.
        """
        if self.simulated:
            logger.info(f"[SIMULATED] Assigning {from_number} to agent {agent_id}")
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {"agent_id": agent_id, "from_number": from_number}
        try:
            async with httpx.AsyncClient() as client:
                # Attempt 1: a generic assign endpoint
                resp = await client.post(f"{self.base_url}/v1/phone-numbers/assign", headers=headers, json=payload, timeout=15.0)
                if 200 <= resp.status_code < 300:
                    return
                # Attempt 2: resource-specific PATCH
                safe_num = from_number.replace("+", "%2B")
                resp2 = await client.patch(f"{self.base_url}/v1/phone-numbers/{safe_num}", headers=headers, json={"agent_id": agent_id}, timeout=15.0)
                resp2.raise_for_status()
        except Exception as e:
            logger.error(f"Error assigning number {from_number} to agent {agent_id}: {str(e)}")
            raise

    async def resolve_agent_id_for_from_number(self, from_number: str) -> Optional[str]:
        """Return the agent id currently assigned to a provisioned phone number, if any."""
        if self.simulated:
            return None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        safe_num = from_number.replace("+", "%2B")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/v1/phone-numbers/{safe_num}", headers=headers, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                # Common shapes: { agent_id: "agent_..." } or nested under number settings
                return data.get("agent_id") or data.get("outbound_agent_id") or (data.get("settings") or {}).get("agent_id")
        except Exception as e:
            logger.error(f"Error resolving agent by number {from_number}: {str(e)}")
            return None

    def _get_default_agent_config(self) -> Dict[str, Any]:
        """Get default agent configuration for Retell AI"""
        backend_url_env = os.getenv('BACKEND_URL', 'https://engaging-termination-posing-win.trycloudflare.com').rstrip('/')
        # Convert https:// to wss:// for WebSocket connections
        websocket_url = backend_url_env.replace('https://', 'wss://').replace('http://', 'ws://')
        websocket_url = f"{websocket_url}/api/llm/retell/custom-llm"
        
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
            },
            "custom_llm_dynamic_websocket_url": websocket_url
        }


