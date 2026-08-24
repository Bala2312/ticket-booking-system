# System Design Write-Up: Ticket Booking Platform

## 1. Seat Hold and TTL Mechanism
To prevent inventory lockup during high-demand event drops, the application uses a dynamic Time-To-Live (TTL) hold strategy. When a user selects seats, their status changes from `AVAILABLE` to `HELD` in the database, and an entry is added to `seat_holds` with an expiration timestamp (`expires_at = NOW() + 10 minutes`). 

TTL enforcement is handled through a dual-layered approach:
* **Transaction-Level Validation:** Every checkout and booking request checks `expires_at > NOW()`. Stale hold attempts are rejected immediately at the transaction level.
* **Automated Cleanup Worker:** A background scheduler continuously checks for expired holds where `expires_at <= NOW()`. Upon detection, the worker deletes the `seat_holds` record and reverts `ShowSeat.status` back to `AVAILABLE` (or transfers it to the waitlist queue if applicable), ensuring real-time inventory recovery without blocking user requests.

## 2. Concurrency Prevention
Simultaneous requests for the same high-demand seat create race conditions. To guarantee atomic seat allocation and prevent double-booking, the system uses pessimistic row-level locking (`SELECT ... FOR UPDATE NOWAIT`) alongside database-level unique constraints.

When two concurrent requests hit the backend for the same seat:
1. The database locks the targeted `show_seats` row exclusively for Request A.
2. Request B attempts lock acquisition on the same row, fails instantly due to `NOWAIT`, and is rejected immediately with a `400 Bad Request` ("Seat is no longer available").
3. Request A verifies `status == AVAILABLE`, creates the hold record, updates `status` to `HELD`, and commits the transaction.
4. Schema-level unique constraints on `(show_id, seat_id)` serve as a secondary fail-safe against duplicate active holds or bookings.

## 3. Waitlist Auto-Assignment Flow
When an event or seat category sells out, customers can join a First-In, First-Out (FIFO) queue stored in the `waitlists` table. Queue priority is calculated based on `created_at ASC` and filtered by `category` and `status == PENDING`.

When a booking is cancelled or a hold expires:
1. The system invokes the `process_waitlist_for_seat` service task before releasing the seat to the general public.
2. The service queries the `waitlists` queue for the oldest `PENDING` user matching the show and seat category.
3. If a matching waitlisted user exists:
   * The freed seat's status transitions to `OFFERED`.
   * The waitlist entry updates from `PENDING` to `OFFERED`.
   * The seat is reserved exclusively for that user.

## 4. Time-Limited Offer Handling
Waitlist offers are granted with a strict time-limited claim window (`offer_expires_at = NOW() + 10 minutes`).

* **Notification:** Upon offer generation, an asynchronous background task dispatches an email notification containing a personalized, time-limited checkout link.
* **Fulfillment:** If the customer accesses the link and completes checkout within 10 minutes, the waitlist entry transitions to `FULFILLED`, the seat updates to `BOOKED`, and a QR code ticket is issued.
* **Expiration Handling:** If the 10-minute window elapses without completion, the scheduled expiration job marks the waitlist record as `EXPIRED`. The engine then recursively invokes `process_waitlist_for_seat` to offer the seat to the next user in the FIFO queue. If no further waitlisted candidates exist, the seat status reverts to `AVAILABLE` for general public booking.