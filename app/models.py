import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, Numeric, Enum, UniqueConstraint, Index
)
from app.database import Base


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    ORGANISER = "ORGANISER"
    CUSTOMER = "CUSTOMER"


class SeatStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    BOOKED = "BOOKED"
    OFFERED = "OFFERED"


class WaitlistStatus(str, enum.Enum):
    PENDING = "PENDING"
    OFFERED = "OFFERED"
    EXPIRED = "EXPIRED"
    FULFILLED = "FULFILLED"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(Enum(Role), default=Role.CUSTOMER, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Venue(Base):
    __tablename__ = "venues"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    location = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)


class Seat(Base):
    __tablename__ = "seats"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String, ForeignKey("venues.id"), nullable=False)
    row = Column(String, nullable=False)
    number = Column(Integer, nullable=False)
    category = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("venue_id", "row", "number", name="uq_seat_location"),)


class Show(Base):
    __tablename__ = "shows"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    venue_id = Column(String, ForeignKey("venues.id"), nullable=False)
    organiser_id = Column(String, ForeignKey("users.id"), nullable=False)


class ShowSeat(Base):
    __tablename__ = "show_seats"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    show_id = Column(String, ForeignKey("shows.id"), nullable=False)
    seat_id = Column(String, ForeignKey("seats.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    status = Column(Enum(SeatStatus), default=SeatStatus.AVAILABLE, nullable=False)
    version = Column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("show_id", "seat_id", name="uq_show_seat"),)


class SeatHold(Base):
    __tablename__ = "seat_holds"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    show_seat_id = Column(String, ForeignKey("show_seats.id"), unique=True, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reference = Column(String, unique=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    show_id = Column(String, ForeignKey("shows.id"), nullable=False)
    show_seat_id = Column(String, ForeignKey("show_seats.id"), nullable=True)
    status = Column(String, default="CONFIRMED", nullable=False)
    total_amount = Column(Numeric(10, 2), default=0.0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BookingItem(Base):
    __tablename__ = "booking_items"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id = Column(String, ForeignKey("bookings.id"), nullable=False)
    show_seat_id = Column(String, ForeignKey("show_seats.id"), unique=True, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)


class Waitlist(Base):
    __tablename__ = "waitlists"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    show_id = Column(String, ForeignKey("shows.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=True)
    status = Column(Enum(WaitlistStatus), default=WaitlistStatus.PENDING, nullable=False)
    offer_expires_at = Column(DateTime, nullable=True)
    offered_seat_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_waitlist_queue", "show_id", "category", "status", "created_at"),
    )