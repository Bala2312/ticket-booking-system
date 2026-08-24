from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import redis.asyncio as aioredis
from datetime import datetime, timezone
from typing import Optional

from app.database import get_db, get_redis, engine, Base
from app.services.seat_service import SeatService
from app.services.notification_service import NotificationService
from app.models import User, Venue, Seat, Show, ShowSeat, SeatStatus, Role

app = FastAPI(title="Ticket Booking Platform API", version="1.0.0")


class SetupRequest(BaseModel):
    show_id: str = "sh1"
    venue_id: str = "v1"
    seat_id: str = "s1"
    price: float = 100.0


class HoldSeatsRequest(BaseModel):
    user_id: str
    show_id: str
    seat_ids: list[str]


class ConfirmBookingRequest(BaseModel):
    user_id: str
    show_id: str
    seat_ids: list[str]
    recipient_email: Optional[str] = "customer@example.com"
    event_title: Optional[str] = "Live Concert Ticket"


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


@app.post("/api/admin/setup")
async def admin_setup(payload: SetupRequest, db: AsyncSession = Depends(get_db)):
    try:
        # 1. Ensure test users exist
        for uid in ["user_101", "user_202"]:
            user = await db.get(User, uid)
            if not user:
                db.add(
                    User(
                        id=uid,
                        email=f"{uid}@test.com",
                        password="password",
                        name=f"User {uid}",
                        role=Role.CUSTOMER,
                    )
                )

        # 2. Ensure Venue exists
        venue = await db.get(Venue, payload.venue_id)
        if not venue:
            venue = Venue(
                id=payload.venue_id,
                name="Main Arena",
                location="Downtown",
                capacity=100,
            )
            db.add(venue)

        # 3. Ensure Seat exists
        seat = await db.get(Seat, payload.seat_id)
        if not seat:
            seat = Seat(
                id=payload.seat_id,
                venue_id=payload.venue_id,
                row="A",
                number=1,
                category="VIP",
            )
            db.add(seat)

        # 4. Ensure Show exists
        show = await db.get(Show, payload.show_id)
        if not show:
            show = Show(
                id=payload.show_id,
                title="Live Event",
                start_time=datetime.now(timezone.utc),
                venue_id=payload.venue_id,
                organiser_id="user_101",
            )
            db.add(show)

        # 5. Ensure ShowSeat mapping exists or reset to AVAILABLE
        show_seat_id = f"{payload.show_id}_{payload.seat_id}"
        show_seat = await db.get(ShowSeat, show_seat_id)
        if not show_seat:
            show_seat = ShowSeat(
                id=show_seat_id,
                show_id=payload.show_id,
                seat_id=payload.seat_id,
                price=payload.price,
                status=SeatStatus.AVAILABLE,
            )
            db.add(show_seat)
        else:
            show_seat.status = SeatStatus.AVAILABLE

        await db.commit()
        return {
            "status": "success",
            "message": f"Created Show '{payload.show_id}' and Seat '{payload.seat_id}'.",
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Database setup failed: {str(e)}"
        )


@app.post("/api/seats/hold")
async def hold_seats(
    payload: HoldSeatsRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
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
    redis_client: aioredis.Redis = Depends(get_redis),
):
    try:
        # 1. Process booking logic in Database & Redis
        booking = await SeatService.confirm_booking(
            db, redis_client, payload.user_id, payload.show_id, payload.seat_ids
        )

        # 2. Extract booking reference safely from dict or object
        if isinstance(booking, dict):
            booking_ref = (
                booking.get("reference")
                or booking.get("booking_reference")
                or booking.get("id")
                or "CONFIRMED"
            )
        else:
            booking_ref = getattr(
                booking, "reference", getattr(booking, "id", "CONFIRMED")
            )

        # 3. Attempt email dispatch safely
        try:
            await NotificationService.send_ticket_email(
                payload.recipient_email, booking_ref, payload.event_title
            )
        except Exception as mail_err:
            print(f"[Warning] Email sending failed: {mail_err}")

        return {"success": True, "booking_reference": booking_ref}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")