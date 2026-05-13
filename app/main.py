from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.domain.models import SavingsGoal
from app.domain.planning import CENTS
from app.services.finance import FinanceService
from app.services.storage import JsonStorage


def _create_service() -> FinanceService:
    return FinanceService(storage=JsonStorage(Path("data") / "state.json"))


def _decimal_arg(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not a valid decimal: {value!r}") from None


def _positive_decimal_arg(value: str) -> Decimal:
    parsed = _decimal_arg(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value!r}")
    return parsed


def _positive_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a valid integer: {value!r}") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value!r}")
    return parsed


def _goal_progress_percent(goal: SavingsGoal) -> Decimal:
    return (goal.saved_amount / goal.target_amount * Decimal("100")).quantize(CENTS)


def _cmd_add_expense(service: FinanceService, args: argparse.Namespace) -> None:
    tx = service.add_expense(args.amount, args.description, args.currency)
    print(f"Added expense {tx.amount} {tx.currency} in category '{tx.category}'")


def _cmd_add_income(service: FinanceService, args: argparse.Namespace) -> None:
    tx = service.add_income(args.amount, args.description, args.currency)
    print(f"Added income {tx.amount} {tx.currency}")


def _cmd_plan(service: FinanceService, args: argparse.Namespace) -> None:
    budget = service.build_budget_plan(args.income)
    print(f"Budget plan created for income {budget.monthly_income}")
    for category, limit in sorted(budget.category_limits.items()):
        print(f"- {category}: {limit}")


def _cmd_add_goal(service: FinanceService, args: argparse.Namespace) -> None:
    goal = service.add_goal(args.name, args.target, args.months)
    per_month = (goal.target_amount / Decimal(goal.horizon_months)).quantize(CENTS)
    print(f"Goal '{goal.name}' added. Save {per_month} per month.")


def _cmd_goal_progress(service: FinanceService, args: argparse.Namespace) -> None:
    goal = service.add_goal_progress(args.name, args.amount)
    print(
        f"Goal '{goal.name}' progress: {goal.saved_amount}/{goal.target_amount} "
        f"({_goal_progress_percent(goal)}%)"
    )


def _cmd_report(service: FinanceService, args: argparse.Namespace) -> None:
    dash = service.dashboard(days=args.days)
    period_unit = "day" if args.days == 1 else "days"
    print(f"Period: {args.days} {period_unit}")
    print(f"Income: {dash.income.quantize(CENTS)}")
    print(f"Spent: {dash.spent.quantize(CENTS)}")
    print(f"Balance: {(dash.income - dash.spent).quantize(CENTS)}")

    if dash.by_category:
        print("Categories:")
        for category, amount in sorted(dash.by_category.items(), key=lambda item: item[1], reverse=True):
            print(f"- {category}: {amount.quantize(CENTS)}")

    if dash.goals:
        print("Goals:")
        for goal in dash.goals:
            print(
                f"- {goal.name}: {goal.saved_amount.quantize(CENTS)}/{goal.target_amount.quantize(CENTS)} "
                f"({_goal_progress_percent(goal)}%)"
            )


CommandHandler = Callable[[FinanceService, argparse.Namespace], None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finpaws", description="FinPaws budget assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_expense = subparsers.add_parser("add-expense", help="Add expense transaction")
    add_expense.add_argument("--amount", type=_positive_decimal_arg, required=True)
    add_expense.add_argument("--description", required=True)
    add_expense.add_argument("--currency", default="RUB")
    add_expense.set_defaults(handler=_cmd_add_expense)

    add_income = subparsers.add_parser("add-income", help="Add income transaction")
    add_income.add_argument("--amount", type=_positive_decimal_arg, required=True)
    add_income.add_argument("--description", default="income")
    add_income.add_argument("--currency", default="RUB")
    add_income.set_defaults(handler=_cmd_add_income)

    report = subparsers.add_parser("report", help="Show summary report")
    report.add_argument("--days", type=_positive_int_arg, default=30)
    report.set_defaults(handler=_cmd_report)

    budget = subparsers.add_parser("plan", help="Build monthly budget plan")
    budget.add_argument("--income", type=_positive_decimal_arg, required=True)
    budget.set_defaults(handler=_cmd_plan)

    goal = subparsers.add_parser("add-goal", help="Create savings goal")
    goal.add_argument("--name", required=True)
    goal.add_argument("--target", type=_positive_decimal_arg, required=True)
    goal.add_argument("--months", type=_positive_int_arg, required=True)
    goal.set_defaults(handler=_cmd_add_goal)

    progress = subparsers.add_parser("goal-progress", help="Add goal progress")
    progress.add_argument("--name", required=True)
    progress.add_argument("--amount", type=_positive_decimal_arg, required=True)
    progress.set_defaults(handler=_cmd_goal_progress)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: CommandHandler = args.handler
    try:
        handler(_create_service(), args)
    except ValueError as exc:
        print(f"finpaws: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
