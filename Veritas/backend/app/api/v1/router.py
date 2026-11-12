from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.accord.router import router as accord_router
from app.payments.router import router as payments_router
from app.payments.router import accord_payments_router
from app.whatsapp.router import router as whatsapp_router
from app.argus.router import router as argus_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(accord_router, prefix="/accord")
api_router.include_router(payments_router)
api_router.include_router(accord_payments_router)
api_router.include_router(whatsapp_router, prefix="/whatsapp")

# ARGUS Autonomous Fraud Interceptor (both /argus prefix and direct aliases)
api_router.include_router(argus_router, prefix="/argus")
api_router.include_router(argus_router)


