import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api.v1.router import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context managing startup and shutdown tasks."""
    setup_logging()
    settings = get_settings()
    logger.info(f"Starting {settings.APP_NAME} in [{settings.ENVIRONMENT}] mode.")
    
    # Ensure all SQLAlchemy models are registered
    try:
        import app.payments.models
        import app.whatsapp.models
    except Exception as e:
        logger.warning(f"[VERITAS] Model import warning: {e}")

    # Automatically activate ARGUS and ACCORD subsystems
    try:
        from app.argus.database import init_db as init_argus_db
        init_argus_db()
        logger.info("[VERITAS] ARGUS Active: Global Trust Registry & 4-Worker Forensic Engine initialized.")
    except Exception as e:
        logger.warning(f"[VERITAS] ARGUS DB warning: {e}")

    logger.info("[VERITAS] ACCORD Active: Conversational Ingestion & Expense Splits initialized.")

    # Automatically start ARQ worker in background for asynchronous tasks (e.g. Gemini analysis)
    arq_worker = None
    arq_task = None
    try:
        from arq.worker import create_worker
        from app.core.tasks.worker import WorkerSettings
        arq_worker = create_worker(WorkerSettings)
        arq_task = asyncio.create_task(arq_worker.async_run())
        logger.info("[VERITAS] ARQ Background Worker active and listening on Redis queue.")
    except Exception as e:
        logger.warning(f"[VERITAS] ARQ worker could not be started: {e}")

    yield

    if arq_worker:
        try:
            await arq_worker.close()
            if arq_task:
                await arq_task
        except Exception as e:
            logger.warning(f"[VERITAS] Error closing ARQ worker: {e}")

    logger.info(f"Shutting down {settings.APP_NAME}.")


def create_application() -> FastAPI:
    """Application factory for VERITAS FastAPI backend."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description="VERITAS Unified Trust & Transactional Intelligence Platform API",
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Configure CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------------------------
    # Centralized Error Handlers
    # --------------------------------------------------------------------------
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                    "details": getattr(exc, "extra", None),
                },
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "Input validation failed. Please check the provided fields.",
                    "details": jsonable_encoder(exc.errors()),
                },
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled server error: {exc}")
        settings = get_settings()
        message = str(exc) if settings.DEBUG else "An internal server error occurred."
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": message,
                    "details": None,
                },
            },
        )

    # --------------------------------------------------------------------------
    # Route Registration
    # --------------------------------------------------------------------------
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Mount static assets and Argus UI Dashboard
    import os
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    static_dir = os.path.join(workspace_root, "static")
    dist_dir = os.path.join(workspace_root, "Veritas", "frontend", "dist")

    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
        js_dir = os.path.join(static_dir, "js")
        if os.path.exists(js_dir):
            app.mount("/js", StaticFiles(directory=js_dir), name="js")

        @app.get("/argus", tags=["ARGUS UI"])
        @app.get("/argus/simulator", tags=["ARGUS UI"])
        async def serve_argus_ui():
            return FileResponse(os.path.join(static_dir, "index.html"))

    # Mount React Frontend if built dist exists
    if os.path.exists(dist_dir):
        assets_dir = os.path.join(dist_dir, "assets")
        if os.path.exists(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/", tags=["VERITAS UI"])
        @app.get("/veritas", tags=["VERITAS UI"])
        @app.get("/accord", tags=["ACCORD UI"])
        @app.get("/accord/ingest", tags=["ACCORD UI"])
        async def serve_veritas_react_ui():
            return FileResponse(os.path.join(dist_dir, "index.html"))

    @app.get("/status", tags=["Root"])
    @app.get("/api/status", tags=["Root"])
    async def system_status():
        return {
            "platform": "VERITAS Unified Platform",
            "version": "1.0.0",
            "status": "ALL_SYSTEMS_ACTIVE",
            "subsystems": {
                "accord": {
                    "name": "ACCORD Conversational Financial Agreements",
                    "status": "ACTIVE",
                    "docs": f"{settings.API_V1_STR}/accord"
                },
                "argus": {
                    "name": "ARGUS Pre-Settlement Fraud Interceptor",
                    "status": "ACTIVE",
                    "simulator_ui": "/argus",
                    "docs": f"{settings.API_V1_STR}/argus"
                }
            },
            "docs_url": "/docs",
            "api_v1": settings.API_V1_STR,
        }

    return app


app = create_application()

