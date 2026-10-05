from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    redis_url:             str = "redis://localhost:6379/0"
    stream_name:           str = "guest.invited"
    consumer_group:        str = "notification-workers"
    consumer_name:         str = "notifier-1"
    # AWS SES. All optional: when credentials are missing or SES rejects the
    # send (e.g. unverified sender/recipient in sandbox mode), the worker
    # logs the full email instead of sending it.
    aws_access_key_id:     str = ""
    aws_secret_access_key: str = ""
    aws_region:            str = "ap-south-1"
    ses_sender_email:      str = "no-reply@scanme.app"

settings = Settings()
