import html
import io
import logging
import re
import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import qrcode

from ..config.settings import settings

logger = logging.getLogger(__name__)

# Fail fast if the SMTP host is unreachable (e.g. port 587 blocked) instead
# of stalling the consumer loop.
_SMTP_TIMEOUT_SECONDS = 15

# Referenced from the HTML body as <img src="cid:qr_code">.
QR_CONTENT_ID = "qr_code"
_QR_FILENAME = "gallery-qr.png"
# Marks the QR section of the HTML body, dropped if generation fails.
_QR_BLOCK = re.compile(r"<!--qr-->.*?<!--/qr-->", re.S)


def generate_qr_png(url: str) -> bytes:
    """PNG bytes of a QR code encoding `url`, rendered in memory."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf)  # PNG
    return buf.getvalue()


def _qr_part(png: bytes, inline: bool) -> MIMEImage:
    part = MIMEImage(png, "png")
    if inline:
        part.add_header("Content-ID", f"<{QR_CONTENT_ID}>")
        part.add_header("Content-Disposition", "inline", filename=_QR_FILENAME)
    else:
        part.add_header("Content-Disposition", "attachment", filename=_QR_FILENAME)
    return part


def build_mime_message(sender: str, to: str, subject: str, text_body: str, html_body: str,
                       qr_png: bytes | None) -> MIMEMultipart:
    """Without a QR: multipart/alternative (text + HTML). With one:

        multipart/mixed
        ├── multipart/related
        │   ├── multipart/alternative (text, HTML with <img src="cid:qr_code">)
        │   └── image/png  inline, Content-ID <qr_code>
        └── image/png  attachment (same QR, for saving/printing)
    """
    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(text_body, "plain", "utf-8"))
    alternative.attach(MIMEText(html_body, "html", "utf-8"))

    if qr_png is None:
        msg = alternative
    else:
        related = MIMEMultipart("related")
        related.attach(alternative)
        related.attach(_qr_part(qr_png, inline=True))
        msg = MIMEMultipart("mixed")
        msg.attach(related)
        msg.attach(_qr_part(qr_png, inline=False))

    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    return msg


class EmailService:
    def send(self, to: str, subject: str, text_body: str, html_body: str, qr_url: str | None = None) -> bool:
        """Send via SMTP (STARTTLS). Never raises: if SMTP_USER/SMTP_PASSWORD
        aren't set, or the send fails (connection, TLS, auth, rejected
        recipient, ...), the full email is logged instead. Returns True only
        if the SMTP server accepted the message.

        With `qr_url`, a QR code for it is embedded inline (cid:qr_code) and
        also attached. The QR is generated before the SMTP attempt, so the
        log-only fallback still proves generation works. If generation
        itself fails, the email goes out without it."""
        sender = settings.from_address

        qr_png, qr_note = None, ""
        if qr_url:
            try:
                qr_png = generate_qr_png(qr_url)
                qr_note = f"[QR Code generated for: {qr_url}] ({len(qr_png)} bytes PNG, inline cid:{QR_CONTENT_ID} + attachment)\n"
            except Exception as e:
                logger.error(f"QR code generation failed for {qr_url}: {e} — sending without it")
                qr_note = f"[QR Code generation FAILED for: {qr_url}]\n"
                html_body = _QR_BLOCK.sub("", html_body)  # no broken-image icon

        try:
            if not settings.smtp_user or not settings.smtp_password:
                raise RuntimeError("SMTP_USER / SMTP_PASSWORD not set")

            msg = build_mime_message(sender, to, subject, text_body, html_body, qr_png)

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
                f"{qr_note}"
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
    <!--qr--><p>Or scan this QR code with your phone:<br>
      <img src="cid:{QR_CONTENT_ID}" alt="QR Code" width="200" height="200" style="display:block;margin-top:8px;">
    </p><!--/qr-->
    <p><strong>Important:</strong> sign in with Google using this invited account
      (<strong>{e_email}</strong>). Access is limited to invited Google accounts, so
      signing in with a different account won't show you the gallery.</p>
    <p>— The ScanMe team</p>
  </body>
</html>
"""
    return subject, text_body, html_body


email_service = EmailService()
