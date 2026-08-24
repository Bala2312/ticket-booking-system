# High-Concurrency Ticket Booking System

Production-grade event ticket booking engine implemented in Python (FastAPI, SQLAlchemy, PostgreSQL, and Redis).

## Features
* **Pessimistic Concurrency Locking:** Uses PostgreSQL `FOR UPDATE NOWAIT` to prevent duplicate seat holds.
* **TTL Auto-Release:** Automatically releases abandoned held seats after 10 minutes using Redis TTL.
* **Waitlist Auto-Assignment:** First-In-First-Out (FIFO) queue that offers released/cancelled seats to queued users with time-limited claims.
* **QR Ticket Generation:** Generates base64 QR codes upon confirmed booking and sends email notifications.

## Project Structure
```text
ticket-booking-system/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   └── services/
│       ├── seat_service.py
│       ├── waitlist_service.py
│       └── notification_service.py
├── .env.example
├── .gitignore
├── requirements.txt
├── SYSTEM_DESIGN.md
└── README.md