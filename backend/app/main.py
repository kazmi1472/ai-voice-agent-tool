from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import api_router
from dotenv import load_dotenv
import os
import logging

# Load environment variables from .env (if present)
# Try to load from the project root first, then current directory
import pathlib
project_root = pathlib.Path(__file__).parent.parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"Loaded .env from: {env_path}")
else:
    load_dotenv()
    print("Loaded .env from current directory")

# Debug: Check if GROQ_API_KEY is loaded (remove in production)
groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    print(f"GROQ_API_KEY loaded successfully")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

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
