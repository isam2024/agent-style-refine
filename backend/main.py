import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.config import settings
from backend.routers import (
    sessions_router,
    extraction_router,
    generation_router,
    critique_router,
    iteration_router,
)
from backend.routers.styles import router as styles_router
from backend.websocket import websocket_endpoint
from backend.services.vlm import vlm_service
from backend.services.comfyui import comfyui_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Set specific loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Style Refine Agent...")
    logger.info(f"Ollama URL: {settings.ollama_url}")
    logger.info(f"ComfyUI URL: {settings.comfyui_url}")
    logger.info(f"VLM Model (vision): {settings.vlm_model}")
    logger.info(f"Text Model (prompts): {settings.text_model}")

    await init_db()
    logger.info("Database initialized")

    settings.ensure_outputs_dir()
    logger.info(f"Outputs directory: {settings.outputs_dir}")

    # Check services on startup
    vlm_ok = await vlm_service.health_check()
    comfyui_ok = await comfyui_service.health_check()

    if vlm_ok:
        logger.info("Ollama: Connected")
        model_info = await vlm_service.check_model()
        if model_info.get("vlm_model_found"):
            logger.info(f"Vision Model '{settings.vlm_model}': Available")
        else:
            logger.warning(f"Vision Model '{settings.vlm_model}': NOT FOUND")
        if model_info.get("text_model_found"):
            logger.info(f"Text Model '{settings.text_model}': Available")
        else:
            logger.warning(f"Text Model '{settings.text_model}': NOT FOUND")
        if not model_info.get("vlm_model_found") or not model_info.get("text_model_found"):
            logger.warning(f"Available models: {model_info.get('available_models', [])}")
    else:
        logger.error("Ollama: NOT CONNECTED - VLM features will fail")

    if comfyui_ok:
        logger.info("ComfyUI: Connected")
    else:
        logger.warning("ComfyUI: NOT CONNECTED - Image generation will fail")

    logger.info("Startup complete")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Style Refine Agent",
    description="A self-updating Style Agent for iterative image style refinement",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1442", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sessions_router)
app.include_router(extraction_router)
app.include_router(generation_router)
app.include_router(critique_router)
app.include_router(iteration_router)
app.include_router(styles_router)


@app.get("/")
async def root():
    return {
        "name": "Style Refine Agent API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Check health of backend and dependent services."""
    vlm_ok = await vlm_service.health_check()
    comfyui_ok = await comfyui_service.health_check()
    model_info = await vlm_service.check_model()

    return {
        "status": "ok" if vlm_ok and comfyui_ok else "degraded",
        "services": {
            "ollama": {
                "status": "ok" if vlm_ok else "unavailable",
                "url": settings.ollama_url,
                "vlm_model": settings.vlm_model,
                "vlm_model_found": model_info.get("vlm_model_found", False),
                "text_model": settings.text_model,
                "text_model_found": model_info.get("text_model_found", False),
                "available_models": model_info.get("available_models", []),
            },
            "comfyui": {
                "status": "ok" if comfyui_ok else "unavailable",
                "url": settings.comfyui_url,
            },
        },
    }


@app.get("/health/vlm")
async def vlm_health():
    """Detailed VLM health check."""
    return await vlm_service.check_model()


@app.get("/health/vlm/status")
async def vlm_status():
    """Get VLM status including active requests and Ollama processes."""
    return await vlm_service.get_status()


@app.post("/health/vlm/cancel")
async def vlm_cancel_requests():
    """Cancel all active VLM requests."""
    active_before = len(vlm_service.get_active_requests())
    vlm_service.cancel_all_requests()
    return {
        "status": "cancelled",
        "requests_cancelled": active_before,
    }


@app.websocket("/ws/{session_id}")
async def websocket_route(websocket: WebSocket, session_id: str):
    await websocket_endpoint(websocket, session_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=1443,
        reload=True,
        log_level="info",
    )
