# 🎫 High-Concurrency Ticket Booking System

A production-grade, full-stack event ticketing platform built with **FastAPI**, **Streamlit**, **SQLAlchemy**, and **Redis**. Designed to handle concurrent seat holds, automatic reservation expiry, waitlist queues, and real-time QR-code ticket email delivery.

---

## 🚀 Live Links

* **Frontend UI (Streamlit):** https://ticket-booking-system-user-interface.onrender.com/
* **Backend API (FastAPI):** https://ticket-booking-system-my6q.onrender.com
* **Interactive API Docs (Swagger UI):** https://ticket-booking-system-my6q.onrender.com/docs

---

## ✨ Key Features

* **Visual Seat Map & Holding:** Real-time seat locking with automatic TTL expiry to prevent double bookings.
* **Inline QR Ticket Generation:** Dynamically generates base64/CID embedded QR codes sent directly to user inboxes upon confirmation.
* **Waitlist & Reallocation Engine:** Automatic queue reallocation when bookings are canceled or expired.
* **Dual-Tier Architecture:** Asynchronous FastAPI backend separated from an interactive Streamlit administrative dashboard.

---

## 🛠️ Tech Stack

* **Frontend:** Streamlit, Python Requests
* **Backend Framework:** FastAPI, Uvicorn
* **Database & ORM:** SQLite (`aiosqlite`), Async SQLAlchemy
* **Caching & Queues:** Redis
* **Notifications & Tools:** Python `smtplib`, `MIMEImage`, `qrcode`, `Pillow`
* **Deployment:** Render (Web Services)

---

## 💻 Local Setup & Running

### 1. Prerequisites
* Python 3.10+
* Redis running locally (`redis://localhost:6379`)

### 2. Installation
```bash
# Clone repository
git clone [https://github.com/YOUR_USERNAME/ticket-booking-system.git](https://github.com/YOUR_USERNAME/ticket-booking-system.git)
cd ticket-booking-system

# Virtual environment setup
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt