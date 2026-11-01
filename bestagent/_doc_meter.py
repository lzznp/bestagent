# -*- coding: utf-8 -*-
"""_doc_meter.py — 文档量具（§11 ★速查卡约定的"核验器"）：**只量字节，不读内容**。

用法（cwd = bestagent/）：
  python _doc_meter.py

量什么：
  1) 工作文档/*.md 的字节/行数（谁在吃上下文）；
  2) 每份带 `## ★ 速查卡` 的报告：速查卡 vs 全文 的字节占比 + **是否超过 1.5KB 上限**（§11.2 规则 1）；
  3) "最小读集"（速查卡 + §4.1）大概值多少字节。

口径（如实说明，别假装精确）：
  · **不调 tokenizer**（本机没装），只报 UTF-8 字节；
  · 经验换算：中文为主的 markdown ≈ **2.5 字节/词元** → "词元 ≈ 字节 / 2.5" 只是**数量级估算**。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DOCS = Path(__file__).resolve().parent.parent / "工作文档"
CARD_LIMIT = 1536          # §11.2 规则 1：速查卡 ≤1.5KB（字节）


def est_tokens(nbytes: int) -> int:
    return int(round(nbytes / 2.5))


def blen(s: str) -> int:
    return len(s.encode("utf-8"))


def card_of(text: str) -> str:
    """截 `## ★ 速查卡` 到下一个分隔线（---）之间 = 速查卡那一页。"""
    lines = text.splitlines(keepends=True)
    out, on = [], False
    for ln in lines:
        if ln.startswith("## ★ 速查卡"):
            on = True
        elif on and ln.startswith("## "):
            break
        elif on and ln.strip() == "---":
            break
        if on:
            out.append(ln)
    return "".join(out)


def main() -> None:
    print("== 一、工作文档/*.md（按字节降序，前十）==")
    rows, total = [], 0
    for p in sorted(DOCS.glob("*.md")):
        b = p.stat().st_size
        total += b
        rows.append((b, p.name))
    rows.sort(reverse=True)
    for b, n in rows[:10]:
        print(f"  {b:>7} B  (~{est_tokens(b):>6} 词元)  {n}")
    print(f"  ---- 全部 {len(rows)} 份：{total} B (~{est_tokens(total)} 词元)")

    print("\n== 二、每份报告的 ★速查卡（§11 上限 1.5KB）==")
    n = 0
    for b, name in sorted(rows):
        p = DOCS / name
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        card = card_of(text)
        if not card:
            continue
        n += 1
        cb = blen(card)
        flag = "✅" if cb <= CARD_LIMIT else f"❌ 超上限 {cb - CARD_LIMIT} B"
        print(f"  {flag}  速查卡 {cb:>5} B ({len(card.splitlines())} 行) / 全文 {b:>6} B"
              f" = {cb / b * 100:>4.1f}%   {name}")
    if not n:
        print("  （还没有报告带 ★速查卡）")
    print(f"\n  换算提醒：中文 markdown ≈ 2.5 字节/词元，⚠️ **数量级估算**，不是真分词。")


if __name__ == "__main__":
    main()
