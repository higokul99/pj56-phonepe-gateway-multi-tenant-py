from fastapi import APIRouter
from app.api.admin.auth import router as auth_router
from app.api.admin.keys import router as keys_admin_router
from app.api.admin.orders_admin import router as orders_admin_router
from app.api.admin.stats import router as stats_router
from app.api.admin.tenants import router as tenants_admin_router
from app.api.admin.webhooks_admin import router as webhooks_admin_router

admin_router = APIRouter()
admin_router.include_router(auth_router)
admin_router.include_router(stats_router)
admin_router.include_router(tenants_admin_router)
admin_router.include_router(keys_admin_router)
admin_router.include_router(orders_admin_router)
admin_router.include_router(webhooks_admin_router)
