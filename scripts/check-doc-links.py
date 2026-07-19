#!/usr/bin/env python3
"""Markdown リンク検査: 相対パスの実在と見出しアンカーの存在を検証する。

検査対象: リポ内の README*.md / docs/*.md / examples/**/*.md
検査内容(インライン形式 [label](path) / ![alt](path) のみ。reference-style
リンクと本文中の裸のパス文字列は対象外 — 本リポでは使っていない):
  1. 相対リンク(bare パス含む: docs/01_..., README.md, LICENSE 等)の実在
  2. #fragment が対象ファイルの見出しアンカー(GitHub 方式 slug)に存在すること
  3. 画像リンク(![...](path))のパス実在
http(s) / mailto の外部リンクは対象外。CI(ci.yml)から毎 push 実行される。

usage: python3 scripts/check-doc-links.py   (exit 0 = OK / 1 = broken links)
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
CODE_FENCE_RE = re.compile(r"^(```|~~~)")


def github_slug(heading: str) -> str:
    """GitHub 方式の見出しスラグ化(近似): 記号除去・空白→ハイフン・小文字化。

    日本語などの非 ASCII 文字はそのまま残る(GitHub の挙動と同じ)。
    """
    text = re.sub(r"[*_`~\[\]()!]", "", heading).strip()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    text = text.lower().replace(" ", "-")
    return text


def anchors_of(md_path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    in_fence = False
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        slug = github_slug(unicodedata.normalize("NFC", m.group(2)))
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        anchors.add(slug if n == 0 else f"{slug}-{n}")
    return anchors


def iter_md_files():
    yield from REPO.glob("README*.md")
    yield from (REPO / "docs").glob("*.md")
    yield from (REPO / "examples").rglob("*.md")


def main() -> int:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    for md in iter_md_files():
        in_fence = False
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if CODE_FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in LINK_RE.finditer(line):
                raw = m.group(1)
                if raw.startswith(("http://", "https://", "mailto:")):
                    continue
                path_part, _, fragment = raw.partition("#")
                target = md if not path_part else (md.parent / path_part).resolve()
                rel = md.relative_to(REPO)
                if path_part and not target.exists():
                    errors.append(f"{rel}:{lineno}: broken path -> {raw}")
                    continue
                if fragment:
                    if target.is_dir() or target.suffix.lower() != ".md":
                        continue  # md 以外へのアンカーは検査対象外
                    if target not in anchor_cache:
                        anchor_cache[target] = anchors_of(target)
                    frag = unicodedata.normalize("NFC", fragment.lower())
                    if frag not in anchor_cache[target]:
                        errors.append(f"{rel}:{lineno}: missing anchor -> {raw}")
    if errors:
        print(f"[NG] {len(errors)} broken link(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("[OK] all relative links and anchors resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
