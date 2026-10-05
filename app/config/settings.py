from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    redis_url:      str = "redis://localhost:6379/0"
    stream_name:    str = "guest.invited"
    consumer_group: str = "notification-workers"
    consumer_name:  str = "notifier-1"
    # SMTP (Gmail for testing: SMTP_USER is the Gmail address, SMTP_PASSWORD
    # a Google App Password — not the account password). When either is
    # unset, or the send fails, the worker logs the full email instead.
    smtp_host:      str = "smtp.gmail.com"
    smtp_port:      int = 587
    smtp_user:      str | None = None
    smtp_password:  str | None = None
    # "From" address. Gmail rewrites any From that isn't the authenticated
    # account (or a verified alias of it), so this defaults to SMTP_USER.
    sender_email:   str | None = None

    @property
    def from_address(self) -> str:
        return self.sender_email or self.smtp_user or "no-reply@scanme.app"

settings = Settings()
