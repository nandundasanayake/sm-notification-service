import html
import logging

import boto3

from ..config.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self._client = None

    def _ses(self):
        # Created lazily so a bad AWS config surfaces inside send()'s
        # try/except (and falls back to logging) instead of at startup.
        if self._client is None:
            kwargs = {"region_name": settings.aws_region}
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                kwargs["aws_access_key_id"] = settings.aws_access_key_id
                kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            self._client = boto3.client("ses", **kwargs)
        return self._client

    def send(self, to: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send via SES. Never raises: on any failure (missing credentials,
        unverified identities, throttling, ...) the full email is logged
        instead. Returns True only if SES accepted the message."""
        sender = settings.ses_sender_email
        try:
            resp = self._ses().send_email(
                Source=sender,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                    },
                },
            )
            logger.info(f"✉️ Sent '{subject}' to {to} (SES MessageId={resp.get('MessageId')})")
            return True
        except Exception as e:
            logger.warning(
                f"SES send failed ({type(e).__name__}: {e}) — logging email instead:\n"
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
