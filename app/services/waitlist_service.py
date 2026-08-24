from sqlalchemy import select
from app.models import Waitlist, WaitlistStatus, ShowSeat

class WaitlistService:
    @staticmethod
    async def process_waitlist_for_seat(db, show_seat_id: str):
        # Fetch target seat
        seat_stmt = select(ShowSeat).where(ShowSeat.id == show_seat_id)
        seat_res = await db.execute(seat_stmt)
        seat = seat_res.scalars().first()

        if not seat:
            return

        # Query first pending waitlist entry (FIFO)
        wl_stmt = (
            select(Waitlist)
            .where(
                Waitlist.show_id == seat.show_id,
                Waitlist.status == WaitlistStatus.PENDING
            )
            .order_by(Waitlist.id.asc())
        )
        wl_res = await db.execute(wl_stmt)
        
        # Use .scalars().first() instead of .scalar_one_or_none()
        next_entry = wl_res.scalars().first()

        if next_entry:
            next_entry.status = WaitlistStatus.OFFERED
            next_entry.offered_seat_id = show_seat_id
            await db.commit()