from fastapi import APIRouter, HTTPException
from typing import List
from ..schemas.pydantic_schemas import AgentConfigCreate, AgentConfigRead, AgentConfigUpdate
from ..db import get_db
from uuid import UUID

router = APIRouter()

@router.get("/", response_model=List[AgentConfigRead])
async def list_configs():
    db = get_db()
    rows = db.list_agent_configs()
    return rows

@router.post("/", response_model=AgentConfigRead)
async def create_config(body: AgentConfigCreate):
    db = get_db()
    return db.create_agent_config(body)

@router.put("/{config_id}", response_model=AgentConfigRead)
async def update_config(config_id: UUID, body: AgentConfigUpdate):
    db = get_db()
    updated = db.update_agent_config(config_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail="Agent config not found")
    return updated

@router.delete("/{config_id}")
async def delete_config(config_id: UUID):
    db = get_db()
    ok = db.delete_agent_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent config not found")
    return {"deleted": True}
