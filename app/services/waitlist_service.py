from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import ShowSeat, Waitlist, SeatStatus, WaitlistStatus
from app.services.notification_service import NotificationService

OFFER_TTL_MINUTES = 15

class WaitlistService:
    @staticmethod
    async def process_waitlist_for_seat(db: AsyncSession, show_seat_id: str):
        stmt = select(ShowSeat).where(ShowSeat.id == show_seat_id)
        res = await db.execute(stmt)
        show_seat = res.scalar_one_or_none()

        if not show_seat or show_seat.status != SeatStatus.AVAILABLE:
            return

        wl_stmt = (
            select(Waitlist)
            .where(
                Waitlist.show_id == show_seat.show_id,
                Waitlist.status == WaitlistStatus.PENDING
            )
            .order_by(Waitlist.created_at.asc())
        )
        wl_res = await db.execute(wl_stmt)
        next_entry = wl_res.scalar_one_or_none()

        if not next_entry:
            return

        offer_expires_at = datetime.utcnow() + timedelta(minutes=OFFER_TTL_MINUTES)
        
        show_seat.status = SeatStatus.OFFERED
        next_entry.status = WaitlistStatus.OFFERED
        next_entry.offered_seat_id = show_seat_id
        next_entry.offer_expires_at = offer_expires_at

        await db.commit()

        await NotificationService.send_waitlist_offer_email(
            recipient_email="customer@example.com",
            event_title="Event Seat Offer",
            waitlist_id=next_entry.id,
            expires_at=offer_expires_at
        )