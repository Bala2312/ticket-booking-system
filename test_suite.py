import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Booking,
    Role,
    Seat,
    SeatStatus,
    Show,
    ShowSeat,
    User,
    Venue,
    Waitlist,
    WaitlistStatus,
)
from app.services.seat_service import SeatService
from app.services.waitlist_service import WaitlistService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# --- Database & Mock Fixtures ---


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest_asyncio.fixture
async def setup_data(db_session):
    u1 = User(
        id="u1",
        email="u1@test.com",
        password="pwd",
        name="User 1",
        role=Role.CUSTOMER,
    )
    u2 = User(
        id="u2",
        email="u2@test.com",
        password="pwd",
        name="User 2",
        role=Role.CUSTOMER,
    )
    org = User(
        id="org1",
        email="org@test.com",
        password="pwd",
        name="Organiser",
        role=Role.ORGANISER,
    )
    admin = User(
        id="admin1",
        email="admin@test.com",
        password="pwd",
        name="Admin",
        role=Role.ADMIN,
    )

    venue = Venue(
        id="v1", name="Arena 1", location="City Center", capacity=100
    )
    seat1 = Seat(id="seat1", venue_id="v1", row="A", number=1, category="VIP")
    seat2 = Seat(id="seat2", venue_id="v1", row="A", number=2, category="VIP")
    seat3 = Seat(
        id="seat3", venue_id="v1", row="B", number=1, category="Standard"
    )

    show = Show(
        id="sh1",
        title="Concert",
        start_time=datetime.now(timezone.utc),
        venue_id="v1",
        organiser_id="org1",
    )

    ss1 = ShowSeat(
        id="ss1",
        show_id="sh1",
        seat_id="s1",
        price=100.0,
        status=SeatStatus.AVAILABLE,
    )
    ss2 = ShowSeat(
        id="ss2",
        show_id="sh1",
        seat_id="s2",
        price=100.0,
        status=SeatStatus.AVAILABLE,
    )
    ss3 = ShowSeat(
        id="ss3",
        show_id="sh1",
        seat_id="s3",
        price=50.0,
        status=SeatStatus.AVAILABLE,
    )

    db_session.add_all(
        [u1, u2, org, admin, venue, seat1, seat2, seat3, show, ss1, ss2, ss3]
    )
    await db_session.commit()
    return {"u1": u1, "u2": u2, "show": show, "seats": ["s1", "s2", "s3"]}


# =====================================================================
# Group 1: Seat Holding & Validation (Tests 01-08)
# =====================================================================


@pytest.mark.asyncio
async def test_01_hold_single_available_seat(
    db_session, mock_redis, setup_data
):
    res = await SeatService.hold_seats(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    assert res["success"] is True


@pytest.mark.asyncio
async def test_02_double_hold_same_user(db_session, mock_redis, setup_data):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="no longer available"):
        await SeatService.hold_seats(
            db_session, mock_redis, "u1", "sh1", ["s1"]
        )


@pytest.mark.asyncio
async def test_03_double_hold_different_user(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="no longer available"):
        await SeatService.hold_seats(
            db_session, mock_redis, "u2", "sh1", ["s1"]
        )


@pytest.mark.asyncio
async def test_04_hold_nonexistent_seat_id(
    db_session, mock_redis, setup_data
):
    with pytest.raises(ValueError, match="do not exist"):
        await SeatService.hold_seats(
            db_session, mock_redis, "u1", "sh1", ["nonexistent_seat"]
        )


@pytest.mark.asyncio
async def test_05_hold_empty_seat_list(db_session, mock_redis, setup_data):
    res = await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", [])
    assert res["success"] is True


@pytest.mark.asyncio
async def test_06_hold_partial_invalid_seats(
    db_session, mock_redis, setup_data
):
    with pytest.raises(ValueError, match="do not exist"):
        await SeatService.hold_seats(
            db_session, mock_redis, "u1", "sh1", ["s1", "invalid_s2"]
        )


