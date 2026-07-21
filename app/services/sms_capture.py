"""Server-side LLM SMS extractor for expense capture.

Takes raw SMS text (financial bank/UPI notifications only) and turns it into a
structured ``SmsExpense`` using the user's own LLM key + category tree context.
This is a **standalone** structured-output path, separate from the conversational
agent graph.
"""

from __future__ import annotations

import datetime as dt
import logging

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..services.agent.llm import get_model
from ..services.agent.tools import format_user_categories

logger = logging.getLogger("sms_capture")


# ------------------------------- Pydantic model ------------------------------- #
class SmsExpense(BaseModel):
    """Structured extraction from a single financial SMS."""

    is_expense: bool = Field(
        ...,
        description="True if this SMS represents an expense/debit. False for OTP, "
        "credit, refund, promo, or notification-only messages.",
    )
    amount: float = Field(
        ...,
        description="Expense amount as a positive number (INR). Must be extractable "
        "from the SMS text.",
    )
    direction: str = Field(
        default="debit",
        description="'debit' for expenses, 'credit' for refunds/credits.",
    )
    category: str = Field(
        ...,
        description="Most appropriate existing category name (e.g. 'Food', 'Transport') "
        "or 'Uncategorized' if unclear. Must match an existing user category when "
        "possible.",
    )
    parent_category: str | None = Field(
        None,
        description="Parent category name if the extracted category should be nested.",
    )
    subtitle: str | None = Field(
        None,
        description="Short label shown in UI (e.g. 'Dinner at Toit', 'UPI - Amazon').",
    )
    description: str | None = Field(
        None,
        description="Optional longer detail from the SMS.",
    )
    note: str | None = Field(
        None,
        description="Additional context, e.g. last 4 digits, merchant details.",
    )
    occurred_on: str | None = Field(
        None,
        description="Date in 'YYYY-MM-DD' format, or relative like 'today', 'yesterday'. "
        "Null if no date info in SMS.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this extraction (0.0 = very unsure, 1.0 = very sure).",
    )


# ------------------------------- Prompt template ------------------------------- #
_SYSTEM_PROMPT = """\
You are an expense extraction assistant. You receive financial SMS notifications \
(from Indian banks/UPI apps) and must extract structured expense data.

Rules:
- Return is_expense=false for OTP, promo, credit, refund, or non-expense messages.
- Amount is always a positive number in INR.
- Category must be one of the user's existing categories when possible, or \
"Uncategorized" if nothing matches.
- Use the place_label (from GPS reverse-geocoding) to disambiguate categories \
(e.g., restaurant → Food, petrol pump → Transport/Fuel).
- Resolve relative dates (today, yesterday) against today's date.
- Set confidence based on how clear the extraction is.
- subtitle should be a short label like "Dinner at Toit" or "UPI - Amazon Pay".
- If the SMS is not about a financial transaction at all, set is_expense=false.
"""

_USER_PROMPT_TEMPLATE = """\
Extract expense data from the following SMS:

**SMS Text:**
{sms_text}

**Sender:** {sender}
**Received:** {received_at}
**Location:** {place_label} ({lat}, {lng})

**Today's date:** {today}

**Your existing categories (indentation = sub-category):**
{categories}

Respond with valid JSON matching the required schema.
"""


# ------------------------------- Extractor ------------------------------- #
def _parse_date_str(s: str | None, today: dt.date) -> dt.date | None:
    """Parse a date string, resolving relative dates against *today*."""
    if not s:
        return None
    s_lower = s.strip().lower()
    if s_lower == "today":
        return today
    if s_lower == "yesterday":
        return today - dt.timedelta(days=1)
    try:
        return dt.datetime.strptime(s_lower, "%Y-%m-%d").date()
    except ValueError:
        return None


async def extract_with_context(
    *,
    db: Session,
    user_id: int,
    sms_text: str,
    sender: str | None = None,
    received_at: dt.datetime | None = None,
    lat: float | None = None,
    lng: float | None = None,
    place_label: str | None = None,
    model_override: str | None = None,
) -> dict:
    """Full extraction with user context (categories, DB session).

    This is the primary entry point called from the API endpoint.
    """
    today = dt.date.today()

    # Build category context for the user
    categories_ctx = format_user_categories(db, user_id)

    # Get the model (possibly with SMS-specific override)
    model = get_model(model_override)
    structured_model = model.with_structured_output(SmsExpense)

    # Build prompt
    prompt = _USER_PROMPT_TEMPLATE.format(
        sms_text=sms_text,
        sender=sender or "unknown",
        received_at=received_at.isoformat() if received_at else "unknown",
        place_label=place_label or "unknown",
        lat=lat if lat is not None else "unknown",
        lng=lng if lng is not None else "unknown",
        today=today.isoformat(),
        categories=categories_ctx,
    )

    result = structured_model.invoke(prompt)

    return {
        "is_expense": result.is_expense,
        "amount": float(result.amount),
        "direction": result.direction,
        "category": result.category,
        "parent_category": result.parent_category,
        "subtitle": result.subtitle,
        "description": result.description,
        "note": result.note,
        "occurred_on": _parse_date_str(result.occurred_on, today),
        "confidence": float(result.confidence),
    }