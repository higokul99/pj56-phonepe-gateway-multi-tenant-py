from fastapi import APIRouter
from sqlalchemy import text
from app import __version__
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.redis import get_redis
from app.schemas.common import ApiResponse, HealthCheckResponse

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "/healthz",
    response_model=ApiResponse[HealthCheckResponse],
    summary="Health check probe",
    description="Liveness and readiness check for load balancers and orchestrators.",
)
async def health_check():
    db_status = "ok"
    redis_status = "ok"

    # Check DB
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)[:50]}"

    # Check Redis
    try:
        redis_mgr = await get_redis()
        pong = await redis_mgr.set("healthcheck", "ok", ex=10)
        if not pong:
            redis_status = "degraded (in-memory)"
    except Exception as e:
        redis_status = f"error: {str(e)[:50]}"

    all_healthy = db_status == "ok" and ("ok" in redis_status or "degraded" in redis_status)

    return ApiResponse(
        success=all_healthy,
        data=HealthCheckResponse(
            status="healthy" if all_healthy else "unhealthy",
            version=__version__,
            environment=settings.APP_ENV,
            database=db_status,
            redis=redis_status,
        ),
    )
