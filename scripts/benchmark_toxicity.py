"""Benchmark the rule-based toxicity detector: latency + quality on a small labeled corpus.

uv run python scripts/benchmark_toxicity.py
make bench-toxicity
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass

from app.agent.safety import score_toxicity


@dataclass(frozen=True, slots=True)
class Case:
    text: str
    toxic: bool
    category: str | None = None  # one of: "obscenity", "insult", "threat", "en-toxic", or None


# Curated in-house corpus. Toxic examples cover the categories the detector targets;
# non-toxic examples include morphological near-misses (e.g. "херувимы", "перебежать")
# that share substrings with toxic stems, to expose false positives. Where a phrase is
# genuinely ambiguous (e.g. "сука-собака" — a female dog vs an insult), it's labelled
# according to what the rule-based detector *should* output given context-free input.
CORPUS: tuple[Case, ...] = (
    # --- obscenity (Russian mat) — incl. prefixed forms (за-/на-/о-) ---
    Case("какого хуя ты творишь", True, "obscenity"),
    Case("пиздец твоей системе, ничего не работает", True, "obscenity"),
    Case("заебал уже своими отчётами", True, "obscenity"),
    Case("охуенно работает, спасибо", True, "obscenity"),
    Case("блядь, ты опять всё сломал", True, "obscenity"),
    Case("ты мудак конченый", True, "obscenity"),
    Case("иди нахуй со своими советами", True, "obscenity"),
    Case("ёбаный бот, опять глючит", True, "obscenity"),
    Case("полная херня, не работает", True, "obscenity"),
    Case("мне на это насрать", True, "obscenity"),
    # --- insult (Russian) ---
    Case("ты тупой как пробка", True, "insult"),
    Case("полный идиот этот твой котик", True, "insult"),
    Case("ты дебил совсем что ли", True, "insult"),
    Case("какой же ты урод после этого", True, "insult"),
    Case("ублюдок, опять подсунул не то", True, "insult"),
    Case("придурок, я же сказал, не то", True, "insult"),
    Case("дурак ты, и шутки твои дурацкие", True, "insult"),
    Case("кретин, считай нормально", True, "insult"),
    # --- threat (Russian) ---
    Case("я тебя убью если не покажешь баланс", True, "threat"),
    Case("сдохни уже, бесполезный бот", True, "threat"),
    Case("разорву на части за эту ошибку", True, "threat"),
    Case("грохну тебя и весь твой код", True, "threat"),
    Case("я тебя избью при встрече", True, "threat"),
    Case("повешу тебя на твоих же проводах", True, "threat"),
    # --- en-toxic ---
    Case("you fucking piece of garbage", True, "en-toxic"),
    Case("this is a stupid moron bot", True, "en-toxic"),
    Case("go kill yourself, bot", True, "en-toxic"),
    Case("bullshit, this asshole assistant", True, "en-toxic"),
    Case("oh shit, that broke everything", True, "en-toxic"),
    # --- non-toxic: ordinary finance / chat ---
    Case("покажи отчёт за месяц", False),
    Case("сколько я потратил на еду в апреле", False),
    Case("построй бюджет на доход 150000", False),
    Case("хочу накопить 300000 на отпуск за 12 месяцев", False),
    Case("объясни правило 50 30 20", False),
    Case("конвертируй 1000 рублей в доллары", False),
    Case("какой у меня баланс сейчас", False),
    Case("привет, как дела", False),
    Case("спасибо, помогло", False),
    Case("when is my next salary payment due", False),
    Case("translate this to russian please", False),
    Case("what is the 50/30/20 budgeting rule", False),
    # --- non-toxic: morphological near-misses (must NOT trip the detector) ---
    Case("херувимы поют в храме", False),  # "хер" stem dropped → no FP
    Case("Перебежать дорогу нельзя", False),  # "еб" inside word — no boundary
    Case("Ассертивность — это про психологию", False),  # "ass" inside word
    Case("в углу стоит чугунная сковорода", False),
    Case("ставлю чай на конфорку и смотрю отчёт", False),
)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    return statistics.quantiles(sorted(values), n=100, method="inclusive")[int(p) - 1]


def bench_latency(samples: Iterable[tuple[str, str]], iterations: int = 2_000) -> None:
    print("--- Latency (per call, " + str(iterations) + " runs/sample) ---")
    print(f"{'sample':<20} {'mean':>8} {'p50':>8} {'p95':>8} {'p99':>8}")
    for label, text in samples:
        # warm-up
        for _ in range(50):
            score_toxicity(text)
        durations: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter_ns()
            score_toxicity(text)
            durations.append((time.perf_counter_ns() - t0) / 1000)  # µs
        mean = statistics.mean(durations)
        p50 = statistics.median(durations)
        p95 = _percentile(durations, 95)
        p99 = _percentile(durations, 99)
        print(
            f"{label:<20} {mean:>6.1f}µs {p50:>6.1f}µs {p95:>6.1f}µs {p99:>6.1f}µs"
            f"   throughput ≈ {1_000_000 / mean:>10,.0f}/s"
        )


def bench_quality(corpus: tuple[Case, ...]) -> None:
    print("\n--- Quality on the labeled corpus (" + str(len(corpus)) + " cases) ---")
    tp = fp = tn = fn = 0
    per_category_tp: dict[str, int] = {}
    per_category_total: dict[str, int] = {}
    false_positives: list[tuple[str, list[str]]] = []
    false_negatives: list[str] = []
    for case in corpus:
        report = score_toxicity(case.text)
        predicted_toxic = report.score >= 0.5
        if case.toxic:
            per_category_total[case.category or "?"] = per_category_total.get(case.category or "?", 0) + 1
        if case.toxic and predicted_toxic:
            tp += 1
            if case.category:
                per_category_tp[case.category] = per_category_tp.get(case.category, 0) + 1
        elif case.toxic and not predicted_toxic:
            fn += 1
            false_negatives.append(case.text)
        elif not case.toxic and predicted_toxic:
            fp += 1
            false_positives.append((case.text, report.hits))
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(corpus)

    print(f"  overall   precision={precision:.2f}  recall={recall:.2f}  F1={f1:.2f}  accuracy={accuracy:.2f}")
    print(f"  confusion  TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print("  per-category recall:")
    for category in ("obscenity", "insult", "threat", "en-toxic"):
        total = per_category_total.get(category, 0)
        caught = per_category_tp.get(category, 0)
        if total:
            print(f"    {category:<10} {caught}/{total} ({caught / total:.0%})")

    if false_positives:
        print("\n  False positives (non-toxic flagged):")
        for text, hits in false_positives:
            print(f"    - {text!r:<60} hits={hits}")
    if false_negatives:
        print("\n  False negatives (toxic missed):")
        for text in false_negatives:
            print(f"    - {text!r}")


def main() -> None:
    print("=== FinPaws rule-based toxicity bench ===\n")
    bench_latency(
        [
            ("short (12 chars)", "ты тупой"),
            ("medium (80 chars)", "Какого хуя ты опять подсунул мне неправильный отчёт, бесполезный бот?"),
            ("long (400 chars)", "Доход 150000. " + "куплено молока и хлеба, потом метро. " * 10),
            ("clean medium", "покажи отчёт за последний месяц с разбивкой по категориям"),
        ]
    )
    bench_quality(CORPUS)


if __name__ == "__main__":
    main()
