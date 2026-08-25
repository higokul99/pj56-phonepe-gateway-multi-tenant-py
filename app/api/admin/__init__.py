from fastapi import APIRouter
from app.api.admin.tenants import router as tenants_admin_router
from app.api.admin.keys import router as keys_admin_router

admin_router = APIRouter()
admin_router.include_router(tenants_admin_router)
admin_router.include_router(keys_admin_router)
