from fastapi import APIRouter

from app.api.v1.routers import admin, auth, chat, geo, risk, routing, safe_zones, safety, sos, weather

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(weather.router)
api_router.include_router(geo.router)
api_router.include_router(risk.router)
api_router.include_router(safety.router)
api_router.include_router(chat.router)
api_router.include_router(safe_zones.router)
api_router.include_router(routing.router)
api_router.include_router(sos.router)
