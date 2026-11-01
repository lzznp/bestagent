# -*- coding: utf-8 -*-
"""一次性把"实况取证"需要的行范围 dump 到 UTF-8 文件（只读，不改任何东西）。
输出 _dump_20260922.txt
"""
from pathlib import Path

W = Path(__file__).resolve().parent          # bestagent
ROOT = W.parent                              # 工作区根
OUT = W / "_dump_20260922.txt"

RANGES = [
    (W / "framework_config.py", 1, 20),
    (W / "framework_config.py", 71, 91),
    (W / "framework_config.py", 166, 195),
    (W / "m3_chat.py", 528, 546),
    (W / "m3_chat.py", 900, 925),
    (W / "m3_chat.py", 1257, 1305),
    (W / "m3_chat.py", 1866, 1872),
    (W / "m3_chat.py", 1903, 1909),
    (W / "m3_chat.py", 2060, 2066),
    (W / "m3_chat.py", 2310, 2316),
    (W / "m3_chat.py", 2343, 2358),
    (W / "m3_chat.py", 2426, 2455),
    (W / "m3_chat.py", 2634, 2640),
    (ROOT / "工作文档" / "PROGRESS.md", 440, 448),
    (ROOT / "工作文档" / "DSH升级事故·衔接报告.md", 282, 300),
    (ROOT / "工作文档" / "省token第一刀与岗位认人·衔接报告.md", 215, 232),
    (ROOT / "工作文档" / "省token第一刀与岗位认人·衔接报告.md", 274, 280),
    (ROOT / "工作文档" / "搜索体检与一岗一库·衔接报告.md", 408, 422),
]

L = []


def out(s=""):
    L.append(str(s))


def main():
    for path, a, b in RANGES:
        out("=" * 78)
        out(f"### {path}  [{a}-{b}]")
        if not path.exists():
            out("  （文件不存在）")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i in range(a, min(b, len(lines)) + 1):
            out(f"{i:5}: {lines[i-1]}")
    # 找 dsh_home 里的 cordis.patch.yml（tool row id 的来源）
    out("=" * 78)
    out("### dsh_home 下的 cordis*.yml")
    for p in sorted((W / "data" / "dsh_home").rglob("cordis*.yml")):
        out(f"  {p}  ({p.stat().st_size} B)")
    # probe_tools.py 全文行数 + 前 40 行
    pt = W / "probe_tools.py"
    out("=" * 78)
    out(f"### {pt}")
    if pt.exists():
        lines = pt.read_text(encoding="utf-8", errors="replace").splitlines()
        out(f"  （全文 {len(lines)} 行）")
        for i, ln in enumerate(lines[:45], 1):
            out(f"{i:5}: {ln}")
    else:
        out("  （不存在）")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(L))


if __name__ == "__main__":
    main()
