from datetime import datetime, timedelta
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
import redis.asyncio as aioredis

from app.models import ShowSeat, SeatHold, Booking, BookingItem, SeatStatus

HOLD_TTL_MINUTES = 10

class SeatService:
    @staticmethod
    async def hold_seats(db: AsyncSession, redis_client: aioredis.Redis, user_id: str, show_id: str, seat_ids: List[str]):
        expires_at = datetime.utcnow() + timedelta(minutes=HOLD_TTL_MINUTES)
        
        query = text("""
            SELECT id, status 
            FROM show_seats 
            WHERE show_id = :show_id AND seat_id = ANY(:seat_ids)
            FOR UPDATE NOWAIT;
        """)
        
        result = await db.execute(query, {"show_id": show_id, "seat_ids": seat_ids})
        locked_seats = result.fetchall()

        if len(locked_seats) != len(seat_ids):
            raise ValueError("One or more selected seats do not exist.")

        for seat in locked_seats:
            if seat.status != SeatStatus.AVAILABLE.value:
                raise ValueError("One or more requested seats are no longer available.")

        show_seat_ids = [seat.id for seat in locked_seats]

        await db.execute(
            update(ShowSeat)
            .where(ShowSeat.id.in_(show_seat_ids))
            .values(status=SeatStatus.HELD)
        )

        for ss_id in show_seat_ids:
            hold = SeatHold(show_seat_id=ss_id, user_id=user_id, expires_at=expires_at)
            db.add(hold)

        await db.commit()

        for ss_id in show_seat_ids:
            await redis_client.set(f"hold_ttl:{ss_id}", user_id, ex=HOLD_TTL_MINUTES * 60)

        return {"success": True, "expires_at": expires_at}

    @staticmethod
    async def confirm_booking(db: AsyncSession, redis_client: aioredis.Redis, user_id: str, show_id: str, seat_ids: List[str]):
        stmt = (
            select(ShowSeat)
            .where(ShowSeat.show_id == show_id, ShowSeat.seat_id.in_(seat_ids))
        )
        res = await db.execute(stmt)
        show_seats = res.scalars().all()

        show_seat_ids = [ss.id for ss in show_seats]
        holds_stmt = select(SeatHold).where(SeatHold.show_seat_id.in_(show_seat_ids))
        holds_res = await db.execute(holds_stmt)
        holds = {h.show_seat_id: h for h in holds_res.scalars().all()}

        total_amount = 0
        for ss in show_seats:
            hold = holds.get(ss.id)
            if not hold or hold.user_id != user_id or hold.expires_at < datetime.utcnow():
                raise ValueError("Seat hold expired or invalid.")
            total_amount += ss.price

        new_booking = Booking(user_id=user_id, show_id=show_id, total_amount=total_amount)
        db.add(new_booking)
        await db.flush()

        for ss in show_seats:
            item = BookingItem(booking_id=new_booking.id, show_seat_id=ss.id, price=ss.price)
            db.add(item)
            ss.status = SeatStatus.BOOKED

        for h in holds.values():
            await db.delete(h)

        await db.commit()

        for ss_id in show_seat_ids:
            await redis_client.delete(f"hold_ttl:{ss_id}")

        return new_booking