from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import Waitlist, WaitlistStatus, ShowSeat, SeatStatus, Show
from app.services.notification_service import NotificationService


class WaitlistService:
    @staticmethod
    async def join_waitlist(db, user_id: str, show_id: str, category: str = "Standard"):
        """Adds a user to the category waitlist queue in PENDING state."""
        show_stmt = select(Show).where(Show.id == show_id)
        show_res = await db.execute(show_stmt)
        show = show_res.scalars().first()
        if not show:
            raise ValueError(f"Show {show_id} does not exist.")

        new_entry = Waitlist(
            user_id=user_id,
            show_id=show_id,
            category=category,
            status=WaitlistStatus.PENDING,
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_entry)
        await db.commit()
        await db.refresh(new_entry)
        return new_entry

    @staticmethod
    async def process_waitlist_for_seat(db, show_seat_id: str):
        """Finds the next pending waitlist entry (FIFO), issues a 10-minute offer, and updates status."""
        # Fetch target seat
        seat_stmt = select(ShowSeat).where(ShowSeat.id == show_seat_id)
        seat_res = await db.execute(seat_stmt)
        seat = seat_res.scalars().first()

        if not seat:
            return None

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
        
        # Select first matching entry
        next_entry = wl_res.scalars().first()

        if next_entry:
            # Enforce 10-minute time-limited offer window
            offer_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)

            next_entry.status = WaitlistStatus.OFFERED
            next_entry.offered_seat_id = show_seat_id
            if hasattr(next_entry, "offer_expires_at"):
                next_entry.offer_expires_at = offer_expiry

            # Reserve seat status as HELD for offered waitlist user
            seat.status = SeatStatus.HELD
            await db.commit()

            # Dispatch time-limited notification email
            await NotificationService.send_ticket_email(
                recipient_email=f"{next_entry.user_id}@example.com",
                booking_ref=f"OFFER-{seat.id}",
                event_title=f"Waitlist Offer: Seat {seat.id} reserved for 10 minutes!"
            )

            return {
                "status": "OFFERED",
                "waitlist_id": next_entry.id,
                "user_id": next_entry.user_id,
                "offered_seat_id": show_seat_id,
                "expires_at": offer_expiry.isoformat()
            }

        # If no waitlisted users remain, release seat back to public pool
        seat.status = SeatStatus.AVAILABLE
        await db.commit()
        return {"status": "NO_WAITLIST", "seat_id": show_seat_id}

    @staticmethod
    async def expire_stale_offers(db):
        """Reclaims seats from expired offers and advances to the next waitlisted user."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(Waitlist)
            .where(
                Waitlist.status == WaitlistStatus.OFFERED,
                Waitlist.offer_expires_at <= now
            )
        )
        res = await db.execute(stmt)
        expired_entries = res.scalars().all()

        for entry in expired_entries:
            entry.status = WaitlistStatus.EXPIRED
            freed_seat_id = entry.offered_seat_id
            await db.commit()

            # Pass the freed seat to the next person in line
            if freed_seat_id:
                await WaitlistService.process_waitlist_for_seat(db, freed_seat_id)