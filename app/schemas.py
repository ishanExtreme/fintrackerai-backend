import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_month(v: str) -> str:
    if not MONTH_RE.match(v):
        raise ValueError("month must be in 'YYYY-MM' format")
    return v


# ----------------------------- Categories -----------------------------
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


# ----------------------------- Transactions -----------------------------
class TransactionBase(BaseModel):
    amount: float = Field(gt=0)
    category_id: int | None = None
    currency: str = "INR"
    occurred_on: dt.date | None = None
    note: str | None = None


class TransactionCreate(TransactionBase):
    source: str = "manual"  # chat | sms | manual


class TransactionUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    category_id: int | None = None
    currency: str | None = None
    occurred_on: dt.date | None = None
    note: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    amount: float
    currency: str
    occurred_on: dt.date
    note: str | None
    source: str


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


# ----------------------------- Budgets -----------------------------
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


# ----------------------------- Investments -----------------------------
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


# ----------------------------- Dashboard -----------------------------
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
