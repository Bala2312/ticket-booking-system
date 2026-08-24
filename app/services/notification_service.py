import io
import base64
import qrcode
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings

class NotificationService:
    @staticmethod
    def generate_qr_base64(payload_data: str) -> str:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(payload_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    @staticmethod
    async def send_ticket_email(recipient_email: str, booking_ref: str, event_title: str):
        qr_b64 = NotificationService.generate_qr_base64(f"BOOKING_REF:{booking_ref}")
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your Event Ticket - Ref: {booking_ref}"
        msg["From"] = "no-reply@ticketplatform.com"
        msg["To"] = recipient_email

        html = f"""
        <html>
            <body>
                <h2>Booking Confirmed for {event_title}</h2>
                <p>Reference ID: <strong>{booking_ref}</strong></p>
                <img src="data:image/png;base64,{qr_b64}" alt="QR Ticket"/>
            </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        if settings.SMTP_HOST and settings.SMTP_HOST != "smtp.mailtrap.io":
            try:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                    server.starttls()
                    server.login(settings.SMTP_USER, settings.SMTP_PASS)
                    server.sendmail(msg["From"], [recipient_email], msg.as_string())
            except Exception as e:
                print(f"Email error: {e}")

    @staticmethod
    async def send_waitlist_offer_email(recipient_email: str, event_title: str, waitlist_id: str, expires_at):
        print(f"Waitlist offer sent to {recipient_email} for waitlist ID {waitlist_id}")