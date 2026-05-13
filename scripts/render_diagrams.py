"""Render the Mermaid diagrams in ``docs/diagrams/*.md`` to SVG via mermaid.ink.

No local Node/puppeteer needed — POSTs nothing, just GETs ``https://mermaid.ink/svg/<base64>``.
A non-SVG response (or embedded "syntax error") fails the run, so this doubles as a syntax check.

    uv run python scripts/render_diagrams.py
    make diagrams
"""

from __future__ import annotations

import base64
import re
import urllib.request
from pathlib import Path

_DIAGRAMS_DIR = Path(__file__).resolve().parent.parent / "docs" / "diagrams"
_UA = "Mozilla/5.0 (FinPaws-docs render_diagrams.py)"
_BLOCK_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)

# (source .md, 0-based mermaid-block index, output .svg) — multi-block files list each block.
_JOBS: tuple[tuple[str, int, str], ...] = (
    ("c4-context.md", 0, "c4-context.svg"),
    ("c4-container.md", 0, "c4-container.svg"),
    ("c4-component.md", 0, "c4-component.svg"),
    ("data-flow.md", 0, "data-flow.svg"),
    ("workflow.md", 0, "workflow-sequence.svg"),
    ("workflow.md", 1, "workflow-state.svg"),
)


def _render(code: str) -> bytes:
    token = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")
    url = f"https://mermaid.ink/svg/{token}?theme=neutral&bgColor=ffffff"
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=120) as resp:
        data: bytes = resp.read()
    if not data.lstrip().startswith(b"<svg"):
        raise RuntimeError(f"mermaid.ink did not return SVG: {data[:120]!r}")
    if b"Syntax error" in data or b"Parse error" in data:
        raise RuntimeError("mermaid.ink rendered a syntax-error placeholder — check the diagram source")
    return data


def main() -> int:
    failures = 0
    for src_name, block_idx, out_name in _JOBS:
        src = _DIAGRAMS_DIR / src_name
        blocks = _BLOCK_RE.findall(src.read_text(encoding="utf-8"))
        if block_idx >= len(blocks):
            print(f"!! {src_name}: no mermaid block #{block_idx}")
            failures += 1
            continue
        try:
            svg = _render(blocks[block_idx].rstrip())
        except Exception as exc:  # noqa: BLE001 - report and continue to the next diagram
            print(f"!! {out_name}: {exc}")
            failures += 1
            continue
        (_DIAGRAMS_DIR / out_name).write_bytes(svg)
        print(f"ok  {out_name}  ({len(svg):,} bytes)")
    if failures:
        print(f"\n{failures} diagram(s) failed")
        return 1
    print(f"\nrendered {len(_JOBS)} diagrams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
