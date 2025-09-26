import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_agent_config_crud():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        payload = {
            "name": "Default Agent",
            "description": "Test agent",
            "prompt_template": "Hello {driver_name}",
            "voice_settings": {"backchanneling": True}
        }
        res = await ac.post("/api/agent-configs/", json=payload)
        assert res.status_code == 200
        cfg = res.json()

        res = await ac.get("/api/agent-configs/")
        assert res.status_code == 200
        lst = res.json()
        assert len(lst) >= 1

        res = await ac.put(f"/api/agent-configs/{cfg['id']}", json={"description": "Updated"})
        assert res.status_code == 200

        res = await ac.delete(f"/api/agent-configs/{cfg['id']}")
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_call_start_and_webhook_flow():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create config
        res = await ac.post("/api/agent-configs/", json={
            "name": "Check-in Agent",
            "description": "",
            "prompt_template": "Dispatch check-in for {driver_name} on {load_number}",
            "voice_settings": {"backchanneling": True}
        })
        cfg = res.json()

        # Start call (simulate mode)
        res = await ac.post("/api/calls/start?mode=local", json={
            "driver_name": "Mike",
            "phone_number": "+15551234567",
            "load_number": "7891-B",
            "agent_config_id": cfg["id"],
        })
        assert res.status_code == 202
        call_id = res.json()["call_id"]

        # Simulate speech with blowout to trigger emergency
        event = {
            "event_type": "speech",
            "call_id": call_id,
            "timestamp": "2025-09-24T12:34:56Z",
            "payload": {"speech_text": "I just had a blowout on I-15 North mile 123", "stable": True, "confidence": 0.92, "speaker": "driver"}
        }
        res = await ac.post("/api/retell/webhook", json=event)
        assert res.status_code == 200

        # Call should be processed
        res = await ac.get(f"/api/calls/{call_id}")
        assert res.status_code == 200
        detail = res.json()
        assert detail["structured_summary"] is not None
        assert detail["structured_summary"].get("call_outcome") in ("Emergency Detected", "In-Transit Update", "Unknown")