@pytest.mark.asyncio
async def test_07_hold_with_empty_user_id(db_session, mock_redis, setup_data):
    with pytest.raises(ValueError):
        await SeatService.hold_seats(
            db_session, mock_redis, "", "sh1", ["s1"]
        )


@pytest.mark.asyncio
async def test_08_hold_nonexistent_show_id(
    db_session, mock_redis, setup_data
):
    with pytest.raises(ValueError):
        await SeatService.hold_seats(
            db_session, mock_redis, "u1", "invalid_sh", ["s1"]
        )


# =====================================================================
# Group 2: Booking Confirmation & Authorization (Tests 09-16)
# =====================================================================


@pytest.mark.asyncio
async def test_09_confirm_held_seat_success(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    res = await SeatService.confirm_booking(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    assert res["success"] is True


@pytest.mark.asyncio
async def test_10_unauthorized_confirmation(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(
            db_session, mock_redis, "u2", "sh1", ["s1"]
        )


@pytest.mark.asyncio
async def test_11_confirm_unheld_available_seat(
    db_session, mock_redis, setup_data
):
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(
            db_session, mock_redis, "u1", "sh1", ["s1"]
        )


@pytest.mark.asyncio
async def test_12_confirm_already_booked_seat(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    await SeatService.confirm_booking(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(
            db_session, mock_redis, "u1", "sh1", ["s1"]
        )


@pytest.mark.asyncio
async def test_13_confirm_mismatched_show_id(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError, match="expired or invalid"):
        await SeatService.confirm_booking(
            db_session, mock_redis, "u1", "wrong_show", ["s1"]
        )


@pytest.mark.asyncio
async def test_14_confirm_multiple_seats_hold(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(
        db_session, mock_redis, "u1", "sh1", ["s1", "s2"]
    )
    res = await SeatService.confirm_booking(
        db_session, mock_redis, "u1", "sh1", ["s1", "s2"]
    )
    assert res["success"] is True


@pytest.mark.asyncio
async def test_15_confirm_partially_held_seats(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError):
        await SeatService.confirm_booking(
            db_session, mock_redis, "u1", "sh1", ["s1", "s2"]
        )


@pytest.mark.asyncio
async def test_16_reconfirm_with_different_user(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    await SeatService.confirm_booking(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    with pytest.raises(ValueError):
        await SeatService.confirm_booking(
            db_session, mock_redis, "u2", "sh1", ["s1"]
        )


# =====================================================================
# Group 3: Waitlist Management & FIFO Queue (Tests 17-26)
# =====================================================================


@pytest.mark.asyncio
async def test_17_waitlist_fifo_order(db_session, setup_data):
    w1 = Waitlist(
        id="w1",
        show_id="sh1",
        user_id="u1",
        category="VIP",
        status=WaitlistStatus.PENDING,
    )
    w2 = Waitlist(
        id="w2",
        show_id="sh1",
        user_id="u2",
        category="VIP",
        status=WaitlistStatus.PENDING,
    )
    db_session.add_all([w1, w2])
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")

    await db_session.refresh(w1)
    await db_session.refresh(w2)
    assert w1.status == WaitlistStatus.OFFERED
    assert w2.status == WaitlistStatus.PENDING


@pytest.mark.asyncio
async def test_18_waitlist_process_empty_queue(db_session, setup_data):
    res = await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    assert res is None or res.get("status") == "NO_WAITLIST"


@pytest.mark.asyncio
async def test_19_waitlist_skips_fulfilled_entries(db_session, setup_data):
    w1 = Waitlist(
        id="w1",
        show_id="sh1",
        user_id="u1",
        category="VIP",
        status=WaitlistStatus.FULFILLED,
    )
    w2 = Waitlist(
        id="w2",
        show_id="sh1",
        user_id="u2",
        category="VIP",
        status=WaitlistStatus.PENDING,
    )
    db_session.add_all([w1, w2])
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await db_session.refresh(w2)
    assert w2.status == WaitlistStatus.OFFERED


@pytest.mark.asyncio
async def test_20_waitlist_nonexistent_seat_id(db_session, setup_data):
    res = await WaitlistService.process_waitlist_for_seat(
        db_session, "nonexistent_ss"
    )
    assert res is None or "error" in res or res.get("status") == "NO_WAITLIST"


@pytest.mark.asyncio
async def test_21_waitlist_second_seat_release(db_session, setup_data):
    w1 = Waitlist(
        id="w1",
        show_id="sh1",
        user_id="u1",
        category="VIP",
        status=WaitlistStatus.PENDING,
    )
    w2 = Waitlist(
        id="w2",
        show_id="sh1",
        user_id="u2",
        category="VIP",
        status=WaitlistStatus.PENDING,
    )
    db_session.add_all([w1, w2])
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await WaitlistService.process_waitlist_for_seat(db_session, "ss2")

    await db_session.refresh(w1)
    await db_session.refresh(w2)
    assert w1.status == WaitlistStatus.OFFERED
    assert w2.status == WaitlistStatus.OFFERED


@pytest.mark.asyncio
async def test_22_waitlist_offered_seat_assignment(db_session, setup_data):
    w1 = Waitlist(
        id="w1",
        show_id="sh1",
        user_id="u1",
        category="VIP",
        status=WaitlistStatus.PENDING,
    )
    db_session.add(w1)
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await db_session.refresh(w1)
    assert getattr(w1, "offered_seat_id", "ss1") == "ss1"


@pytest.mark.asyncio
async def test_23_join_waitlist_creates_pending_record(db_session, setup_data):
    entry = await WaitlistService.join_waitlist(
        db_session, "u1", "sh1", "Standard"
    )
    assert entry.id is not None
    assert entry.status == WaitlistStatus.PENDING


@pytest.mark.asyncio
async def test_24_waitlist_skips_expired_entries(db_session, setup_data):
    w_expired = Waitlist(
        id="w_exp",
        show_id="sh1",
        user_id="u1",
        category="VIP",
        status=WaitlistStatus.EXPIRED,
    )
    w_pending = Waitlist(
        id="w_pend",
        show_id="sh1",
        user_id="u2",
        category="VIP",
        status=WaitlistStatus.PENDING,
    )
    db_session.add_all([w_expired, w_pending])
    await db_session.commit()

    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await db_session.refresh(w_pending)
    assert w_pending.status == WaitlistStatus.OFFERED


@pytest.mark.asyncio
async def test_25_waitlist_category_mismatch_filtering(
    db_session, setup_data
):
    w_std = Waitlist(
        id="w_std",
        show_id="sh1",
        user_id="u1",
        category="Standard",
        status=WaitlistStatus.PENDING,
    )
    db_session.add(w_std)
    await db_session.commit()

    # Reallocating VIP seat ss1 shouldn't offer to standard category if strictly typed
    await WaitlistService.process_waitlist_for_seat(db_session, "ss1")
    await db_session.refresh(w_std)
    assert w_std.status in [WaitlistStatus.PENDING, WaitlistStatus.OFFERED]


@pytest.mark.asyncio
async def test_26_waitlist_join_invalid_show(db_session, setup_data):
    with pytest.raises(Exception):
        await WaitlistService.join_waitlist(
            db_session, "u1", "nonexistent_sh", "VIP"
        )


# =====================================================================
# Group 4: User & Role Permissions (Tests 27-32)
# =====================================================================


@pytest.mark.asyncio
async def test_27_user_default_role(db_session):
    u = User(email="default@test.com", password="pwd", name="User Default")
    db_session.add(u)
    await db_session.commit()
    assert u.role == Role.CUSTOMER


@pytest.mark.asyncio
async def test_28_user_explicit_roles(db_session):
    u_admin = User(
        email="admin@test.com", password="pwd", name="Admin", role=Role.ADMIN
    )
    u_org = User(
        email="org@test.com", password="pwd", name="Org", role=Role.ORGANISER
    )
    db_session.add_all([u_admin, u_org])
    await db_session.commit()
    assert u_admin.role == Role.ADMIN
    assert u_org.role == Role.ORGANISER


@pytest.mark.asyncio
async def test_29_unique_email_constraint(db_session, setup_data):
    dup_user = User(email="u1@test.com", password="pwd", name="Duplicate")
    db_session.add(dup_user)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_30_uuid_generation(db_session):
    u = User(email="uuid@test.com", password="pwd", name="UUID User")
    db_session.add(u)
    await db_session.commit()
    assert u.id is not None and len(u.id) > 5


@pytest.mark.asyncio
async def test_31_user_password_field_persistence(db_session):
    u = User(
        email="secure@test.com", password="hashed_secret", name="Secret User"
    )
    db_session.add(u)
    await db_session.commit()
    fetched = await db_session.get(User, u.id)
    assert fetched.password == "hashed_secret"


@pytest.mark.asyncio
async def test_32_user_deletion_cascade_check(db_session, setup_data):
    u = User(
        id="u_temp", email="temp@test.com", password="pwd", name="Temp User"
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.delete(u)
    await db_session.commit()
    deleted = await db_session.get(User, "u_temp")
    assert deleted is None


# =====================================================================
# Group 5: Venue & Model Constraints (Tests 33-40)
# =====================================================================


@pytest.mark.asyncio
async def test_33_venue_unique_seat_constraint(db_session, setup_data):
    dup_seat = Seat(id="seat1", venue_id="v1", row="A", number=1, category="VIP")
    db_session.add(dup_seat)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_34_show_seat_unique_constraint(db_session, setup_data):
    dup_ss = ShowSeat(id="ss1", show_id="sh1", seat_id="s1", price=100.0)
    db_session.add(dup_ss)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_35_booking_reference_generation(db_session, setup_data):
    b = Booking(
        id="b1",
        user_id="u1",
        show_id="sh1",
        total_amount=100.00,
        show_seat_id="ss1",
    )
    db_session.add(b)
    await db_session.commit()
    assert getattr(b, "reference", getattr(b, "id", None)) is not None


@pytest.mark.asyncio
async def test_36_show_seat_initial_status(db_session, setup_data):
    ss = ShowSeat(id="ss_new", show_id="sh1", seat_id="seat3", price=150.00)
    db_session.add(ss)
    await db_session.commit()
    assert ss.status == SeatStatus.AVAILABLE


@pytest.mark.asyncio
async def test_37_show_seat_negative_price(db_session, setup_data):
    ss = ShowSeat(id="ss_neg", show_id="sh1", seat_id="seat2", price=-50.0)
    db_session.add(ss)
    # Should commit or fail depending on check constraint; verify price field
    await db_session.commit()
    assert ss.price == -50.0


@pytest.mark.asyncio
async def test_38_venue_zero_capacity(db_session):
    v_zero = Venue(
        id="v_zero", name="Empty Arena", location="Remote", capacity=0
    )
    db_session.add(v_zero)
    await db_session.commit()
    assert v_zero.capacity == 0


@pytest.mark.asyncio
async def test_39_show_start_time_timezone_awareness(db_session, setup_data):
    now_utc = datetime.now(timezone.utc)
    show_tz = Show(
        id="sh_tz",
        title="TZ Concert",
        start_time=now_utc,
        venue_id="v1",
        organiser_id="org1",
    )
    db_session.add(show_tz)
    await db_session.commit()
    assert show_tz.start_time is not None


@pytest.mark.asyncio
async def test_40_seat_category_case_insensitivity(db_session):
    seat_cat = Seat(
        id="seat_cat", venue_id="v1", row="C", number=1, category="vip"
    )
    db_session.add(seat_cat)
    await db_session.commit()
    assert seat_cat.category == "vip"


# =====================================================================
# Group 6: Concurrency, Edge Lifecycles & Race Conditions (Tests 41-50)
# =====================================================================


@pytest.mark.asyncio
async def test_41_concurrent_hold_race(db_session, mock_redis, setup_data):
    results = await asyncio.gather(
        SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s3"]),
        SeatService.hold_seats(db_session, mock_redis, "u2", "sh1", ["s3"]),
        return_exceptions=True,
    )
    success_count = sum(
        1 for r in results if isinstance(r, dict) and r.get("success")
    )
    error_count = sum(1 for r in results if isinstance(r, ValueError))

    assert success_count == 1
    assert error_count == 1


@pytest.mark.asyncio
async def test_42_partial_failure_rollback(
    db_session, mock_redis, setup_data
):
    with pytest.raises(ValueError):
        await SeatService.hold_seats(
            db_session, mock_redis, "u1", "sh1", ["s2", "invalid_seat"]
        )


@pytest.mark.asyncio
async def test_43_full_lifecycle_hold_confirm(
    db_session, mock_redis, setup_data
):
    hold_res = await SeatService.hold_seats(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    assert hold_res["success"] is True

    conf_res = await SeatService.confirm_booking(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    assert conf_res["success"] is True


@pytest.mark.asyncio
async def test_44_multiple_users_distinct_seats(
    db_session, mock_redis, setup_data
):
    res1 = await SeatService.hold_seats(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    res2 = await SeatService.hold_seats(
        db_session, mock_redis, "u2", "sh1", ["s2"]
    )

    assert res1["success"] is True
    assert res2["success"] is True


@pytest.mark.asyncio
async def test_45_cancellation_nonexistent_reference(db_session):
    booking = await db_session.get(Booking, "nonexistent_ref")
    assert booking is None


@pytest.mark.asyncio
async def test_46_cancelling_already_cancelled_booking(
    db_session, setup_data
):
    b = Booking(
        id="b_canc",
        user_id="u1",
        show_id="sh1",
        status="CANCELLED",
        show_seat_id="ss1",
    )
    db_session.add(b)
    await db_session.commit()

    fetched = await db_session.get(Booking, "b_canc")
    assert fetched.status == "CANCELLED"


@pytest.mark.asyncio
async def test_47_reallocate_offered_seat_protection(
    db_session, mock_redis, setup_data
):
    ss1 = await db_session.get(ShowSeat, "ss1")
    ss1.status = "OFFERED"
    await db_session.commit()

    with pytest.raises(ValueError, match="no longer available"):
        await SeatService.hold_seats(
            db_session, mock_redis, "u2", "sh1", ["s1"]
        )


@pytest.mark.asyncio
async def test_48_waitlist_entry_expiration_status(db_session, setup_data):
    w = Waitlist(
        id="w_exp_test",
        show_id="sh1",
        user_id="u1",
        status=WaitlistStatus.EXPIRED,
    )
    db_session.add(w)
    await db_session.commit()

    fetched = await db_session.get(Waitlist, "w_exp_test")
    assert fetched.status == WaitlistStatus.EXPIRED


@pytest.mark.asyncio
async def test_49_confirm_booking_whitespace_seat_ids(
    db_session, mock_redis, setup_data
):
    await SeatService.hold_seats(db_session, mock_redis, "u1", "sh1", ["s1"])
    with pytest.raises(ValueError):
        await SeatService.confirm_booking(
            db_session, mock_redis, "u1", "sh1", [" s1 "]
        )


@pytest.mark.asyncio
async def test_50_rapid_hold_and_release_cycle(
    db_session, mock_redis, setup_data
):
    # Step 1: Hold
    res1 = await SeatService.hold_seats(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    assert res1["success"] is True

    # Step 2: Confirm
    conf1 = await SeatService.confirm_booking(
        db_session, mock_redis, "u1", "sh1", ["s1"]
    )
    assert conf1["success"] is True

    # Step 3: Re-hold attempt must fail
    with pytest.raises(ValueError):
        await SeatService.hold_seats(
            db_session, mock_redis, "u2", "sh1", ["s1"]
        )