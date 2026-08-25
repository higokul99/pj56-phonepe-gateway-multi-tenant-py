import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app import __version__
from app.api.admin import admin_router
from app.api.health import router as health_router
from app.api.v1 import api_v1_router
from app.config import get_settings
from app.core.exceptions import PaymentGatewayException
from app.core.logging import logger
from app.redis import redis_manager
from app.services.reconciliation import run_reconciliation_loop

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{__version__} in [{settings.APP_ENV}] mode")
    await redis_manager.connect()

    # Launch reconciliation worker if enabled
    reconciliation_task = None
    if settings.ENABLE_BACKGROUND_RECONCILIATION:
        reconciliation_task = asyncio.create_task(run_reconciliation_loop())

    yield

    # Shutdown
    logger.info("Shutting down microservice...")
    if reconciliation_task:
        reconciliation_task.cancel()
        try:
            await reconciliation_task
        except asyncio.CancelledError:
            pass

    await redis_manager.close()


app = FastAPI(
    title="PhonePe Payment Gateway Microservice",
    description=(
        "Standalone multi-tenant microservice wrapping PhonePe's Standard Checkout API (OAuth-based). "
        "Allows merchant websites to initiate payments, track statuses, handle refunds, and receive signed webhooks."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def audit_and_access_log_middleware(request: Request, call_next):
    """Logs incoming requests with timing and key prefixes without logging secrets."""
    start_time = time.time()
    response: Response = await call_next(request)
    process_time = (time.time() - start_time) * 1000

    key_prefix = getattr(request.state, "key_prefix", "unauthenticated")
    tenant_id = getattr(request.state, "tenant_id", "-")

    logger.info(
        f'{request.method} {request.url.path} -> {response.status_code} '
        f'[{process_time:.2f}ms] tenant={tenant_id} key={key_prefix}'
    )
    return response


# --- Exception Handlers ---

@app.exception_handler(PaymentGatewayException)
async def payment_gateway_exception_handler(request: Request, exc: PaymentGatewayException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        errors.append(f"{loc}: {err.get('msg')}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation error",
                "details": {"errors": errors},
            },
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred",
                "details": {},
            },
        },
    )


from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import os

# Mount static assets directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    return RedirectResponse(url="/static/index.html")


@app.get("/admin", include_in_schema=False)
async def admin_page():
    return RedirectResponse(url="/static/index.html")


# --- Register Routers ---
app.include_router(health_router)
app.include_router(api_v1_router)
app.include_router(admin_router)

