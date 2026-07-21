import datetime as dt

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    firebase_uid: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Category(Base):
    """Flexible, hierarchical category.

    - Any category may have a ``parent_id`` (self-reference), so the LLM can
      create a parent (e.g. "Personal") and a sub-category under it
      (e.g. "Movie tickets") on the fly.
    - ``created_by`` distinguishes user-created vs LLM-created categories.
    - ``type`` / ``image`` / ``tags`` / ``description`` are optional metadata
      the LLM (or user) can enrich over time.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image: Mapped[str | None] = mapped_column(String, nullable=True)  # emoji, icon name, or URL
    type: Mapped[str | None] = mapped_column(String, nullable=True)  # expense | income | investment | ...
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String, default="user")  # user | llm
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    parent: Mapped["Category | None"] = relationship(
        "Category", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(
        "Category", back_populates="parent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "parent_id", "name", name="uq_category_name_per_parent"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True, nullable=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, default="INR")
    occurred_on: Mapped[dt.date] = mapped_column(Date, default=dt.date.today, index=True)
    subtitle: Mapped[str | None] = mapped_column(String(120), nullable=True)  # short label shown in UI
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # longer optional detail
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, default="manual")  # chat | sms | manual
    raw_ref: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. SMS hash for dedupe
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # LLM extraction confidence (0..1)
    reviewed: Mapped[bool] = mapped_column(default=False)  # accepted from review queue
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)  # capture-time GPS
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)  # capture-time GPS
    location_label: Mapped[str | None] = mapped_column(String, nullable=True)  # reverse-geocoded place
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "raw_ref", name="uq_txn_user_rawref"),
    )


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String, nullable=False)  # 'YYYY-MM'
    limit_amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "month", name="uq_budget_cat_month"),
    )


class Investment(Base):
    """Minimal investment record: how much was invested in a month.

    No returns, no live prices — just the amount (optionally per category).
    """

    __tablename__ = "investments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String, nullable=False, index=True)  # 'YYYY-MM'
    category: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "mutual funds"
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class LlmCredential(Base):
    """Per-user bring-your-own LLM key, encrypted at rest (Phase 2 uses this)."""

    __tablename__ = "llm_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    provider: Mapped[str] = mapped_column(String, default="anthropic")
    encrypted_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
