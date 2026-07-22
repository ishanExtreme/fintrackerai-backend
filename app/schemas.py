import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_month(v: str) -> str:
    if not MONTH_RE.match(v):
        raise ValueError("month must be in 'YYYY-MM' format")
    return v


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    description: str | None = None
    image: str | None = None
    type: str | None = None
    tags: list[str] = Field(default_factory=list)


class CategoryCreate(CategoryBase):
    created_by: str = "user"  # "user" | "llm"


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: int | None = None
    description: str | None = None
    image: str | None = None
    type: str | None = None
    tags: list[str] | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str
    description: str | None
    image: str | None
    type: str | None
    tags: list[str] = Field(default_factory=list)
    created_by: str


class CategoryTree(CategoryOut):
    children: list["CategoryTree"] = Field(default_factory=list)


class TransactionBase(BaseModel):
    amount: float = Field(gt=0)
    category_id: int | None = None
    currency: str = "INR"
    occurred_on: dt.date | None = None
    subtitle: str | None = Field(default=None, max_length=120)
    description: str | None = None
    note: str | None = None


class TransactionCreate(TransactionBase):
    source: str = "manual"  # chat | sms | manual


class TransactionUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    category_id: int | None = None
    currency: str | None = None
    occurred_on: dt.date | None = None
    subtitle: str | None = Field(default=None, max_length=120)
    description: str | None = None
    note: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reviewed: bool | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    amount: float
    currency: str
    occurred_on: dt.date
    subtitle: str | None
    description: str | None
    note: str | None
    source: str
    confidence: float | None
    reviewed: bool
    lat: float | None
    lng: float | None
    location_label: str | None
    counterparty: str | None


class TransactionDeleteResult(BaseModel):
    deleted: int


class SmsIngest(BaseModel):
    """Structured payload produced by on-device SMS/notification parsing.

    Raw SMS text is never sent — only these extracted fields.
    """

    amount: float = Field(gt=0)
    direction: str = "debit"  # debit | credit
    raw_hash: str = Field(min_length=1)  # for dedupe
    merchant: str | None = None
    occurred_on: dt.date | None = None
    account_masked: str | None = None
    category_id: int | None = None


class SmsIngestResult(BaseModel):
    status: str  # created | duplicate | skipped
    transaction: TransactionOut | None = None


class SmsCapture(BaseModel):
    """Raw SMS capture payload from the mobile app."""

    sms_text: str = Field(..., min_length=1)
    sender: str | None = None
    received_at: dt.datetime | None = None
    lat: float | None = None
    lng: float | None = None
    place_label: str | None = None
    raw_hash: str = Field(..., min_length=1)  # dedupe key


class SmsCaptureResult(BaseModel):
    status: str  # created | duplicate | skipped
    transaction: TransactionOut | None = None


class ReviewBatchRequest(BaseModel):
    """Batch review accept for SMS captures."""
    ids: list[int] | None = None  # specific transaction IDs
    month: str | None = None  # all SMS transactions for a month


class ReviewBatchResult(BaseModel):
    updated: int  # number of transactions marked as reviewed


class CaptureRuleIn(BaseModel):
    """Create a 'remember' rule from a structured form.

    kind='payee' needs match_value (+ category_id/subtitle to apply).
    kind='location' needs lat/lng (+ location_name; category_id optional).
    """

    kind: str = Field(..., pattern="^(payee|location)$")
    match_value: str | None = Field(default=None, max_length=200)
    lat: float | None = None
    lng: float | None = None
    radius_m: float | None = Field(default=None, gt=0)
    location_name: str | None = Field(default=None, max_length=120)
    category_id: int | None = None
    subtitle: str | None = Field(default=None, max_length=120)


class CaptureRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    match_value: str | None
    lat: float | None
    lng: float | None
    radius_m: float | None
    location_name: str | None
    category_id: int | None
    subtitle: str | None


class CaptureRuleResult(BaseModel):
    rule: CaptureRuleOut
    applied: int  # existing unreviewed SMS captures updated by this rule


class BudgetUpsert(BaseModel):
    category_id: int
    month: str
    limit_amount: float = Field(gt=0)

    _v_month = field_validator("month")(_validate_month)


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    month: str
    limit_amount: float


class InvestmentCreate(BaseModel):
    amount: float = Field(gt=0)
    month: str
    category: str | None = None
    note: str | None = None

    _v_month = field_validator("month")(_validate_month)


class InvestmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    month: str
    category: str | None
    amount: float
    note: str | None


class SpendingRow(BaseModel):
    category_id: int | None
    category_name: str
    parent_id: int | None
    total: float


class BudgetStatusRow(BaseModel):
    category_id: int
    category_name: str
    month: str
    limit_amount: float
    spent: float
    remaining: float


class MonthlyInvestment(BaseModel):
    month: str
    total: float


class ChatRequest(BaseModel):
    conversation_id: str = Field(..., description="Per-session id == LangGraph thread_id.")
    message: str = Field(..., min_length=1)
    tz: str | None = Field(
        None,
        description="IANA timezone of the user (e.g. 'Asia/Kolkata') used to resolve "
        "'today'/'this month'. Falls back to the server's local date if unset or invalid.",
    )


class ChatEvent(BaseModel):
    """A structured side-effect the app can render (e.g. a budget warning),
    emitted by a tool alongside the natural-language reply."""

    type: str
    data: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    events: list[ChatEvent] = Field(default_factory=list)
    awaiting_user: bool = Field(
        default=False,
        description="True when the reply is a clarifying question; the app should "
        "keep the conversation open and post the answer under the same id.",
    )


class LlmKeyIn(BaseModel):
    api_key: str = Field(..., min_length=1)
    provider: str = "google_genai"


class SmsLlmKeyIn(BaseModel):
    """Set the dedicated SMS-capture LLM key (+ optional cheaper model)."""

    api_key: str = Field(..., min_length=1)
    provider: str = "google_genai"
    model: str | None = None  # optional 'provider:model' override


class LlmKeyStatus(BaseModel):
    configured: bool  # user has stored their own key
    provider: str | None = None
    using: str  # "user" | "shared" | "none"
    model: str | None = None  # SMS key only: the effective model override
