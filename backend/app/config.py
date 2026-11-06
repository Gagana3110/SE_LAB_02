import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./dfs_local.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = ""
    session_minutes: int = 30
    cookie_secure: bool = False
    admin_email: str = ""
    admin_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_from: str = "no-reply@dfs-demo.com"
    app_base_url: str = "http://localhost:8080"
    reset_minutes: int = 30

    def model_post_init(self, __context) -> None:
        # Without a configured secret, sessions simply end when the app restarts.
        if not self.jwt_secret:
            self.jwt_secret = secrets.token_urlsafe(32)


settings = Settings()
