from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import api_router
from dotenv import load_dotenv
import os

# Load environment variables from backend/.env (if present)
load_dotenv()

app = FastAPI(title="AI Voice Agent Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    return {"status": "ok"}
