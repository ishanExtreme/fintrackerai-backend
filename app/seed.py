from sqlalchemy.orm import Session

from . import models

# Minimal starter set. The LLM and the user can freely add parents and
# sub-categories on top of these.
DEFAULT_CATEGORIES: list[dict] = [
    {"name": "Food", "image": "🍔"},
    {"name": "Transport", "image": "🚗"},
    {"name": "Shopping", "image": "🛍️"},
    {"name": "Bills", "image": "🧾"},
    {"name": "Health", "image": "🏥"},
    {"name": "Entertainment", "image": "🎬"},
    {"name": "Personal", "image": "🙂"},
    {"name": "Others", "image": "📦"},
]


def seed_default_categories(db: Session, user_id: int) -> None:
    existing = (
        db.query(models.Category.id).filter(models.Category.user_id == user_id).first()
    )
    if existing:
        return
    for entry in DEFAULT_CATEGORIES:
        db.add(
            models.Category(
                user_id=user_id,
                name=entry["name"],
                image=entry.get("image"),
                type="expense",
                tags=[],
                created_by="user",
            )
        )
    db.commit()
