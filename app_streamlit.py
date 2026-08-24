import streamlit as st
import requests

API_URL = "https://ticket-booking-system-my6q.onrender.com"

st.set_page_config(page_title="Ticket Booking System", layout="wide")
st.title("🎫 Ticket Booking Platform")

tabs = st.tabs([
    "1. Setup Show/Venue",
    "2. Visual Seat Map & Hold",
    "3. Confirm Booking",
    "4. Waitlist & Cancellations",
])

# Tab 1: Setup
with tabs[0]:
    st.header("Admin / Organiser Setup")
    col1, col2 = st.columns(2)
    with col1:
        show_id = st.text_input("Show ID", value="sh1")
        venue_id = st.text_input("Venue ID", value="v1")
    with col2:
        seat_id = st.text_input("Seat ID", value="s1")
        price = st.number_input("Seat Price", value=100.0)

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Create Show & Seat Record"):
            payload = {
                "show_id": show_id,
                "venue_id": venue_id,
                "seat_id": seat_id,
                "price": price,
            }
            try:
                res = requests.post(f"{API_URL}/api/admin/setup", json=payload)
                if res.status_code == 200:
                    st.success(res.json().get("message", "Database configured!"))
                else:
                    st.error(f"Setup Failed ({res.status_code}): {res.text}")
            except Exception as e:
                st.error(f"Error connecting to backend: {e}")

    with col_b2:
        if st.button("Check Backend Health"):
            try:
                res = requests.get(f"{API_URL}/health")
                st.success(f"Backend Status: {res.json()}")
            except Exception as e:
                st.error(f"Cannot connect to API at {API_URL}: {e}")

# Tab 2: Visual Seat Selection & Hold
with tabs[1]:
    st.header("Visual Seat Grid & Hold")
    u_id = st.text_input("Customer User ID", value="user_101", key="hold_uid")
    s_id = st.text_input("Show ID", value="sh1", key="hold_sh")
    target_seat = st.text_input("Seat ID to Hold", value="s1", key="hold_seat")

    if st.button("Place Seat Hold"):
        payload = {"user_id": u_id, "show_id": s_id, "seat_ids": [target_seat]}
        try:
            res = requests.post(f"{API_URL}/api/seats/hold", json=payload)
            if res.status_code == 200:
                st.success(
                    f"Hold Successful! Expires at: {res.json().get('expires_at')}"
                )
            else:
                st.error(f"Hold Failed ({res.status_code}): {res.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

# Tab 3: Confirm Booking
with tabs[2]:
    st.header("Confirm Booking")
    c_uid = st.text_input("Customer User ID", value="user_101", key="conf_uid")
    c_sh = st.text_input("Show ID", value="sh1", key="conf_sh")
    c_seat = st.text_input("Seat ID to Confirm", value="s1", key="conf_seat")
    c_email = st.text_input(
        "Recipient Email", value="customer@example.com", key="conf_email"
    )
    c_title = st.text_input(
        "Event Title", value="Live Concert", key="conf_title"
    )

    if st.button("Confirm Booking"):
        payload = {
            "user_id": c_uid,
            "show_id": c_sh,
            "seat_ids": [c_seat],
            "recipient_email": c_email,
            "event_title": c_title,
        }
        try:
            res = requests.post(f"{API_URL}/api/bookings/confirm", json=payload)
            if res.status_code == 200:
                st.success(
                    f"Booking Confirmed! Reference: {res.json().get('booking_reference')}"
                )
            else:
                st.error(f"Confirmation Failed ({res.status_code}): {res.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

# Tab 4: Waitlist & Reallocation Management
with tabs[3]:
    st.header("Waitlist & Reallocation")
    
    col_w1, col_w2 = st.columns(2)

    with col_w1:
        st.subheader("Join Waitlist Queue")
        w_uid = st.text_input("Waitlist User ID", value="user_303", key="wl_uid")
        w_sh = st.text_input("Show ID", value="sh1", key="wl_sh")
        w_cat = st.selectbox("Seat Category", ["VIP", "Standard", "Premium"], key="wl_cat")

        if st.button("Join Waitlist"):
            payload = {
                "user_id": w_uid,
                "show_id": w_sh,
                "category": w_cat
            }
            try:
                res = requests.post(f"{API_URL}/api/waitlist/join", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    st.success(f"{data.get('message')} (Waitlist ID: {data.get('waitlist_id')})")
                else:
                    st.error(f"Waitlist Join Failed ({res.status_code}): {res.text}")
            except Exception as e:
                st.error(f"Request failed: {e}")

    with col_w2:
        st.subheader("Cancel Booking & Reallocate")
        cancel_ref = st.text_input("Booking Reference or ID to Cancel", value="CONFIRMED", key="cancel_ref")

        if st.button("Cancel Booking"):
            payload = {"booking_reference": cancel_ref}
            try:
                res = requests.post(f"{API_URL}/api/bookings/cancel", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    st.success(f"{data.get('message')}")
                    realloc = data.get("reallocation")
                    if realloc:
                        st.json(realloc)
                else:
                    st.error(f"Cancellation Failed ({res.status_code}): {res.text}")
            except Exception as e:
                st.error(f"Request failed: {e}")