from fastapi import APIRouter
from app.api.v1.orders import router as orders_router
from app.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter()
api_v1_router.include_router(orders_router)
api_v1_router.include_router(webhooks_router)
