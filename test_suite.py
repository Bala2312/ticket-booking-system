import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models import (
    User, Role, Venue, Seat, Show, ShowSeat, SeatStatus, 
    Waitlist, WaitlistStatus, Booking
)
from app.services.seat_service import SeatService
from app.services.waitlist_service import WaitlistService


# Database Fixtures
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

@pytest.fixture
def mock_redis():
    return AsyncMock()

# Seed Data Fixture
@pytest_asyncio.fixture
async def setup_data(db_session):
    u1 = User(id="u1", email="u1@test.com", password="pwd", name="User 1", role=Role.CUSTOMER)
    u2 = User(id="u2", email="u2@test.com", password="pwd", name="User 2", role=Role.CUSTOMER)
    org = User(id="org1", email="org@test.com", password="pwd", name="Organiser", role=Role.ORGANISER)
    admin = User(id="admin1", email="admin@test.com", password="pwd", name="Admin", role=Role.ADMIN)

    venue = Venue(id="v1", name="Arena 1", location="City Center", capacity=100)
    seat1 = Seat(id="seat1", venue_id="v1", row="A", number=1, category="VIP")
    seat2 = Seat(id="seat2", venue_id="v1", row="A", number=2, category="VIP")
    seat3 = Seat(id="seat3", venue_id="v1", row="B", number=1, category="Standard")

    show = Show(id="sh1", title="Concert", start_time=datetime.now(timezone.utc), venue_id="v1", organiser_id="org1")

    ss1 = ShowSeat(id="ss1", show_id="sh1", seat_id="s1", price=100.0, status=SeatStatus.AVAILABLE)
    ss2 = ShowSeat(id="ss2", show_id="sh1", seat_id="s2", price=100.0, status=SeatStatus.AVAILABLE)
    ss3 = ShowSeat(id="ss3", show_id="sh1", seat_id="s3", price=50.0, status=SeatStatus.AVAILABLE)

    db_session.add_all([u1, u2, org, admin, venue, seat1, seat2, seat3, show, ss1, ss2, ss3])
    await db_session.commit()
    return {"u1": u1, "u2": u2, "show": show, "seats": ["s1", "s2", "s3"]}


# --- Group 1: Seat Holding & Validation (Tests 1-6) ---

@pytest.mark.asyncio
async def test_01_hold_single_available_seat(db_session, mock_redis, setup_data):
    res = await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    assert res["success"] is True

@pytest.mark.asyncio
async def test_02_double_hold_same_user(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="no longer available"):
        await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])

@pytest.mark.asyncio
async def test_03_double_hold_different_user(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="no longer available"):
        await SeatService.hold_seats(db_session, mock_redis, "u2", "sh1", ["s1"])

@pytest.mark.asyncio
async def test_04_hold_nonexistent_seat_id(db_session, mock_redis, setup_data):
    with pytest.raises(ValueError, match="do not exist"):
        await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["nonexistent_seat"])

@pytest.mark.asyncio
async def test_05_hold_empty_seat_list(db_session, mock_redis, setup_data):
    res = await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", [])
    assert res["success"] is True

@pytest.mark.asyncio
async def test_06_hold_partial_invalid_seats(db_session, mock_redis, setup_data):
    with pytest.raises(ValueError, match="do not exist"):
        await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1", "invalid_s2"])


# --- Group 2: Booking Confirmation & Authorization (Tests 7-12) ---

