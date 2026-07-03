import base64
import json
import threading
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .db import get_db
from .seed import seed_default_categories

_init_lock = threading.Lock()


def _parse_service_account(raw: str) -> dict:
    """Parse a service-account JSON string, accepting raw JSON or base64 JSON.

    Some env editors choke on raw JSON (quotes + embedded ``\\n``); base64
    sidesteps that — encode the JSON once and paste a single clean token.
    """
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    try:
        # binascii.Error and UnicodeDecodeError both subclass ValueError.
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
    except ValueError as exc:
        raise ValueError(
            "FIREBASE_CREDENTIALS_JSON is neither valid JSON nor base64-encoded JSON."
        ) from exc
    return json.loads(decoded)


@lru_cache(maxsize=1)
def _firebase_app():
    """Initialise the firebase-admin app exactly once and return it.

    ``lru_cache`` + a lock make this idempotent even when the first few requests
    race concurrently — otherwise two of them both call ``initialize_app()`` and
    the second raises "The default Firebase app already exists". We also reuse an
    app initialised elsewhere via ``get_app()`` as a belt-and-suspenders guard.

    Credentials are resolved in order: inline JSON (raw or base64) → file path →
    Application Default Credentials.
    """
    import firebase_admin
    from firebase_admin import credentials

    settings = get_settings()
    with _init_lock:
        if firebase_admin._apps:
            return firebase_admin.get_app()

        if settings.firebase_credentials_json:
            cred = credentials.Certificate(
                _parse_service_account(settings.firebase_credentials_json)
            )
        elif settings.firebase_credentials_file:
            cred = credentials.Certificate(settings.firebase_credentials_file)
        else:
            cred = None  # Application Default Credentials

        options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
        if cred is None:
            return firebase_admin.initialize_app(options=options)
        return firebase_admin.initialize_app(cred, options)


def _verify_firebase_token(token: str) -> dict:
    from firebase_admin import auth as fb_auth

    try:
        # Pass the explicit app so verification never triggers a default-app init.
        return fb_auth.verify_id_token(token, app=_firebase_app())
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
