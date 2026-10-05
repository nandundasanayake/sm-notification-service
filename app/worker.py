import logging, sys, time
import redis

from .config.settings import settings
from .services.email import email_service, build_guest_invite

# Explicit stdout handler at INFO so `docker logs` shows everything, even if
# an imported library configured the root logger first (force=True).
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

# Redis Stream setup
r = redis.from_url(settings.redis_url,
    decode_responses=True,
    socket_timeout=10,          # must exceed the 5s xreadgroup block below
    socket_connect_timeout=5,
    retry_on_timeout=True,)

def ensure_stream_group():
    try:
        r.xgroup_create(settings.stream_name, settings.consumer_group, id="0", mkstream=True)
        logger.info(f"Consumer group '{settings.consumer_group}' created")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info("Consumer group already exists")
        else:
            raise

# Handlers
def handle_guest_invited(data: dict):
    guest_email = data.get("guest_email")
    gallery_url = data.get("gallery_url")
    event_name  = data.get("event_name") or "your event"
    if not guest_email or not gallery_url:
        logger.error(f"Malformed Guest.Invited message, skipping: {data}")
        return

    subject, text_body, html_body = build_guest_invite(event_name, gallery_url, guest_email)
    # send() never raises — SMTP failures fall back to logging the email.
    if email_service.send(guest_email, subject, text_body, html_body):
        publish_email_sent(data.get("event_id"), guest_email)

def publish_email_sent(event_id: str | None, guest_email: str):
    """Delivery receipt for sm-photographer-service (sets
    event_collaborators.email_status). Only after a real SMTP send — a
    logged-only fallback email leaves the guest PENDING. Non-fatal: the
    email is already out, so a lost receipt only leaves the status stale."""
    try:
        r.xadd(settings.email_sent_stream, {
            "event_id": event_id or "",
            "guest_email": guest_email,
            "status": "SENT",
        })
    except Exception as e:
        logger.error(f"Failed to publish {settings.email_sent_stream} for {guest_email} on {event_id}: {e}")

# Main consumer loop
def run():
    logger.info(f"✓ Notification worker started — listening on Redis Stream '{settings.stream_name}' at {settings.redis_url}")

    # Broker may not be up yet (it lives outside Compose, so there's no
    # depends_on to wait on) — keep retrying instead of exiting silently.
    while True:
        try:
            ensure_stream_group()
            break
        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Redis not reachable at {settings.redis_url} ({e}), retrying in 5s...")
            time.sleep(5)

    while True:
        try:
            messages = r.xreadgroup(
                settings.consumer_group,
                settings.consumer_name,
                {settings.stream_name: ">"},
                count=10,
                block=5000   # block 5s waiting for messages
            )

            if not messages:
                continue

            for stream, entries in messages:
                for msg_id, data in entries:
                    logger.info(f"Guest.Invited {msg_id}: event={data.get('event_id')} to={data.get('guest_email')}")
                    try:
                        handle_guest_invited(data)
                    except Exception as e:
                        # Email is best-effort; don't let one bad message
                        # stall the stream or be redelivered forever.
                        logger.error(f"Message {msg_id} failed: {e}")
                    r.xack(settings.stream_name, settings.consumer_group, msg_id)

        except redis.exceptions.ConnectionError:
            logger.warning("Redis connection lost, retrying in 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Worker stopped")
            break

if __name__ == "__main__":
    run()