@pytest.mark.asyncio
async def test_07_confirm_held_seat_success(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    res = await SeatService.confirm_booking(db_session, mock_redis, "u1", "sh1", ["s1"])
    assert res["success"] is True

@pytest.mark.asyncio
async def test_08_unauthorized_confirmation(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(db_session, mock_redis, "u2", "sh1", ["s1"])

@pytest.mark.asyncio
async def test_09_confirm_unheld_available_seat(db_session, mock_redis, setup_data):
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(db_session, mock_redis, "u1", "sh1", ["s1"])

@pytest.mark.asyncio
async def test_10_confirm_already_booked_seat(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    await SeatService.confirm_booking(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(db_session, mock_redis, "u1", "sh1", ["s1"])

@pytest.mark.asyncio
async def test_11_confirm_mismatched_show_id(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(db_session, mock_redis, "u1", "wrong_show", ["s1"])

@pytest.mark.asyncio
async def test_12_confirm_multiple_seats_hold(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1", "s2"])
    res = await SeatService.confirm_booking(db_session, mock_redis, "u1", "sh1", ["s1", "s2"])
    assert res["success"] is True


# --- Group 3: Waitlist Management & FIFO Queue (Tests 13-18) ---

@pytest.mark.asyncio
async def test_13_waitlist_fifo_order(db_session, setup_data):
    w1 = Waitlist(id="w1", show_id="sh1", user_id="u1", category="VIP", status=WaitlistStatus.PENDING)
    w2 = Waitlist(id="w2", show_id="sh1", user_id="u2", category="VIP", status=WaitlistStatus.PENDING)
    db_session.add_all([w1, w2])
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    
    await db_session.refresh(w1)
    await db_session.refresh(w2)
    assert w1.status == WaitlistStatus.OFFERED
    assert w2.status == WaitlistStatus.PENDING

@pytest.mark.asyncio
async def test_14_waitlist_process_empty_queue(db_session, setup_data):
    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    # Should execute without errors

@pytest.mark.asyncio
async def test_15_waitlist_skips_fulfilled_entries(db_session, setup_data):
    w1 = Waitlist(id="w1", show_id="sh1", user_id="u1", category="VIP", status=WaitlistStatus.FULFILLED)
    w2 = Waitlist(id="w2", show_id="sh1", user_id="u2", category="VIP", status=WaitlistStatus.PENDING)
    db_session.add_all([w1, w2])
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await db_session.refresh(w2)
    assert w2.status == WaitlistStatus.OFFERED

@pytest.mark.asyncio
async def test_16_waitlist_nonexistent_seat_id(db_session, setup_data):
    await WaitlistService.process_waitlist_for_seat(db_session, "nonexistent_ss")

@pytest.mark.asyncio
async def test_17_waitlist_second_seat_release(db_session, setup_data):
    w1 = Waitlist(id="w1", show_id="sh1", user_id="u1", category="VIP", status=WaitlistStatus.PENDING)
    w2 = Waitlist(id="w2", show_id="sh1", user_id="u2", category="VIP", status=WaitlistStatus.PENDING)
    db_session.add_all([w1, w2])
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await WaitlistService.process_waitlist_for_seat(db_session, "ss2")
    
    await db_session.refresh(w1)
    await db_session.refresh(w2)
    assert w1.status == WaitlistStatus.OFFERED
    assert w2.status == WaitlistStatus.OFFERED

@pytest.mark.asyncio
async def test_18_waitlist_offered_seat_assignment(db_session, setup_data):
    w1 = Waitlist(id="w1", show_id="sh1", user_id="u1", category="VIP", status=WaitlistStatus.PENDING)
    db_session.add(w1)
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await db_session.refresh(w1)
    assert w1.offered_seat_id == "ss1"


# --- Group 4: User & Role Permissions (Tests 19-22) ---

@pytest.mark.asyncio
async def test_19_user_default_role(db_session):
    u = User(email="default@test.com", password="pwd", name="User Default")
    db_session.add(u)
    await db_session.commit()
    assert u.role == Role.CUSTOMER

@pytest.mark.asyncio
async def test_20_user_explicit_roles(db_session):
    u_admin = User(email="admin@test.com", password="pwd", name="Admin", role=Role.ADMIN)
    u_org = User(email="org@test.com", password="pwd", name="Org", role=Role.ORGANISER)
    db_session.add_all([u_admin, u_org])
    await db_session.commit()
    assert u_admin.role == Role.ADMIN
    assert u_org.role == Role.ORGANISER

@pytest.mark.asyncio
async def test_21_unique_email_constraint(db_session, setup_data):
    dup_user = User(email="u1@test.com", password="pwd", name="Duplicate")
    db_session.add(dup_user)
    with pytest.raises(IntegrityError):
        await db_session.commit()

@pytest.mark.asyncio
async def test_22_uuid_generation(db_session):
    u = User(email="uuid@test.com", password="pwd", name="UUID User")
    db_session.add(u)
    await db_session.commit()
    assert u.id is not None and len(u.id) > 10


# --- Group 5: Venue & Model Constraints (Tests 23-26) ---

@pytest.mark.asyncio
async def test_23_venue_unique_seat_constraint(db_session, setup_data):
    dup_seat = Seat(venue_id="v1", row="A", number=1, category="VIP")
    db_session.add(dup_seat)
    with pytest.raises(IntegrityError):
        await db_session.commit()

@pytest.mark.asyncio
async def test_24_show_seat_unique_constraint(db_session, setup_data):
    dup_ss = ShowSeat(show_id="sh1", seat_id="s1", price=100.0)
    db_session.add(dup_ss)
    with pytest.raises(IntegrityError):
        await db_session.commit()

@pytest.mark.asyncio
async def test_25_booking_reference_generation(db_session, setup_data):
    b = Booking(user_id="u1", show_id="sh1", total_amount=100.00)
    db_session.add(b)
    await db_session.commit()
    assert b.reference is not None

@pytest.mark.asyncio
async def test_26_show_seat_initial_status(db_session, setup_data):
    ss = ShowSeat(show_id="sh1", seat_id="s_new", price=150.00)
    db_session.add(ss)
    await db_session.commit()
    assert ss.status == SeatStatus.AVAILABLE


# --- Group 6: Concurrency & End-to-End Lifecycle (Tests 27-30) ---

@pytest.mark.asyncio
async def test_27_concurrent_hold_race(db_session, mock_redis, setup_data):
    # Simulate simultaneous hold requests for same seat
    results = await asyncio.gather(
        SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s3"]),
        SeatService.hold_seats(db_session, mock_redis, "u2", "sh1", ["s3"]),
        return_exceptions=True
    )
    success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    error_count = sum(1 for r in results if isinstance(r, ValueError))
    
    assert success_count == 1
    assert error_count == 1

@pytest.mark.asyncio
async def test_28_partial_failure_rollback(db_session, mock_redis, setup_data):
    # Try holding s2 (available) and invalid seat together
    with pytest.raises(ValueError):
        await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s2", "invalid_seat"])

@pytest.mark.asyncio
async def test_29_full_lifecycle_hold_confirm(db_session, mock_redis, setup_data):
    # 1. Hold
    hold_res = await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    assert hold_res["success"] is True
    
    # 2. Confirm
    conf_res = await SeatService.confirm_booking(db_session, mock_redis, "u1", "sh1", ["s1"])
    assert conf_res["success"] is True

@pytest.mark.asyncio
async def test_30_multiple_users_distinct_seats(db_session, mock_redis, setup_data):
    res1 = await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    res2 = await SeatService.hold_seats(db_session, mock_redis, "u2", "sh1", ["s2"])
    
    assert res1["success"] is True
    assert res2["success"] is True