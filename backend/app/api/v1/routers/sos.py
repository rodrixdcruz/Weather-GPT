import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.models import SosEvent
from app.schemas.schemas import SosRequest, SosResponse

router = APIRouter(prefix="/sos", tags=["sos"])
log = get_logger(__name__)


@router.post("/trigger", response_model=SosResponse)
async def trigger_sos(payload: SosRequest, db: Session = Depends(get_db)):
    """Log an SOS event.

    CRITICAL: `dispatched` is only ever True if `SOS_DISPATCH_ENABLED`
    is set AND a real call to the dispatch webhook succeeds. The API
    and the frontend must never claim help was actually notified
    otherwise — see product constraints.
    """
    settings = get_settings()
    event = SosEvent(
        id=str(uuid.uuid4()),
        user_id=payload.user_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        note=payload.note,
        dispatched=False,
    )

    dispatched = False
    dispatch_provider = None

    if settings.SOS_DISPATCH_ENABLED and settings.SOS_DISPATCH_WEBHOOK_URL:
        # TODO: integrate a real dispatch service here (e.g. NDMA/NDRF
        # API, Twilio, a district control-room webhook) and set
        # `dispatched = True` only after a confirmed successful call.
        dispatch_provider = "not_configured"
        dispatched = False

    event.dispatched = dispatched
    event.dispatch_provider = dispatch_provider
    db.add(event)
    db.commit()

    log.warning("sos.trigger id=%s lat=%.4f lon=%.4f dispatched=%s", event.id, payload.latitude, payload.longitude, dispatched)

    message = (
        "Your SOS event was logged with your current location and a real dispatch service confirmed delivery."
        if dispatched
        else "Your SOS event was logged with your current location. No live dispatch service is connected yet, so no real alert was sent — use the emergency contacts shown for immediate help."
    )

    return SosResponse(id=event.id, logged=True, dispatched=dispatched, message=message)
