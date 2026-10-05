import html
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config.settings import settings

logger = logging.getLogger(__name__)

# Fail fast if the SMTP host is unreachable (e.g. port 587 blocked) instead
# of stalling the consumer loop.
_SMTP_TIMEOUT_SECONDS = 15


class EmailService:
    def send(self, to: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send via SMTP (STARTTLS). Never raises: if SMTP_USER/SMTP_PASSWORD
        aren't set, or the send fails (connection, TLS, auth, rejected
        recipient, ...), the full email is logged instead. Returns True only
        if the SMTP server accepted the message."""
        sender = settings.from_address
        try:
            if not settings.smtp_user or not settings.smtp_password:
                raise RuntimeError("SMTP_USER / SMTP_PASSWORD not set")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = to
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.sendmail(sender, [to], msg.as_string())

            logger.info(f"✉️ Sent '{subject}' to {to} via {settings.smtp_host}:{settings.smtp_port}")
            return True
        except Exception as e:
            logger.warning(
                f"SMTP send failed ({type(e).__name__}: {e}) — logging email instead:\n"
                f"----- EMAIL -----\n"
                f"From:    {sender}\n"
                f"To:      {to}\n"
                f"Subject: {subject}\n"
                f"\n{text_body}\n"
                f"-----------------"
            )
            return False


def build_guest_invite(event_name: str, gallery_url: str, guest_email: str) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body) for a Guest.Invited email."""
    subject = f"You've been invited to view photos for {event_name}"

    text_body = (
        f"Hi,\n\n"
        f"You've been invited to view the photos from {event_name}.\n\n"
        f"Open the gallery here:\n{gallery_url}\n\n"
        f"IMPORTANT: Sign in with Google using this invited account ({guest_email}). "
        f"Access is limited to invited Google accounts, so signing in with a "
        f"different account won't show you the gallery.\n\n"
        f"— The ScanMe team\n"
    )

    e_name, e_url, e_email = html.escape(event_name), html.escape(gallery_url, quote=True), html.escape(guest_email)
    html_body = f"""\
<html>
  <body style="font-family: Arial, sans-serif; color: #222; line-height: 1.5;">
    <p>Hi,</p>
    <p>You've been invited to view the photos from <strong>{e_name}</strong>.</p>
    <p>
      <a href="{e_url}" style="display:inline-block;padding:10px 18px;background:#111;color:#fff;text-decoration:none;border-radius:6px;">
        View the gallery
      </a>
    </p>
    <p>Or open this link: <a href="{e_url}">{e_url}</a></p>
    <p><strong>Important:</strong> sign in with Google using this invited account
      (<strong>{e_email}</strong>). Access is limited to invited Google accounts, so
      signing in with a different account won't show you the gallery.</p>
    <p>— The ScanMe team</p>
  </body>
</html>
"""
    return subject, text_body, html_body


email_service = EmailService()
