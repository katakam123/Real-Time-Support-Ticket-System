
import os
import smtplib
from email.message import EmailMessage


def send_email(recipient: str, subject: str, body: str) -> None:
    """Send a plain-text email through the configured SMTP server."""

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or smtp_username

    if not smtp_host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM/SMTP_USERNAME must be configured.")

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = sender
    email["To"] = recipient
    email.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls()

        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)

        server.send_message(email)
