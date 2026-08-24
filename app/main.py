from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import redis.asyncio as aioredis

from app.database import get_db, get_redis, engine, Base
from app.services.seat_service import SeatService
from app.services.notification_service import NotificationService

app = FastAPI(title="Ticket Booking Platform API", version="1.0.0")

class HoldSeatsRequest(BaseModel):
    user_id: str
    show_id: str
    seat_ids: list[str]

class ConfirmBookingRequest(BaseModel):
    user_id: str
    show_id: str
    seat_ids: list[str]
    recipient_email: str
    event_title: str

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def root():
    return {"message": "Ticket Booking Platform API is operational."}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "engine": "FastAPI + PostgreSQL + Redis"}

@app.post("/api/seats/hold")
async def hold_seats(
    payload: HoldSeatsRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis)
):
    try:
        res = await SeatService.hold_seats(
            db, redis_client, payload.user_id, payload.show_id, payload.seat_ids
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/bookings/confirm")
async def confirm_booking(
    payload: ConfirmBookingRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis)
):
    try:
        booking = await SeatService.confirm_booking(
            db, redis_client, payload.user_id, payload.show_id, payload.seat_ids
        )
        await NotificationService.send_ticket_email(
            payload.recipient_email, booking.reference, payload.event_title
        )
        return {"success": True, "booking_reference": booking.reference}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))