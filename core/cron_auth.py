import secrets

from fastapi import Header, HTTPException, Response

from core.config import settings


def require_cron_secret(
    response: Response,
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None),
):
    response.headers["Cache-Control"] = "no-store"
    secret = settings.cron_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Cron secret is not configured")
    expected = f"Bearer {secret}".encode()
    bearer_valid = secrets.compare_digest((authorization or "").encode(), expected)
    legacy_valid = secrets.compare_digest((x_cron_secret or "").encode(), secret.encode())
    if not (bearer_valid or legacy_valid):
        raise HTTPException(status_code=401, detail="Unauthorized")
