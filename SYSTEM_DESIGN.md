# System Design Write-Up: Ticket Booking Platform

## 1. Seat Hold and TTL Mechanism
To prevent inventory lockup during high-demand event drops, the application uses a dynamic Time-To-Live (TTL) hold strategy. When a user selects seats, their status changes to `HELD` in PostgreSQL, and an entry is added to `seat_holds` with `expires_at = NOW() + 10 minutes`. To ensure real-time cleanup without database polling overhead, a matching key `hold_ttl:{show_seat_id}` is created in Redis with a 10-minute expiration time. When Redis emits a key expiration notification, an asynchronous background task sets the seat back to `AVAILABLE`. Additionally, every purchase attempt validates `expires_at > NOW()` at the database transaction level to reject stale requests.

## 2. Concurrency Protection
Simultaneous requests for the same seat cause race conditions. To guarantee atomic seat allocation, the system uses PostgreSQL Pessimistic Row Locking (`SELECT ... FOR UPDATE NOWAIT`). When Request A and Request B hit the backend concurrently for the same seat ID:
1. PostgreSQL locks the targeted `show_seats` row exclusively for Request A.
2. Request B attempts lock acquisition, fails instantly due to `NOWAIT`, and receives a `400 Bad Request` ("Seats unavailable").
3. Request A verifies status == `AVAILABLE`, sets status to `HELD`, and commits.

## 3. Waitlist Auto-Assignment and Time-Limited Offers
When a seat category is sold out, users can join a FIFO queue stored in the `waitlists` table. When a booking is cancelled or a hold expires:
1. The freed seat is set to state `OFFERED`.
2. The waitlist engine fetches the oldest `PENDING` user for that show and seat category (`ORDER BY created_at ASC`).
3. The entry updates to `OFFERED` with an `offer_expires_at` timestamp set to 15 minutes.
4. An automated email with a claim link is dispatched.
5. If the user completes checkout within 15 minutes, the seat transitions to `BOOKED`. If the offer expires, the scheduler sets the waitlist entry to `EXPIRED`, sets the seat back to `AVAILABLE`, and triggers the queue for the next user.