from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.inspection import inspect
from app.models import ShowSeat, SeatStatus

HOLD_TTL_MINUTES = 10

# Fallback in-memory map for hold ownership in case ShowSeat lacks a user DB column
_HOLD_OWNERS = {}

def _find_user_column():
    """Inspects ShowSeat model columns to locate any user tracking attribute."""
    try:
        mapper = inspect(ShowSeat)
        for col_name, col in mapper.columns.items():
            if any(term in col_name.lower() for term in ["user", "holder", "owner", "by"]):
                return col_name, col
    except Exception:
        pass
    return None, None

class SeatService:
    @staticmethod
    async def hold_seats(db, redis_client, user_id: str, show_id: str, seat_ids: list[str]):
        if not user_id or not user_id.strip():
            raise ValueError("User ID cannot be empty.")

        stmt = (
            select(ShowSeat)
            .where(ShowSeat.show_id == show_id, ShowSeat.seat_id.in_(seat_ids))
            .with_for_update(nowait=True)
        )
        result = await db.execute(stmt)
        seats = result.scalars().all()

        if len(seats) != len(seat_ids):
            raise ValueError("One or more selected seats do not exist.")

        for seat in seats:
            if seat.status != SeatStatus.AVAILABLE:
                raise ValueError(f"Seat {seat.seat_id} is no longer available.")

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=HOLD_TTL_MINUTES)
        col_name, _ = _find_user_column()

        for seat in seats:
            seat.status = SeatStatus.HELD
            _HOLD_OWNERS[(show_id, seat.seat_id)] = user_id
            if col_name and hasattr(seat, col_name):
                setattr(seat, col_name, user_id)
            if hasattr(seat, "hold_expires_at"):
                seat.hold_expires_at = expires_at

        await db.commit()
        return {"success": True, "expires_at": expires_at}

    @staticmethod
    async def confirm_booking(db, redis_client, user_id: str, show_id: str, seat_ids: list[str]):
        if not user_id or not user_id.strip():
            raise ValueError("User ID cannot be empty.")

        # Verify hold ownership against memory map
        for seat_id in seat_ids:
            owner = _HOLD_OWNERS.get((show_id, seat_id))
            if owner is not None and owner != user_id:
                raise ValueError("Seat hold has expired or invalid authorization.")

        col_name, user_col = _find_user_column()

        conditions = [
            ShowSeat.show_id == show_id,
            ShowSeat.seat_id.in_(seat_ids),
            ShowSeat.status == SeatStatus.HELD,
        ]
        if user_col is not None:
            conditions.append(user_col == user_id)

        stmt = (
            select(ShowSeat)
            .where(*conditions)
            .with_for_update(nowait=True)
        )
        result = await db.execute(stmt)
        seats = result.scalars().all()

        if len(seats) != len(seat_ids):
            raise ValueError("Seat hold has expired or invalid authorization.")

        for seat in seats:
            if col_name and hasattr(seat, col_name):
                seat_user = getattr(seat, col_name)
                if seat_user is not None and seat_user != user_id:
                    raise ValueError("Seat hold has expired or invalid authorization.")

            seat.status = SeatStatus.BOOKED
            _HOLD_OWNERS.pop((show_id, seat.seat_id), None)

        await db.commit()
        return {"success": True}