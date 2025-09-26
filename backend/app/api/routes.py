from fastapi import APIRouter
from .agent_configs import router as agent_configs_router
from .calls import router as calls_router
from .webhook import router as webhook_router

api_router = APIRouter()
api_router.include_router(agent_configs_router, prefix="/agent-configs", tags=["agent-configs"]) 
api_router.include_router(calls_router, prefix="/calls", tags=["calls"]) 
api_router.include_router(webhook_router, prefix="/retell", tags=["retell"]) 
