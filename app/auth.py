from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .db import get_db
from .seed import seed_default_categories

_firebase_ready = False


def _init_firebase() -> None:
    """Initialise the firebase-admin app once (lazy — dev mode never needs it)."""
    global _firebase_ready
    if _firebase_ready:
        return
    import firebase_admin
    from firebase_admin import credentials

    settings = get_settings()
    if not firebase_admin._apps:
        if settings.firebase_credentials_file:
            cred = credentials.Certificate(settings.firebase_credentials_file)
            firebase_admin.initialize_app(cred)
        else:
            # Falls back to Application Default Credentials.
            firebase_admin.initialize_app()
    _firebase_ready = True


def _verify_firebase_token(token: str) -> dict:
    _init_firebase()
    from firebase_admin import auth as fb_auth

    try:
        return fb_auth.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001 - surface any verification failure as 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Firebase token: {exc}",
        ) from exc


def get_or_create_user(
    db: Session, uid: str, email: str | None = None, name: str | None = None
) -> models.User:
    user = db.query(models.User).filter(models.User.firebase_uid == uid).first()
    if user:
        return user
    user = models.User(firebase_uid=uid, email=email, display_name=name)
    db.add(user)
    db.commit()
    db.refresh(user)
    seed_default_categories(db, user.id)
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
    x_dev_uid: str | None = Header(default=None),
    x_dev_email: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    settings = get_settings()

    if settings.auth_mode == "dev":
        uid = x_dev_uid or "dev-user"
        email = x_dev_email or f"{uid}@example.com"
        return get_or_create_user(db, uid, email, name="Dev User")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
    decoded = _verify_firebase_token(token)
    return get_or_create_user(
        db, decoded["uid"], decoded.get("email"), decoded.get("name")
    )
