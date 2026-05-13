"""Benchmark the rule-based toxicity detector against the external RuToxic corpus.

Dataset: ``AlexSham/Toxic_Russian_Comments`` (Odnoklassniki / Pikabu comments, binary labels) —
the same family of data ``cointegrated/rubert-tiny-toxicity`` was trained on. ~25k labelled
comments in the test split. The file is downloaded once to ``data/`` (git-ignored) if absent.

This is an *out-of-distribution* benchmark: the corpus was not built around our stem list, so it
shows the real recall ceiling of a pure-regex detector and where it leaks.

    uv run python scripts/benchmark_rutoxic.py
    make bench-rutoxic
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.agent.safety import score_toxicity
from app.config import SETTINGS

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATASET_PATH = _DATA_DIR / "rutoxic_test.jsonl"
_DATASET_URL = "https://huggingface.co/datasets/AlexSham/Toxic_Russian_Comments/resolve/main/test.jsonl"


@dataclass(frozen=True, slots=True)
class Row:
    text: str
    toxic: bool


def _ensure_dataset() -> None:
    if _DATASET_PATH.exists():
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading {_DATASET_URL} -> {_DATASET_PATH} ...")
    with urllib.request.urlopen(_DATASET_URL) as resp:
        _DATASET_PATH.write_bytes(resp.read())


def load_rows() -> list[Row]:
    _ensure_dataset()
    rows: list[Row] = []
    with _DATASET_PATH.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append(Row(text=str(obj["text"]), toxic=int(obj["label"]) == 1))
    return rows


def main() -> None:
    threshold = SETTINGS.toxicity_threshold
    print("=== FinPaws rule-based toxicity vs RuToxic (external) ===\n")
    rows = load_rows()
    n_toxic = sum(1 for r in rows if r.toxic)
    print(f"corpus: {len(rows):,} comments  ({n_toxic:,} toxic / {len(rows) - n_toxic:,} non-toxic)")
    print(f"decision threshold: score >= {threshold}\n")

    tp = fp = tn = fn = 0
    false_positives: list[tuple[str, list[str]]] = []
    false_negatives: list[str] = []
    t0 = time.perf_counter()
    for row in rows:
        report = score_toxicity(row.text)
        predicted = report.score >= threshold
        if row.toxic and predicted:
            tp += 1
        elif row.toxic and not predicted:
            fn += 1
            if len(false_negatives) < 20:
                false_negatives.append(row.text)
        elif not row.toxic and predicted:
            fp += 1
            if len(false_positives) < 20:
                false_positives.append((row.text, report.hits))
        else:
            tn += 1
    elapsed = time.perf_counter() - t0

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(rows)
    # Specificity / "toxic-spam rate": of the non-toxic comments, how many got flagged.
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print("--- Quality ---")
    print(f"  precision={precision:.3f}  recall={recall:.3f}  F1={f1:.3f}  accuracy={accuracy:.3f}")
    print(f"  confusion  TP={tp:,}  FP={fp:,}  TN={tn:,}  FN={fn:,}")
    print(f"  false-positive rate (flagged | non-toxic) = {fpr:.3%}")

    print("\n--- Latency over the whole corpus ---")
    per_call_us = elapsed / len(rows) * 1_000_000
    print(
        f"  {len(rows):,} comments in {elapsed:.2f}s  ->  {per_call_us:.1f}µs/comment  (~{1 / (elapsed / len(rows)):,.0f}/s)"
    )

    if false_negatives:
        print("\n--- Sample false negatives (toxic, missed) ---")
        for text in false_negatives[:12]:
            print(f"  - {text[:120]!r}")
    if false_positives:
        print("\n--- Sample false positives (non-toxic, flagged) ---")
        for text, hits in false_positives[:12]:
            print(f"  - {text[:120]!r}  hits={hits}")


if __name__ == "__main__":
    main()
