from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID


class AgentConfigBase(BaseModel):
    name: str
    description: Optional[str] = None
    prompt_template: str
    voice_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AgentConfigCreate(AgentConfigBase):
    pass


class AgentConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt_template: Optional[str] = None
    voice_settings: Optional[Dict[str, Any]] = None


class AgentConfigRead(AgentConfigBase):
    id: str
    created_at: Optional[str]
    updated_at: Optional[str]


class CallStartRequest(BaseModel):
    driver_name: str
    phone_number: str
    load_number: Optional[str] = None
    agent_config_id: str


class TranscriptSegment(BaseModel):
    text: str
    speaker: str
    timestamp: Optional[str]
    confidence: Optional[float]


class CallRead(BaseModel):
    id: str
    driver_name: str
    phone_number: str
    load_number: Optional[str]
    agent_config_id: Optional[str]
    status: str
    created_at: Optional[str]
    events: Optional[List[Dict[str, Any]]] = None
    full_transcript: Optional[List[TranscriptSegment]] = None
    structured_summary: Optional[Dict[str, Any]] = None


class CallListResponse(BaseModel):
    items: List[CallRead]
    total: int
    page: int
    page_size: int
