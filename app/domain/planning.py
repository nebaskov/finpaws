"""Pure budget/report math shared by the CLI service, the REST API, and the agent tools.

Keeping this logic in one place avoids the three slightly different copies that the
endpoints, the agent tools, and ``FinanceService`` used to carry around.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from app.domain.models import TransactionKind

#: Money is rounded to whole kopecks/cents everywhere it is reported to a user.
CENTS = Decimal("0.01")
_ZERO = Decimal("0")

#: A budget aims to leave 20% of income unspent, so category limits sum to 80%.
_BUDGET_SAVINGS_RATE = Decimal("0.8")

#: Fallback split (the classic 50/30/20-ish allocation) used when there is no history.
DEFAULT_BUDGET_WEIGHTS: Mapping[str, Decimal] = {
    "housing": Decimal("0.30"),
    "food": Decimal("0.20"),
    "transport": Decimal("0.10"),
    "utilities": Decimal("0.10"),
    "shopping": Decimal("0.10"),
    "entertainment": Decimal("0.10"),
    "other": Decimal("0.10"),
}


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENTS)


def totals_by_category(items: Iterable[tuple[str, Decimal]]) -> dict[str, Decimal]:
    """Sum ``(category, amount)`` pairs into a ``{category: total}`` mapping."""
    totals: dict[str, Decimal] = {}
    for category, amount in items:
        totals[category] = totals.get(category, _ZERO) + amount
    return totals


# A history below this many distinct categories is too sparse to scale into a sensible budget —
# we use the standard weights instead so a single transport receipt doesn't yield a 100%-transport plan.
_MIN_HISTORY_CATEGORIES = 3


def budget_limits(monthly_income: Decimal, history: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """Per-category monthly limits.

    With *enough* spending history (≥ :data:`_MIN_HISTORY_CATEGORIES` distinct categories), scale
    each category's share of past spending to 80% of ``monthly_income``; otherwise fall back to
    :data:`DEFAULT_BUDGET_WEIGHTS`.
    """
    spent_total = sum(history.values(), start=_ZERO)
    if len(history) < _MIN_HISTORY_CATEGORIES or spent_total <= _ZERO:
        return {
            category: round_money(monthly_income * weight)
            for category, weight in DEFAULT_BUDGET_WEIGHTS.items()
        }
    return {
        category: round_money(amount / spent_total * monthly_income * _BUDGET_SAVINGS_RATE)
        for category, amount in history.items()
    }


@dataclass(frozen=True, slots=True)
class ReportTotals:
    income: Decimal
    spent: Decimal
    by_category: dict[str, Decimal]
    transactions_count: int = 0

    @property
    def balance(self) -> Decimal:
        return self.income - self.spent

    def rounded(self) -> ReportTotals:
        return ReportTotals(
            income=round_money(self.income),
            spent=round_money(self.spent),
            by_category={category: round_money(amount) for category, amount in self.by_category.items()},
            transactions_count=self.transactions_count,
        )


def summarize(rows: Iterable[tuple[str, str, Decimal]]) -> ReportTotals:
    """Aggregate ``(kind, category, amount)`` rows into income / spent / per-category totals."""
    income = _ZERO
    spent = _ZERO
    by_category: dict[str, Decimal] = {}
    count = 0
    for kind, category, amount in rows:
        count += 1
        if kind == TransactionKind.EXPENSE:
            spent += amount
            by_category[category] = by_category.get(category, _ZERO) + amount
        else:
            income += amount
    return ReportTotals(income=income, spent=spent, by_category=by_category, transactions_count=count)
