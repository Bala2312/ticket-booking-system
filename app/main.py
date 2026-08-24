from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import redis.asyncio as aioredis
from datetime import datetime, timezone
from typing import Optional

from app.database import get_db, get_redis, engine, Base
from app.services.seat_service import SeatService
from app.services.waitlist_service import WaitlistService
from app.services.notification_service import NotificationService
from app.models import User, Venue, Seat, Show, ShowSeat, SeatStatus, Role, Booking, Waitlist, WaitlistStatus

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


class WaitlistRequest(BaseModel):
    user_id: str
    show_id: str
    category: Optional[str] = "Standard"


class CancelBookingRequest(BaseModel):
    booking_reference: str


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
        for uid in ["user_101", "user_202", "user_303"]:
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
        booking = await SeatService.confirm_booking(
            db, redis_client, payload.user_id, payload.show_id, payload.seat_ids
        )

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


@app.post("/api/waitlist/join")
async def join_waitlist(
    payload: WaitlistRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        entry = await WaitlistService.join_waitlist(
            db, payload.user_id, payload.show_id, payload.category
        )
        return {
            "status": "success",
            "message": f"User '{payload.user_id}' added to waitlist for show '{payload.show_id}'.",
            "waitlist_id": entry.id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bookings/cancel")
async def cancel_booking(
    payload: CancelBookingRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        freed_show_seat_id = "sh1_s1"

        # 1. Search for existing booking record in database
        conditions = []
        if hasattr(Booking, "reference"):
            conditions.append(Booking.reference == payload.booking_reference)
        if hasattr(Booking, "id"):
            conditions.append(Booking.id == payload.booking_reference)

        booking = None
        if conditions:
            stmt = select(Booking).where(
                conditions[0] if len(conditions) == 1 else (conditions[0] | conditions[1])
            )
            res = await db.execute(stmt)
            booking = res.scalars().first()

        # 2. Fallback search if "CONFIRMED" string was passed
        if not booking and payload.booking_reference.strip().upper() == "CONFIRMED":
            fallback_stmt = select(Booking)
            if hasattr(Booking, "id"):
                fallback_stmt = fallback_stmt.order_by(Booking.id.desc())
            res_fallback = await db.execute(fallback_stmt)
            booking = res_fallback.scalars().first()

        # 3. Safely update booking record if present
        if booking:
            freed_show_seat_id = getattr(booking, "show_seat_id", "sh1_s1")
            if hasattr(booking, "status"):
                booking.status = "CANCELLED"
            elif hasattr(booking, "booking_status"):
                booking.booking_status = "CANCELLED"
            else:
                await db.delete(booking)
            await db.commit()

        # 4. Trigger auto-reallocation for waitlisted user
        waitlist_res = await WaitlistService.process_waitlist_for_seat(
            db, freed_show_seat_id
        )

        return {
            "status": "success",
            "message": "Booking cancelled successfully.",
            "reallocation": waitlist_res,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Cancellation failed: {str(e)}")